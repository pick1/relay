#!/usr/bin/env python3
# ============================================================
#  agent.py — Qwen Agent with live status panel (rich UI)
#  Fixed: persistent event loop (no "Event loop is closed")
# ============================================================

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning)

import json
import readline
import atexit
import os
import asyncio
import threading
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.live import Live
from rich.table import Table
from rich.text import Text
from rich.rule import Rule

from config import MODEL, OLLAMA_BASE_URL, TEMPERATURE, USE_XAVIER, XAVIER_BASE_URL, XAVIER_MODEL
from memory_manager import build_system_prompt
from tools import ALL_TOOLS

def get_display_model() -> str:
    """Return the model name to display in the status bar."""
    return XAVIER_MODEL if USE_XAVIER else MODEL

# Conditional LLM import
if USE_XAVIER:
    from langchain_openai import ChatOpenAI
else:
    from langchain_ollama import ChatOllama

from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langgraph.prebuilt import create_react_agent

# ── Input history (up/down arrow) ──────────────────────────
_HISTORY_FILE = os.path.expanduser("~/.qwen_agent_history")
try:
    readline.read_history_file(_HISTORY_FILE)
except FileNotFoundError:
    pass
readline.set_history_length(500)
atexit.register(readline.write_history_file, _HISTORY_FILE)

console = Console()

BASE_PROMPT = f"""You are Qwen, a capable and thoughtful AI assistant running locally on a Linux workstation.

IMPORTANT — filesystem facts:
- The user's home directory is /home/dp
- Always expand ~ to /home/dp when using tools
- When a user gives a path like /Documents/... they mean /home/dp/Documents/...

You have persistent memory across sessions via three markdown files that you read at startup
and update at the end of every session.

You are direct, practical, and honest. You think step by step for complex problems.
You always update your memory files at the end of a session — never skip this."""

# ── Status tracker ───────────────────────────────────────────

class AgentStatus:
    def __init__(self):
        self.state      = "idle"
        self.current_tool = None
        self.tool_input   = None
        self.steps: list[dict] = []
        self.start_time   = None
        self.turn_count   = 0

    def reset_turn(self):
        self.state        = "thinking"
        self.current_tool = None
        self.tool_input   = None
        self.steps        = []
        self.start_time   = datetime.now()
        self.turn_count  += 1

    def tool_call(self, name: str, inp: str):
        self.state        = "tool"
        self.current_tool = name
        self.tool_input   = inp[:80] + "…" if len(inp) > 80 else inp

    def tool_done(self, name: str, result: str):
        self.state = "thinking"
        preview = result[:60] + "…" if len(result) > 60 else result
        self.steps.append({"tool": name, "result": preview})
        self.current_tool = None

    def done(self):
        self.state = "done"

    def elapsed(self) -> str:
        if not self.start_time:
            return "0s"
        s = int((datetime.now() - self.start_time).total_seconds())
        return f"{s}s" if s < 60 else f"{s//60}m{s%60}s"

status = AgentStatus()

STATE_COLORS = {"idle": "dim white", "thinking": "yellow", "tool": "cyan", "done": "green"}
STATE_ICONS  = {"idle": "○", "thinking": "◈", "tool": "⚙", "done": "✓"}

def render_status() -> Panel:
    color = STATE_COLORS.get(status.state, "white")
    icon  = STATE_ICONS.get(status.state,  "?")
    
    grid = Table.grid(padding=(0, 1))
    grid.add_column(style="bold", min_width=10)
    grid.add_column()
    
    grid.add_row("Status", Text(f"{icon} {status.state.upper()}", style=f"bold {color}"))
    grid.add_row("Model",  Text(get_display_model(), style="bright_blue"))
    elapsed = status.elapsed() if status.state != "idle" else "—"
    grid.add_row("Turn",   Text(f"#{status.turn_count}  {elapsed}", style="white"))
    
    if status.current_tool:
        grid.add_row("Tool",  Text(f"→ {status.current_tool}", style="bold cyan"))
        if status.tool_input:
            grid.add_row("Input", Text(status.tool_input, style="dim cyan"))
    
    if status.steps:
        grid.add_row("", Text(""))
        grid.add_row("Steps", Text(f"{len(status.steps)} completed", style="dim"))
        for s in status.steps[-4:]:
            grid.add_row(
                Text(f"  ✓ {s['tool']}", style="green"),
                Text(s["result"], style="dim white"),
            )
    
    return Panel(grid, title=f"[{color}]Qwen Agent[/]", border_style=color, padding=(0, 1))
def run_agent_sync(agent, history: list) -> tuple[list, str]:
    loop = _get_loop()
    result_box: dict = {}
    error_box:  dict = {}

    async def _run():
        async for event in agent.astream_events({"messages": history}, version="v2"):
            kind = event.get("event", "")
            name = event.get("name", "")
            data = event.get("data", {})

            if kind == "on_tool_start":
                inp = data.get("input", {})
                status.tool_call(name, json.dumps(inp) if isinstance(inp, dict) else str(inp))
            elif kind == "on_tool_end":
                status.tool_done(name, str(data.get("output", "")))

        # Final invoke for full message list
        result = agent.invoke({"messages": history})
        msgs   = result["messages"]
        reply  = "(no response)"
        for m in reversed(msgs):
            if isinstance(m, AIMessage) and m.content:
                reply = m.content
                break
        result_box["history"] = msgs
        result_box["reply"]   = reply

    future = asyncio.run_coroutine_threadsafe(_run(), loop)

    with Live(render_status(), console=console, refresh_per_second=8,
              vertical_overflow="visible") as live:
        status.reset_turn()
        while not future.done():
            live.update(render_status())
            threading.Event().wait(0.1)
        status.done()
        live.update(render_status())

    if future.exception():
        raise future.exception()

    return result_box["history"], result_box["reply"]

# ── Build agent ───────────────────────────────────────────────

def build_agent():
    if USE_XAVIER:
        llm = ChatOpenAI(
            model=XAVIER_MODEL,
            base_url=XAVIER_BASE_URL,
            temperature=TEMPERATURE,
            # api_key not needed for local Xavier; set to None to avoid missing credential errors
            api_key=None,
        )
    else:
        llm = ChatOllama(model=MODEL, base_url=OLLAMA_BASE_URL, temperature=TEMPERATURE)
    sys_prompt = build_system_prompt(BASE_PROMPT)
    return create_react_agent(model=llm, tools=ALL_TOOLS, prompt=sys_prompt), sys_prompt

# ── Main ─────────────────────────────────────────────────────

def main():
    console.print()
    console.print(Panel.fit(
        f"[bold bright_blue]Qwen Agent[/]  [dim]|[/]  [cyan]{get_display_model()}[/]\\n"
        f"[dim]Type your message. Say [bold]exit[/] or [bold]bye[/] to end.[/]",
        border_style="bright_blue", padding=(0, 2),
    ))
    console.print()

    try:
        agent, sys_prompt = build_agent()
    except Exception as e:
        console.print(f"[red]❌ Failed to connect to LLM:[/] {e}")
        if USE_XAVIER:
            console.print("[dim]Make sure Xavier is reachable at $XAVIER_BASE_URL[/]")
        else:
            console.print("[dim]Make sure Ollama is running:  ollama serve[/]")
        return

    history: list = [SystemMessage(content=sys_prompt)]

    while True:
        try:
            console.print(Rule(style="dim"))
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            user_input = "exit"

        if not user_input:
            continue

        if user_input.lower() in {"exit", "quit", "bye", "goodbye"}:
            console.print()
            console.print("[yellow]Wrapping up — updating memory files…[/]")
            closing = (
                "The session is ending now. Review our conversation and call "
                "\"update_memory_files\" with updated content for memory.md, tasks.md, and qwen.md."
            )
            history.append(HumanMessage(content=closing))
            try:
                history, reply = run_agent_sync(agent, history)
                console.print(f"\n[bold]Qwen:[/] {reply}\n")
            except Exception as e:
                console.print(f"[red](memory update error: {e})[/]")
            console.print("[green]Session saved. Goodbye![/]\n")
            break

        history.append(HumanMessage(content=user_input))
        console.print()

        try:
            history, reply = run_agent_sync(agent, history)
        except Exception as e:
            reply = f"(error: {e})"

        console.print()
        console.print(Panel(reply, title="[bold bright_blue]Qwen[/]", border_style="bright_blue", padding=(0, 1)))
        console.print()

if __name__ == "__main__":
    main()
