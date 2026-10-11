# confirm_gate.py — lets tools (worker thread) ask the UI thread for approval
import threading

_lock = threading.Lock()
_pending = threading.Event()
_answered = threading.Event()
_state = {"action": "", "detail": "", "ok": False}

def ask(action: str, detail: str) -> bool:
    """Called from a tool. Blocks until the UI thread answers."""
    with _lock:
        _state.update(action=action, detail=detail, ok=False)
        _answered.clear()
        _pending.set()
        _answered.wait()
        return _state["ok"]

def pending() -> bool:
    return _pending.is_set()

def question() -> tuple[str, str]:
    return _state["action"], _state["detail"]

def answer(ok: bool) -> None:
    _state["ok"] = ok
    _pending.clear()
    _answered.set()
