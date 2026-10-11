# ============================================================
#  config.py — central settings for the Qwen Agent
#  Edit MODEL after running detect_hardware.sh
# ============================================================

import os

# ── Model ────────────────────────────────────────────────
# Run detect_hardware.sh to find the best value for your machine
MODEL = os.getenv("AGENT_MODEL", os.getenv("QWEN_MODEL", "qwen3:14b"))
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# ── Xavier (OpenAI-compatible) override ─────────────────────────────
USE_XAVIER = os.getenv("USE_OPENAI", os.getenv("USE_XAVIER", "false")).lower() == "true"
XAVIER_BASE_URL = os.getenv("OPENAI_BASE_URL") or os.getenv("XAVIER_BASE_URL", "http://192.168.1.110:8080/v1")
XAVIER_MODEL = os.getenv("OPENAI_MODEL") or os.getenv("XAVIER_MODEL", "gpt-oss-20b")

# ── Agent memory files ───────────────────────────────────────
AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
MEMORY_FILE  = os.path.join(AGENT_DIR, "memory.md")
TASKS_FILE   = os.path.join(AGENT_DIR, "tasks.md")
QWEN_FILE    = os.path.join(AGENT_DIR, "qwen.md")

# ── Conversation ─────────────────────────────────────────────
MAX_HISTORY_MESSAGES = 20     # short-term window kept in context
TEMPERATURE          = 0.7