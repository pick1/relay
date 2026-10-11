#!/usr/bin/env bash
export USE_OPENAI=true OPENAI_BASE_URL=http://localhost:8080/v1 OPENAI_MODEL=gemma4-26b
exec python3 "$(dirname "$0")/agent.py" "$@"
