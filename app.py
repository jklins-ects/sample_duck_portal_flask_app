import json
import threading
from typing import Optional, Dict, Any

from flask import Flask, render_template
from flask_socketio import SocketIO

# Uses the same portal manager + state type your existing script uses
from nfc_portal import NfcPortalManager, PortalState

import duck

# Match your reader naming (copied from your controller pattern)
LEFT_READER_MATCH = "0"
RIGHT_READER_MATCH = "1"


def classify_portal_side(reader_name: str) -> Optional[str]:
    if LEFT_READER_MATCH in reader_name:
        return "left"
    if RIGHT_READER_MATCH in reader_name:
        return "right"
    return None


# -----------------------------
# Duck data lookup (stub)
# -----------------------------
def get_duck_data(duck_id: str) -> Dict[str, Any]:
    """
    TODO: Replace this with your real lookup.
    For now, returns hardcoded data (and tweaks name/id so you can test different UIDs).
    """
    default_value = {
        "_id": "5555555555555555555555555",
        "name": "Not a real Duck",
        "adjectives": ["bright", "hopeful", "cheerful"],
        "body": {"head": "yellow", "front1": "pink", "front2": "purple", "back1": "green", "back2": "blue"},
        "derpy": False,
        "bio": "We'll get this working soon.",
        "date": "2026-03-04T00:00:00.000Z",
        "approved": True,
        "stats": {"strength": 6, "health": 7, "focus": 6, "intelligence": 7, "kindness": 10},
        "__v": 0,
        "assembler": "Nobody, it's fake",
    }

    base = default_value
    """
    base = next((x for x in duck_manager.data if x["_id"] == duck_id), default_value)
    """

    # make it obvious on-screen which duck is which
    out = dict(base)
    out["_id"] = duck_id
    out["name"] = f"{base['name']} ({duck_id[-4:]})" if duck_id else base["name"]
    return out


# -----------------------------
# Flask / Socket.IO setup
# -----------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = "dev"

# If you use eventlet or gevent, it’s even smoother; threading works fine for starters.
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Track last-seen per side so we only emit when changes happen
_state_lock = threading.Lock()
_last_uid_by_side: Dict[str, Optional[str]] = {"left": None, "right": None}
_active_ducks: Dict[str, Optional[Dict[str, Any]]] = {
    "left": None, "right": None}


def _portal_payload(state: PortalState) -> Dict[str, Any]:
    # Use UID as duck_id (you can swap this to read JSON-from-tag later)
    duck_id = state.get_id()

    duck = get_duck_data(duck_id)

    return {
        "side": classify_portal_side(state.reader_name),
        "uid": state.uid_hex,
        "duck": duck,
    }


def on_state_changed(old_state: PortalState, new_state: PortalState):
    side = classify_portal_side(new_state.reader_name)
    if side is None:
        return

    uid_now = new_state.uid_hex if new_state.has_tag() else None
    with _state_lock:
        uid_prev = _last_uid_by_side.get(side)
        if uid_now == uid_prev:
            return
        _last_uid_by_side[side] = uid_now
        duck_now = get_duck_data(new_state.get_id())
        _active_ducks[side] = duck_now
    # Emit to all connected browsers
    if uid_now is None:
        socketio.emit("portal_clear", {"side": side})
    else:
        socketio.emit("portal_update", _portal_payload(new_state))


_manager: Optional[NfcPortalManager] = None


def start_nfc_manager():
    global _manager
    if _manager is not None:
        return

    _manager = NfcPortalManager(
        poll_interval_seconds=0.20,
        memory_page_end_inclusive=0x40,
        on_state_changed=on_state_changed,
    )
    _manager.start()


@app.route("/")
def index():
    return render_template("index.html")


@socketio.on("connect")
def _on_connect():
    """
    When a client connects, push the current known state so the UI is correct.
    """
    with _state_lock:
        snapshot = dict(_last_uid_by_side)

    for side, uid in snapshot.items():
        if uid:
            # fake a payload without needing PortalState:
            socketio.emit(
                "portal_update",
                {"side": side, "uid": uid, "duck": _active_ducks[side]},
            )
        else:
            socketio.emit("portal_clear", {"side": side})


if __name__ == "__main__":
    # Start NFC manager once when server starts
    start_nfc_manager()
    duck_manager = duck.DuckManager()
    # Run web server
    socketio.run(app, host="0.0.0.0", port=5000, debug=True)
