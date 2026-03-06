import threading
from typing import Optional, Dict, Any

from flask import Flask, render_template
from flask_socketio import SocketIO
import duck
from nfc_portal import (
    NfcPortalManager,
    PortalState,
    run_simulator_input_loop,
)

# --------------------------------
# Config
# --------------------------------

SIMULATION_MODE = False

# Real reader matching
LEFT_READER_MATCH = "0"
RIGHT_READER_MATCH = "1"


def classify_portal_side(reader_name: str) -> Optional[str]:
    """
    Supports both real reader names and simulation names.
    """
    reader_upper = reader_name.upper()

    if "SIM_LEFT" in reader_upper or "LEFT" in reader_upper or LEFT_READER_MATCH in reader_name:
        return "left"

    if "SIM_RIGHT" in reader_upper or "RIGHT" in reader_upper or RIGHT_READER_MATCH in reader_name:
        return "right"

    return None


# -----------------------------
# Duck data lookup (stub)
# -----------------------------
def get_duck_data(duck_id: str) -> Dict[str, Any]:
    default_value = {
        "_id": "5555555555555555555555555",
        "name": f"Not a real Duck {duck_id}",
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

    # base = default_value

    base = next(
        (x for x in duck_manager.data if x["_id"] == duck_id), default_value)

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
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

_state_lock = threading.Lock()
_last_uid_by_side: Dict[str, Optional[str]] = {"left": None, "right": None}
_active_ducks: Dict[str, Optional[Dict[str, Any]]] = {
    "left": None, "right": None}

_manager: Optional[NfcPortalManager] = None


def _portal_payload(state: PortalState) -> Dict[str, Any]:
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

        if uid_now is None:
            _active_ducks[side] = None
        else:
            _active_ducks[side] = get_duck_data(new_state.get_id())

    if uid_now is None:
        socketio.emit("portal_clear", {"side": side})
    else:
        socketio.emit("portal_update", _portal_payload(new_state))


def start_nfc_manager():
    global _manager

    if _manager is not None:
        return

    _manager = NfcPortalManager(
        poll_interval_seconds=0.20,
        memory_page_end_inclusive=0x40,
        on_state_changed=on_state_changed,
        simulation_mode=SIMULATION_MODE,
    )
    _manager.start()


@app.route("/")
def index():
    return render_template("index.html")


@socketio.on("connect")
def _on_connect():
    with _state_lock:
        snapshot = dict(_last_uid_by_side)
        ducks_snapshot = dict(_active_ducks)

    for side, uid in snapshot.items():
        if uid:
            socketio.emit(
                "portal_update",
                {"side": side, "uid": uid, "duck": ducks_snapshot[side]},
            )
        else:
            socketio.emit("portal_clear", {"side": side})


if __name__ == "__main__":
    start_nfc_manager()
    duck_manager = duck.DuckManager()
    if SIMULATION_MODE:
        server_thread = threading.Thread(
            target=lambda: socketio.run(
                app,
                host="0.0.0.0",
                port=5000,
                debug=False,
                use_reloader=False,
            ),
            daemon=True,
        )
        server_thread.start()

        print("Flask server running at http://localhost:5000")
        print("Simulation mode is ON.")
        run_simulator_input_loop(_manager)
    else:
        socketio.run(app, host="0.0.0.0", port=5000, debug=True)
