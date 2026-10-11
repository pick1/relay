# Qwen Agent

![Python](https://img.shields.io/badge/python-3.10+-3776AB?logo=python&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-ReAct_agent-1C3C3C)
![llama.cpp](https://img.shields.io/badge/llama.cpp-OpenAI_API-orange)
![Ollama](https://img.shields.io/badge/Ollama-supported-black?logo=ollama)
![Local](https://img.shields.io/badge/runs-100%25_local-success)

A local, tool-using AI agent with a live terminal status panel, persistent markdown memory, and a human-in-the-loop approval gate for anything that can change your system.

Works with any **OpenAI-compatible endpoint** (llama.cpp `llama-server`, a remote box like a Jetson) or **Ollama**.

---

## Features

- **ReAct agent** built on LangGraph `create_react_agent`
- **Live status panel** (rich): current state, active tool, step history, timing
- **Persistent memory**: three markdown files injected at startup and updated at session end
- **Approval gate**: `shell`, `write_file`, and `python_repl` require an explicit `y/n` before running
- **Two backends**: OpenAI-compatible server or Ollama, switched by environment variables
- **Readline history** across sessions (`~/.qwen_agent_history`)

---

## File Structure

```
qwen-agent/
├── agent.py            ← main entry point (UI loop, agent wiring)
├── config.py           ← model, backend & path settings (env-overridable)
├── tools.py            ← all agent tools
├── confirm_gate.py     ← thread-safe approval prompts for risky tools
├── memory_manager.py   ← loads/writes the memory .md files
├── run-local.sh        ← launcher for a local llama-server backend
├── detect_hardware.sh  ← suggests an Ollama model for your hardware
├── requirements.txt
│
├── memory.md           ← facts about you        (auto-updated, not tracked)
├── tasks.md            ← ongoing tasks          (auto-updated, not tracked)
└── qwen.md             ← agent's self-notes     (auto-updated, not tracked)
```

---

## Quick Start

### 1. Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install duckduckgo-search   # optional, enables web_search
```

### 2. Choose a backend

#### Option A — llama.cpp `llama-server` (recommended)

Start a server with tool-calling enabled (`--jinja` is required):

```bash
llama-server -m /path/to/model.gguf --alias my-model \
  --jinja -ngl 99 -c 32768 --port 8080
```

Then run the agent against it:

```bash
USE_XAVIER=true \
XAVIER_BASE_URL=http://localhost:8080/v1 \
XAVIER_MODEL=my-model \
python3 agent.py
```

Or edit and use the launcher:

```bash
./run-local.sh
```

> `USE_XAVIER` / `XAVIER_*` are historical names from the original Jetson AGX Xavier setup. They select the OpenAI-compatible backend and work with any such server, local or remote.

#### Option B — Ollama

```bash
./detect_hardware.sh            # optional: suggests a model for your RAM/GPU
ollama pull qwen3.5:9b
QWEN_MODEL=qwen3.5:9b python3 agent.py
```

### 3. Chat

Type normally. Say `exit`, `quit`, or `bye` to end the session; the agent will update its memory files before closing.

---

## Configuration

All settings live in `config.py` and can be overridden with environment variables.

| Variable | Default | Purpose |
|---|---|---|
| `QWEN_MODEL` | `qwen3:14b` | Ollama model name |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |
| `USE_XAVIER` | `false` | `true` = use the OpenAI-compatible backend |
| `XAVIER_BASE_URL` | `http://192.168.1.110:8080/v1` | OpenAI-compatible endpoint |
| `XAVIER_MODEL` | `gpt-oss-20b` | Model name / server alias |

`TEMPERATURE` (default `0.7`) is set directly in `config.py`.

---

## Tools

| Tool | What it does | Approval |
|---|---|:---:|
| `update_memory_files` | Rewrites memory.md / tasks.md / qwen.md | — |
| `read_file` | Read a file from disk | — |
| `list_directory` | List directory contents | — |
| `web_search` | DuckDuckGo search (top 5 results) | — |
| `write_file` | Create or overwrite a file | ✅ |
| `shell` | Run a shell command (30 s timeout) | ✅ |
| `python_repl` | Execute Python in an isolated namespace | ✅ |

### Approval gate

Tools run on a background thread while the status panel redraws on the main thread. Risky tools call `confirm_gate.ask(action, detail)`, which blocks until the UI thread pauses the panel, shows the pending action, and asks **Allow? [y/n]** (default: no). A denied action returns a message telling the model not to retry and to ask you how to proceed.

To gate a new tool:

```python
if not confirm_gate.ask("my_tool", detail_string):
    return DENIED
```

---

## How Memory Works

| File | Purpose |
|---|---|
| `memory.md` | Facts the agent learns about you: preferences, context, key info |
| `tasks.md` | Active tasks, todos, follow-ups between sessions |
| `qwen.md` | The agent's own style notes and operating reminders |

- **Read at startup:** injected into the system prompt.
- **Written at session end:** on `exit`, the agent calls `update_memory_files`, instructed to keep existing entries and only add or update.
- **Plain markdown:** edit them by hand any time.

> ⚠️ Smaller models sometimes drop content when rewriting whole files. Review with `git diff` (or a backup) after sessions until you trust your model.

These files contain personal details and are excluded via `.gitignore`.

---

## Tested Models

On an RTX 2060 (12 GB) with 32 GB RAM:

| Model | Backend | Speed | Notes |
|---|---|---|---|
| Gemma 4 26B-A4B (UD-IQ3_S) | llama-server, `--n-cpu-moe 12` | ~36 tok/s | Best overall; reliable tool calls; correct code fixes |
| Ternary Bonsai 2 27B (PTQ1_0) | PrismML llama.cpp fork | ~35 tok/s | Strong reasoning, but long forced thinking and sloppy patches |
| Qwen 3.5 9B (Q8_0) | Ollama | ~30 tok/s | Solid lightweight baseline |

MoE models with expert offload (`--n-cpu-moe`) give the best capability-per-VRAM on mid-range GPUs.

---

## Customising

- **Add a tool:** write a `@tool` function in `tools.py` and append it to `ALL_TOOLS`. Gate it if it can modify anything.
- **Change personality:** edit `BASE_PROMPT` in `agent.py`.
- **Change the session-end behavior:** edit the `closing` prompt in `main()` in `agent.py`.

---

## Safety Notes

- Approved shell commands run as your user, with your permissions.
- Web search results are untrusted input; a malicious page can try to steer the model. Keep the approval gate on.
- Abliterated or uncensored models will not push back on destructive actions. The gate is your only safeguard there.
