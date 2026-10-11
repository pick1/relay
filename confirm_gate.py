# confirm_gate.py — approval routing for risky tools.
# Rules first (auto-allow read-only / hard-deny dangerous), then a race between
# the terminal prompt and a Telegram Approve/Deny message. First answer wins.
# No answer within RELAY_APPROVAL_TIMEOUT seconds = deny (fail closed).
import json, os, re, secrets, select, sys, threading, urllib.parse, urllib.request, urllib.error
from pathlib import Path

HOME = str(Path.home())
TIMEOUT_S = int(os.getenv("RELAY_APPROVAL_TIMEOUT", "600"))

def _load_env(path: Path = Path.home() / ".config" / "relay" / "env") -> None:
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))
    except FileNotFoundError:
        pass

_load_env()
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Rules ────────────────────────────────────────────────────
_SAFE_SHELL = re.compile(
    r"^\s*(ls|cat|head|tail|wc|pwd|whoami|uname|date|df|du|free|uptime|which|file|stat"
    r"|grep|rg|nvidia-smi|ps|git\s+(status|log|diff|show|branch|remote\s+-v))(\s|$)")
_SHELL_META = re.compile(r"[;&|`>]|\$\(|<\(")
_DENY_SHELL = re.compile(
    r"\bsudo\b|\brm\s+-\w*r\w*f|\brm\s+-\w*f\w*r|\bmkfs|\bdd\s+if=|:\(\)\s*\{"
    r"|\bchmod\s+-R\b|\bchown\s+-R\b|(curl|wget)[^|]*\|\s*(ba)?sh"
    r"|git\s+push\b.*--force|\.ssh\b|\.config/(signal|relay)|\.git-credentials|\s/etc/")
_DENY_PATHS = [os.path.join(HOME, p) for p in (".ssh", ".config", ".git-credentials",
                                               ".bashrc", ".profile")] + ["/etc/", "/usr/", "/boot/"]

def classify(action: str, detail: str) -> str:
    """Return 'allow', 'deny', or 'ask'."""
    if action == "shell":
        if _DENY_SHELL.search(detail):
            return "deny"
        if _SAFE_SHELL.match(detail) and not _SHELL_META.search(detail):
            return "allow"
        return "ask"
    if action == "write_file":
        return "deny" if any(p in detail for p in _DENY_PATHS) else "ask"
    return "ask"   # python_repl and anything else

# ── Shared state ─────────────────────────────────────────────
_lock = threading.Lock()          # one approval at a time
_answer_lock = threading.Lock()   # first answer wins
_tg_lock = threading.Lock()       # one Telegram poller at a time
_pending = threading.Event()
_answered = threading.Event()
_state = {"action": "", "detail": "", "ok": False, "by": ""}

def pending() -> bool:
    return _pending.is_set()

def question() -> tuple[str, str]:
    return _state["action"], _state["detail"]

def answer(ok: bool, by: str = "terminal") -> bool:
    with _answer_lock:
        if _answered.is_set():
            return False
        _state.update(ok=ok, by=by)
        _answered.set()
        return True

def ask(action: str, detail: str) -> bool:
    """Called from a tool (worker thread). Blocks until approved/denied/timeout."""
    verdict = classify(action, detail)
    if verdict != "ask":
        return verdict == "allow"
    with _lock:
        _state.update(action=action, detail=detail, ok=False, by="")
        _answered.clear()
        _pending.set()
        if TG_TOKEN and TG_CHAT:
            nonce = secrets.token_hex(4)
            threading.Thread(target=_telegram_flow, args=(action, detail, nonce),
                             daemon=True).start()
        if not _answered.wait(TIMEOUT_S):
            answer(False, "timeout")
        _pending.clear()
        return _state["ok"]

# ── Terminal side (called from the UI thread) ────────────────
def prompt_terminal(console) -> None:
    from rich.panel import Panel
    action, detail = question()
    console.print(Panel(detail[:1500], title=f"[bold red]{action} wants to run[/]",
                        border_style="red", padding=(0, 1)))
    if TG_TOKEN and TG_CHAT:
        console.print("[dim]Also sent to Telegram — answer here or there.[/]")
    console.print("[bold red]Allow? [y/N][/] ", end="")
    sys.stdout.flush()
    while not _answered.is_set():
        ready, _, _ = select.select([sys.stdin], [], [], 0.2)
        if ready:
            line = sys.stdin.readline().strip().lower()
            answer(line in ("y", "yes"), "terminal")
            break
    if _state["by"] != "terminal":
        console.print(f"\n[cyan]→ {'approved' if _state['ok'] else 'denied'} ({_state['by']})[/]")

# ── Telegram side ────────────────────────────────────────────
def _tg(method: str, **params):
    data = urllib.parse.urlencode(
        {k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in params.items()}
    ).encode()
    url = f"https://api.telegram.org/bot{TG_TOKEN}/{method}"
    try:
        with urllib.request.urlopen(url, data=data, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:300]
        raise RuntimeError(f"{method} -> HTTP {e.code}: {body}") from None

def _telegram_flow(action: str, detail: str, nonce: str) -> None:
    with _tg_lock:
        try:
            last = _tg("getUpdates", offset=-1, timeout=0).get("result", [])
            offset = last[-1]["update_id"] + 1 if last else None
            text = (f"Relay wants to run {action}:\n\n{detail[:3500]}\n\n"
                    f"Auto-deny in {TIMEOUT_S // 60} min.")
            kb = {"inline_keyboard": [[
                {"text": "✅ Approve", "callback_data": f"ok:{nonce}"},
                {"text": "❌ Deny", "callback_data": f"no:{nonce}"}]]}
            msg = _tg("sendMessage", chat_id=TG_CHAT, text=text, reply_markup=kb)["result"]
            while not _answered.is_set():
                params = {"timeout": 10, "allowed_updates": ["callback_query"]}
                if offset is not None:
                    params["offset"] = offset
                for u in _tg("getUpdates", **params).get("result", []):
                    offset = u["update_id"] + 1
                    cq = u.get("callback_query")
                    if not cq or str(cq["from"]["id"]) != str(TG_CHAT):
                        continue   # ignore anyone who isn't you
                    kind, _, n = cq.get("data", "").partition(":")
                    if n != nonce:
                        continue   # stale button from an older request
                    _tg("answerCallbackQuery", callback_query_id=cq["id"])
                    answer(kind == "ok", "phone")
            result = "✅ Approved" if _state["ok"] else "❌ Denied"
            _tg("editMessageText", chat_id=TG_CHAT, message_id=msg["message_id"],
                text=f"{text}\n\n{result} ({_state['by']})")
        except Exception as e:
            print(f"\n[telegram approval unavailable: {e}]", file=sys.stderr)
