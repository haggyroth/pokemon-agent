from pathlib import Path
from dotenv import load_dotenv
import os
import tempfile

load_dotenv()

PROJECT_ROOT = Path(__file__).parent

# ── Emulator backend ──────────────────────────────────────────────────────────
# "native": drive libmgba in-process (no GUI/Lua/mGBA-http). Requires the
#           compiled binding (python -m game._mgba_build) and `brew install mgba`.
# "http":   legacy mGBA-http transport (mGBA GUI + Lua socket + .NET server).
MGBA_BACKEND      = os.getenv("MGBA_BACKEND",      "native")
ROM_PATH          = os.path.expanduser(
                        os.getenv("ROM_PATH", "~/mgba-http/Pokemon_LeafGreen.gba"))

# ── Run control ───────────────────────────────────────────────────────────────
# START_FROM_SAVE: path to a battery .sav to load and "Continue" into at startup
#   (native backend) instead of booting a new game. Empty = boot the ROM as-is.
# MAX_STEPS: stop after N decision steps (0 = run until interrupted). Useful for
#   bounded smoke/eval runs.
START_FROM_SAVE   = os.path.expanduser(os.getenv("START_FROM_SAVE", ""))
# START_FROM_STATE: path to an mGBA save STATE (.ss*) to load directly at startup
#   (native backend). Loads instantly into exactly that scene — no title screen,
#   no Continue, no quest-log recap. Takes precedence over START_FROM_SAVE.
#   Handy for testing from a fixed spot (e.g. the Pallet Town exterior).
START_FROM_STATE  = os.path.expanduser(os.getenv("START_FROM_STATE", ""))
MAX_STEPS         = int(os.getenv("MAX_STEPS", "0"))
# USE_VISION: attach the live screenshot (and overhead area maps) to the model.
# Set false for text-only models, or models whose vision is unstable/blows the
# context window — the observation string carries the key state either way.
USE_VISION        = os.getenv("USE_VISION", "true").lower() == "true"

# ── Live viewer (native backend only) ─────────────────────────────────────────
# Show a window rendering the game as the agent plays. Requires pygame.
SHOW_WINDOW       = os.getenv("SHOW_WINDOW",  "false").lower() == "true"
VIEWER_SCALE      = int(os.getenv("VIEWER_SCALE", "3"))    # 240x160 -> 720x480
VIEWER_FPS        = int(os.getenv("VIEWER_FPS",   "60"))   # 0 = uncapped

# ── Network (http backend only) ───────────────────────────────────────────────
MGBA_HTTP_BASE    = os.getenv("MGBA_HTTP_BASE",    "http://localhost:5000")

# ── LLM endpoint ──────────────────────────────────────────────────────────────
# The agent uses an OpenAI-compatible client, so it works with LM Studio locally
# OR any OpenAI-compatible cloud endpoint (OpenAI, OpenRouter, Together, Groq,
# Anthropic's OpenAI-compat endpoint, …). To use a cloud model, set:
#   LLM_BASE_URL   e.g. https://api.openai.com/v1  or  https://openrouter.ai/api/v1
#   LLM_API_KEY    your provider key (kept out of git via .env)
#   MODEL_NAME     the provider's model id
# Defaults point at a local LM Studio server with a placeholder key.
# LM_STUDIO_BASE is kept as a back-compat alias for LLM_BASE_URL.
LLM_BASE_URL      = os.getenv("LLM_BASE_URL",
                              os.getenv("LM_STUDIO_BASE", "http://localhost:1234/v1"))
LM_STUDIO_BASE    = LLM_BASE_URL   # back-compat
LLM_API_KEY       = os.getenv("LLM_API_KEY", os.getenv("OPENAI_API_KEY", "lm-studio"))

# ── Model ─────────────────────────────────────────────────────────────────────
# Change MODEL_NAME to match the model loaded in LM Studio exactly.
#
# MAX_TOKENS is a CAP on the response, not a target — the model stops when it's
# done, so a bigger value just avoids truncating (important for reasoning models,
# where the tool call comes AFTER the reasoning). BUT: prompt + MAX_TOKENS must
# fit the model's *loaded* context window, or every call fails with "Context size
# exceeded". A model with a small loaded context (some quantized builds default
# to 4K–8K) needs a small MAX_TOKENS even though its max context is large — check
# LM Studio's loaded context length, not the model's max.
#
#   Model family                 TEMPERATURE  MAX_TOKENS (if context allows)
#   ────────────────────────────  ──────────   ──────────
#   Reasoning (thinking on)       0.6          4096–8192   ENABLE_THINKING=true
#   Instruct / chat (thinking off) 0.2–0.4     2048
#
# ENABLE_THINKING: set True only for models where LM Studio exposes
# reasoning_content (or <think>…</think>). Has no effect on other models.
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
