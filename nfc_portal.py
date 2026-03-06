"""
nfc_portal.py

Reusable NFC portal module for PC/SC CCID readers (pyscard).

Features:
- Polls all connected PC/SC readers
- Reads UID (Get Data)
- Reads Type 2 tag memory pages (NTAG21x / Ultralight style) via FF B0
- Extracts NDEF message TLV
- Parses NDEF records:
    - URL (Well-known 'U')
    - TEXT (Well-known 'T')
    - DATA(MIME)  (TNF_MIME_MEDIA)
    - DATA(EXTERNAL) (TNF_EXTERNAL_TYPE)
    - UNKNOWN fallback
- Detects tag present / removed / changed
- Emits callbacks with per-reader PortalState

Install:
    pip install pyscard
"""

from __future__ import annotations

import json
import time
import threading
import hashlib
from dataclasses import dataclass
from typing import Callable, Optional, Tuple, Dict, Any, List

from smartcard.System import readers
from smartcard.Exceptions import CardConnectionException, NoCardException


# -----------------------------
# PC/SC constants
# -----------------------------

STATUS_SUCCESS_SW1 = 0x90
STATUS_SUCCESS_SW2 = 0x00

# common PC/SC “Get UID” for contactless readers
APDU_GET_CARD_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]

ERROR_CARD_UNRESPONSIVE_HEX = "80100066"  # SCARD_W_UNRESPONSIVE_CARD
ERROR_CARD_REMOVED_HEX = "80100069"       # SCARD_W_REMOVED_CARD


def _is_transient_card_error(exception_object: Exception) -> bool:
    """
    True for “tag moved / flicker” errors. We treat these as “no stable tag”.
    """
    msg = str(exception_object).lower().replace("0x", "")
    return (
        "not responding to a reset" in msg
        or "has been removed" in msg
        or "further communication is not possible" in msg
        or ERROR_CARD_UNRESPONSIVE_HEX in msg
        or ERROR_CARD_REMOVED_HEX in msg
        or isinstance(exception_object, NoCardException)
    )


# -----------------------------
# NDEF constants
# -----------------------------

TNF_WELL_KNOWN = 0x01
TNF_MIME_MEDIA = 0x02
TNF_ABSOLUTE_URI = 0x03
TNF_EXTERNAL_TYPE = 0x04

NDEF_TYPE_URI = b"U"
NDEF_TYPE_TEXT = b"T"

URI_PREFIX_TABLE = [
    "", "http://www.", "https://www.", "http://", "https://",
    "tel:", "mailto:", "ftp://anonymous:anonymous@", "ftp://ftp.",
    "ftps://", "sftp://", "smb://", "nfs://", "ftp://", "dav://",
    "news:", "telnet://", "imap:", "rtsp://", "urn:", "pop:",
    "sip:", "sips:", "tftp:", "btspp://", "btl2cap://",
    "btgoep://", "tcpobex://", "irdaobex://", "file://",
    "urn:epc:id:", "urn:epc:tag:", "urn:epc:pat:", "urn:epc:raw:",
    "urn:epc:", "urn:nfc:"
]


# -----------------------------
# Public data types
# -----------------------------

@dataclass(frozen=True)
class NdefRecord:
    """
    One decoded NDEF record.

    payload_bytes: raw bytes exactly as stored in the tag record payload.
    text_value: friendly interpretation (best-effort) for display/logging.
    """
    kind: str  # "URL" | "TEXT" | "DATA(MIME)" | "DATA(EXTERNAL)" | "ABSOLUTE_URI" | "UNKNOWN"
    type_text: str
    payload_bytes: bytes
    text_value: str
    mime_type: Optional[str] = None
    external_type: Optional[str] = None

    def as_utf8(self, errors: str = "strict") -> str:
        return self.payload_bytes.decode("utf-8", errors=errors)

    def as_json(self) -> Any:
        """
        Parse payload as JSON.

        Some phone NFC apps write "smart quotes" (curly quotes) which are NOT valid JSON.
        We normalize common curly quotes to straight quotes before json.loads.
        """
        raw_text = self.payload_bytes.decode("utf-8", errors="strict")

        # Normalize “ ” ‘ ’ to standard JSON quotes
        normalized_text = (
            raw_text.replace("\u201c", '"')
                    .replace("\u201d", '"')
                    .replace("\u2018", "'")
                    .replace("\u2019", "'")
            # non-breaking space -> space (sometimes appears)
                    .replace("\u00A0", " ")
        )

        return json.loads(normalized_text)

    def looks_like_json(self) -> bool:
        s = self.text_value.strip()
        return (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]"))


@dataclass(frozen=True)
class PortalState:
    """
    Current stable state for one reader.
    """
    reader_name: str
    uid_hex: Optional[str]                  # None when no tag present
    ndef_records: Tuple[NdefRecord, ...]    # empty when none/unknown

    def has_tag(self) -> bool:
        return self.uid_hex is not None

    def first_text(self) -> Optional[str]:
        for r in self.ndef_records:
            if r.kind == "TEXT" and r.text_value.strip():
                return r.text_value.strip()
        return None

    def first_url(self) -> Optional[str]:
        for r in self.ndef_records:
            if r.kind == "URL" and r.text_value.strip():
                return r.text_value.strip()
        return None

    def first_json(self) -> Optional[Any]:
        """
        Returns the first JSON object found.
        Prefers explicit application/json MIME records.
        Falls back to trying to parse JSON from raw payload bytes for other record types.
        """

        # 1) Prefer explicit application/json MIME record
        for r in self.ndef_records:
            if r.kind == "DATA(MIME)" and (r.mime_type or "").lower() == "application/json":
                try:
                    return r.as_json()
                except Exception:
                    pass

        # 2) Next: try parsing JSON from raw bytes for other “data-like” records
        for r in self.ndef_records:
            if r.kind in ("DATA(MIME)", "DATA(EXTERNAL)", "UNKNOWN", "ABSOLUTE_URI", "TEXT", "URL"):
                try:
                    return r.as_json()
                except Exception:
                    pass

        return None

    def get_id(self) -> str:
        obj = self.first_json()
        if isinstance(obj, dict) and isinstance(obj.get("name"), str) and obj["name"].strip():
            return obj["_id"].strip()
        txt = self.first_text()
        if txt:
            return txt
        return ""

    def get_name(self) -> str:
        """
        Best-effort duck name:
          1) JSON field "name" if present
          2) TEXT record value
          3) URL last path segment (optional)
          4) UID fallback
        """
        obj = self.first_json()
        if isinstance(obj, dict) and isinstance(obj.get("name"), str) and obj["name"].strip():
            return obj["name"].strip()

        txt = self.first_text()
        if txt:
            return txt

        url = self.first_url()
        if url:
            # optional heuristic: last path chunk
            parts = [p for p in url.split("/") if p]
            if parts:
                return parts[-1]

        return self.uid_hex or "Unknown Duck"


# -----------------------------
# Type 2: read memory + extract NDEF TLV
# -----------------------------

def _read_type2_memory_pages(card_connection, start_page_inclusive: int, end_page_inclusive: int) -> Optional[bytes]:
    """
    Reads Type 2 tag pages (4 bytes each) via PC/SC READ BINARY:
      FF B0 00 <page> 04

    Returns bytes or None if not supported on this reader/tag combo.
    """
    dump = bytearray()
    for page in range(start_page_inclusive, end_page_inclusive + 1):
        apdu_read_page = [0xFF, 0xB0, 0x00, page & 0xFF, 0x04]
        page_bytes, sw1, sw2 = card_connection.transmit(apdu_read_page)
        if (sw1, sw2) != (STATUS_SUCCESS_SW1, STATUS_SUCCESS_SW2) or len(page_bytes) != 4:
            return None
        dump.extend(page_bytes)
    return bytes(dump)


def _extract_ndef_from_type2_tlvs(type2_memory_bytes: bytes) -> Optional[bytes]:
    """
    Scans TLVs starting at byte offset 16 (page 4) and returns the NDEF Message TLV (0x03) payload.
    """
    if not type2_memory_bytes or len(type2_memory_bytes) < 16:
        return None

    idx = 16
    n = len(type2_memory_bytes)

    while idx < n:
        tlv_tag = type2_memory_bytes[idx]
        idx += 1

        if tlv_tag == 0x00:
            continue
        if tlv_tag == 0xFE:
            return None

        if idx >= n:
            return None

        tlv_length = type2_memory_bytes[idx]
        idx += 1

        # Long-form length support
        if tlv_length == 0xFF:
            if idx + 1 >= n:
                return None
            tlv_length = (type2_memory_bytes[idx]
                          << 8) | type2_memory_bytes[idx + 1]
            idx += 2

        if idx + tlv_length > n:
            return None

        tlv_value = type2_memory_bytes[idx:idx + tlv_length]
        idx += tlv_length

        if tlv_tag == 0x03:
            return tlv_value

    return None


# -----------------------------
# NDEF parsing helpers
# -----------------------------

def _safe_hex(payload_bytes: bytes, limit: int = 96) -> str:
    snippet = payload_bytes[:limit]
    hex_text = " ".join(f"{b:02X}" for b in snippet)
    return hex_text + (" …" if len(payload_bytes) > limit else "")


def _payload_to_text(payload_bytes: bytes) -> str:
    """
    Prefer UTF-8 text, fall back to HEX preview.
    """
    if not payload_bytes:
        return ""
    try:
        return payload_bytes.decode("utf-8")
    except Exception:
        return f"HEX: {_safe_hex(payload_bytes)}"


def _parse_ndef_message(ndef_message_bytes: bytes) -> Tuple[NdefRecord, ...]:
    """
    Parses an NDEF message into records, with both raw bytes + friendly strings.
    """
    if not ndef_message_bytes:
        return tuple()

    records: List[NdefRecord] = []
    idx = 0

    while idx < len(ndef_message_bytes):
        header = ndef_message_bytes[idx]
        idx += 1

        message_end = (header & 0x40) != 0
        short_record = (header & 0x10) != 0
        id_length_present = (header & 0x08) != 0
        tnf = header & 0x07

        if idx >= len(ndef_message_bytes):
            break

        type_length = ndef_message_bytes[idx]
        idx += 1

        if short_record:
            if idx >= len(ndef_message_bytes):
                break
            payload_length = ndef_message_bytes[idx]
            idx += 1
        else:
            if idx + 3 >= len(ndef_message_bytes):
                break
            payload_length = (
                (ndef_message_bytes[idx] << 24)
                | (ndef_message_bytes[idx + 1] << 16)
                | (ndef_message_bytes[idx + 2] << 8)
                | (ndef_message_bytes[idx + 3])
            )
            idx += 4

        record_id_length = 0
        if id_length_present:
            if idx >= len(ndef_message_bytes):
                break
            record_id_length = ndef_message_bytes[idx]
            idx += 1

        if idx + type_length > len(ndef_message_bytes):
            break
        type_bytes = ndef_message_bytes[idx:idx + type_length]
        idx += type_length

        # skip ID bytes if present
        if idx + record_id_length > len(ndef_message_bytes):
            break
        idx += record_id_length

        if idx + payload_length > len(ndef_message_bytes):
            break
        payload_bytes = ndef_message_bytes[idx:idx + payload_length]
        idx += payload_length

        type_text = type_bytes.decode("utf-8", errors="replace")

        # Friendly decoding
        if tnf == TNF_WELL_KNOWN and type_bytes == NDEF_TYPE_URI:
            prefix_code = payload_bytes[0] if len(payload_bytes) > 0 else 0
            uri_rest = payload_bytes[1:].decode("utf-8", errors="replace")
            prefix = URI_PREFIX_TABLE[prefix_code] if prefix_code < len(
                URI_PREFIX_TABLE) else ""
            records.append(
                NdefRecord(
                    kind="URL",
                    type_text=type_text,
                    payload_bytes=payload_bytes,
                    text_value=prefix + uri_rest,
                )
            )

        elif tnf == TNF_WELL_KNOWN and type_bytes == NDEF_TYPE_TEXT:
            # payload: status + lang + text
            if len(payload_bytes) >= 1:
                status = payload_bytes[0]
                lang_len = status & 0x3F
                text_part = payload_bytes[1 + lang_len:]
                text_value = text_part.decode("utf-8", errors="replace")
            else:
                text_value = ""
            records.append(
                NdefRecord(
                    kind="TEXT",
                    type_text=type_text,
                    payload_bytes=payload_bytes,
                    text_value=text_value,
                )
            )

        elif tnf == TNF_MIME_MEDIA:
            mime_type = type_text
            records.append(
                NdefRecord(
                    kind="DATA(MIME)",
                    type_text=type_text,
                    payload_bytes=payload_bytes,
                    text_value=_payload_to_text(payload_bytes),
                    mime_type=mime_type,
                )
            )

        elif tnf == TNF_EXTERNAL_TYPE:
            external_type = type_text
            records.append(
                NdefRecord(
                    kind="DATA(EXTERNAL)",
                    type_text=type_text,
                    payload_bytes=payload_bytes,
                    text_value=_payload_to_text(payload_bytes),
                    external_type=external_type,
                )
            )

        elif tnf == TNF_ABSOLUTE_URI:
            records.append(
                NdefRecord(
                    kind="ABSOLUTE_URI",
                    type_text=type_text,
                    payload_bytes=payload_bytes,
                    text_value=_payload_to_text(payload_bytes),
                )
            )

        else:
            records.append(
                NdefRecord(
                    kind="UNKNOWN",
                    type_text=type_text,
                    payload_bytes=payload_bytes,
                    text_value=_payload_to_text(payload_bytes),
                )
            )

        if message_end:
            break

    return tuple(records)


def _read_uid_hex(card_connection) -> Optional[str]:
    uid_bytes, sw1, sw2 = card_connection.transmit(APDU_GET_CARD_UID)
    if (sw1, sw2) != (STATUS_SUCCESS_SW1, STATUS_SUCCESS_SW2):
        return None
    return "".join(f"{b:02X}" for b in uid_bytes)


def _read_portal_state_for_reader(reader_obj, memory_page_end_inclusive: int) -> PortalState:
    """
    Reads a stable snapshot: UID + NDEF records.
    If no tag is present (or transient error), uid_hex=None and records=empty.
    """
    reader_name = str(reader_obj)
    try:
        connection = reader_obj.createConnection()
        connection.connect()

        uid_hex = _read_uid_hex(connection)
        if uid_hex is None:
            return PortalState(reader_name=reader_name, uid_hex=None, ndef_records=tuple())

        type2_dump = _read_type2_memory_pages(
            connection, 0x00, memory_page_end_inclusive)
        if type2_dump is None:
            return PortalState(reader_name=reader_name, uid_hex=uid_hex, ndef_records=tuple())

        ndef_message = _extract_ndef_from_type2_tlvs(type2_dump)
        if ndef_message is None:
            return PortalState(reader_name=reader_name, uid_hex=uid_hex, ndef_records=tuple())

        records = _parse_ndef_message(ndef_message)
        return PortalState(reader_name=reader_name, uid_hex=uid_hex, ndef_records=records)

    except (CardConnectionException, NoCardException) as e:
        if _is_transient_card_error(e):
            return PortalState(reader_name=reader_name, uid_hex=None, ndef_records=tuple())
        return PortalState(reader_name=reader_name, uid_hex=None, ndef_records=tuple())


def _fingerprint_state(state: PortalState) -> str:
    """
    Used to detect changes without “magic” comparisons.
    """
    h = hashlib.sha256()
    h.update((state.uid_hex or "").encode("utf-8"))
    for r in state.ndef_records:
        h.update(r.kind.encode("utf-8"))
        h.update((r.mime_type or "").encode("utf-8"))
        h.update((r.external_type or "").encode("utf-8"))
        h.update(r.type_text.encode("utf-8", errors="replace"))
        h.update(r.payload_bytes)
    return h.hexdigest()


# -----------------------------
# Manager (polling)
# -----------------------------

OnTagPresentCallback = Callable[[PortalState], None]
OnTagRemovedCallback = Callable[[PortalState], None]
OnStateChangedCallback = Callable[[PortalState, PortalState], None]


class NfcPortalManager:
    """
    Polling-based manager that detects insert/remove/change per reader.

    Why polling:
      - embedded tags can flicker
      - you want “changed” events, which are easiest by comparing snapshots
    """

    def __init__(
        self,
        poll_interval_seconds: float = 0.20,
        memory_page_end_inclusive: int = 0x40,
        on_tag_present: Optional[OnTagPresentCallback] = None,
        on_tag_removed: Optional[OnTagRemovedCallback] = None,
        on_state_changed: Optional[OnStateChangedCallback] = None,
    ):
        self.poll_interval_seconds = poll_interval_seconds
        self.memory_page_end_inclusive = memory_page_end_inclusive

        self.on_tag_present = on_tag_present
        self.on_tag_removed = on_tag_removed
        self.on_state_changed = on_state_changed

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._last_state_by_reader: Dict[str, PortalState] = {}
        self._last_fingerprint_by_reader: Dict[str, str] = {}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def get_current_states(self) -> Dict[str, PortalState]:
        return dict(self._last_state_by_reader)

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            current_reader_objects = readers()
            current_reader_names = [str(r) for r in current_reader_objects]

            # Ensure we track all readers we see
            for reader_name in current_reader_names:
                if reader_name not in self._last_state_by_reader:
                    empty = PortalState(
                        reader_name=reader_name, uid_hex=None, ndef_records=tuple())
                    self._last_state_by_reader[reader_name] = empty
                    self._last_fingerprint_by_reader[reader_name] = _fingerprint_state(
                        empty)

            for reader_obj in current_reader_objects:
                reader_name = str(reader_obj)
                old_state = self._last_state_by_reader.get(
                    reader_name, PortalState(
                        reader_name=reader_name, uid_hex=None, ndef_records=tuple())
                )

                new_state = _read_portal_state_for_reader(
                    reader_obj, self.memory_page_end_inclusive)
                new_fp = _fingerprint_state(new_state)
                old_fp = self._last_fingerprint_by_reader.get(reader_name, "")

                if new_fp != old_fp:
                    # Present / removed
                    if old_state.uid_hex is None and new_state.uid_hex is not None:
                        if self.on_tag_present:
                            self.on_tag_present(new_state)

                    elif old_state.uid_hex is not None and new_state.uid_hex is None:
                        if self.on_tag_removed:
                            self.on_tag_removed(old_state)

                    # Always emit state_changed if provided
                    if self.on_state_changed:
                        self.on_state_changed(old_state, new_state)

                    self._last_state_by_reader[reader_name] = new_state
                    self._last_fingerprint_by_reader[reader_name] = new_fp

            time.sleep(self.poll_interval_seconds)
