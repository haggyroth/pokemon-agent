from pathlib import Path
from dotenv import load_dotenv
import os
import tempfile

load_dotenv()

PROJECT_ROOT = Path(__file__).parent

# ── Network ───────────────────────────────────────────────────────────────────
MGBA_HTTP_BASE    = os.getenv("MGBA_HTTP_BASE",    "http://localhost:5000")
LM_STUDIO_BASE    = os.getenv("LM_STUDIO_BASE",    "http://localhost:1234/v1")

# ── Model ─────────────────────────────────────────────────────────────────────
# Change MODEL_NAME to match the model loaded in LM Studio exactly.
# Adjust TEMPERATURE and MAX_TOKENS to suit the model family:
#
#   Model family              MODEL_NAME example                TEMPERATURE  MAX_TOKENS
#   ─────────────────────── ─────────────────────────────────── ─────────── ──────────
#   Qwen3 (thinking on)      qwen/qwen3-14b                       0.6        8192
#   Qwen3 (thinking off)     qwen/qwen3.5-9b                      0.2        2048
#   Qwen2.5 Instruct         qwen/qwen2.5-14b-instruct            0.2        2048
#   Llama 3.x Instruct       lmstudio-community/llama-3.1-8b      0.4        2048
#   Mistral / Mixtral        mistralai/mistral-7b-instruct        0.3        2048
#   Gemma 3                  google/gemma-3-12b-it                0.4        2048
#
# ENABLE_THINKING: set True only for Qwen3 models where LM Studio exposes
# reasoning_content in the response.  Has no effect on other models.
MODEL_NAME        = os.getenv("MODEL_NAME",        "qwen/qwen2.5-14b-instruct")
TEMPERATURE       = float(os.getenv("TEMPERATURE", "0.6"))
MAX_TOKENS        = int(os.getenv("MAX_TOKENS",    "4096"))
ENABLE_THINKING   = os.getenv("ENABLE_THINKING",   "false").lower() == "true"

# ── Timing ────────────────────────────────────────────────────────────────────
BUTTON_TAP_DELAY  = float(os.getenv("BUTTON_TAP_DELAY",  "0.10"))
DECISION_INTERVAL = float(os.getenv("DECISION_INTERVAL", "1.00"))

# ── Reward ────────────────────────────────────────────────────────────────────
HP_HEAL_THRESHOLD = float(os.getenv("HP_HEAL_THRESHOLD", "0.30"))

# ── Paths ─────────────────────────────────────────────────────────────────────
SAVE_DIR          = PROJECT_ROOT / "saves"
JOURNAL_PATH      = PROJECT_ROOT / "logs" / "battles.jsonl"
PROGRESS_PATH     = PROJECT_ROOT / "logs" / "progress.json"
SCREENSHOT_PATH   = os.getenv("SCREENSHOT_PATH",
                               str(Path(tempfile.gettempdir()) / "mgba_agent_frame.png"))
