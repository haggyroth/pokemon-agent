from pathlib import Path
from dotenv import load_dotenv
import atexit
import os
import shutil
import sys
import tempfile

load_dotenv()

PROJECT_ROOT = Path(__file__).parent

# ── Env parsing helpers ────────────────────────────────────────────────────────
# Numeric env vars are read through _env_int/_env_float so a typo (MAX_STEPS=200a)
# or an out-of-range value fails loudly at startup naming the variable, instead of
# a bare ValueError stack trace from some later module.

def _env_int(name: str, default: int, *, minimum: int | None = None,
             maximum: int | None = None) -> int:
    """Read an integer env var, exiting with a clear message on a bad value."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise SystemExit(f"Invalid integer for {name}: {raw!r}") from exc
    if minimum is not None and value < minimum:
        raise SystemExit(f"{name}={value} is below minimum {minimum}")
    if maximum is not None and value > maximum:
        raise SystemExit(f"{name}={value} is above maximum {maximum}")
    return value


def _env_float(name: str, default: float, *, minimum: float | None = None,
               maximum: float | None = None) -> float:
    """Read a float env var, exiting with a clear message on a bad value."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise SystemExit(f"Invalid float for {name}: {raw!r}") from exc
    if minimum is not None and value < minimum:
        raise SystemExit(f"{name}={value} is below minimum {minimum}")
    if maximum is not None and value > maximum:
        raise SystemExit(f"{name}={value} is above maximum {maximum}")
    return value


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
MAX_STEPS         = _env_int("MAX_STEPS", 0, minimum=0)
# USE_VISION: attach the live screenshot (and overhead area maps) to the model.
# Set false for text-only models, or models whose vision is unstable/blows the
# context window — the observation string carries the key state either way.
USE_VISION        = os.getenv("USE_VISION", "true").lower() == "true"

# ── Live viewer (native backend only) ─────────────────────────────────────────
# Show a window rendering the game as the agent plays. Requires pygame.
SHOW_WINDOW       = os.getenv("SHOW_WINDOW",  "false").lower() == "true"
VIEWER_SCALE      = _env_int("VIEWER_SCALE", 3, minimum=1)    # 240x160 -> 720x480
VIEWER_FPS        = _env_int("VIEWER_FPS", 120, minimum=0)    # playback pace cap; 0 = uncapped

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
# LLM_API_KEY: prefer an explicit key. Fall back to OPENAI_API_KEY ONLY when the
# endpoint really is OpenAI — never hand one provider's key to another (a stray
# OPENAI_API_KEY in the shell would otherwise be sent to OpenRouter/Together/Groq).
if "api.openai.com" in LLM_BASE_URL:
    _api_key_default = os.getenv("OPENAI_API_KEY", "lm-studio")
else:
    if os.getenv("OPENAI_API_KEY") and not os.getenv("LLM_API_KEY"):
        print("WARNING: OPENAI_API_KEY is set but LLM_BASE_URL is not an OpenAI "
              "endpoint; refusing to send that key to a third party. Set "
              "LLM_API_KEY explicitly to authenticate.", file=sys.stderr)
    _api_key_default = "lm-studio"
LLM_API_KEY       = os.getenv("LLM_API_KEY", _api_key_default)

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
TEMPERATURE       = _env_float("TEMPERATURE", 0.6, minimum=0.0)
MAX_TOKENS        = _env_int("MAX_TOKENS", 4096, minimum=1)
ENABLE_THINKING   = os.getenv("ENABLE_THINKING",   "false").lower() == "true"

# ── Spend controls (matter once LLM_BASE_URL points at a paid cloud endpoint) ──
# The main loop is otherwise unbounded (MAX_STEPS=0) and issues up to 6 completions
# per decision step, each carrying a screenshot + history — free against local LM
# Studio, real money against OpenAI/OpenRouter. These caps end the run cleanly (same
# path as MAX_STEPS) once hit. 0 = unlimited.
#   MAX_LLM_CALLS: stop after this many chat-completion API calls.
#   TOKEN_BUDGET:  stop once cumulative (prompt+completion) tokens reach this.
MAX_LLM_CALLS     = _env_int("MAX_LLM_CALLS", 0, minimum=0)
TOKEN_BUDGET      = _env_int("TOKEN_BUDGET", 0, minimum=0)

# ── Operational guardrails (keep a long run from hanging) ──────────────────────
# LLM_TIMEOUT: per chat-completion request timeout in seconds. A local model can
# degrade catastrophically on a marathon run — a single call ballooned to 3+ HOURS
# in an 11-hour eval, which no step/spend cap could stop (they're checked BETWEEN
# steps). This bounds any one call; a timed-out call raises and counts against the
# consecutive-error budget, so a persistently-hung endpoint ends the run cleanly.
# 0 = no timeout.
LLM_TIMEOUT       = _env_float("LLM_TIMEOUT", 180, minimum=0.0)
# MAX_WALL_SECONDS: hard wall-clock cap on a whole run (checked each step). Belt-and-
# suspenders alongside LLM_TIMEOUT so an unattended run can't burn hours. 0 = unlimited.
MAX_WALL_SECONDS  = _env_float("MAX_WALL_SECONDS", 0.0, minimum=0.0)

# ── Timing ────────────────────────────────────────────────────────────────────
BUTTON_TAP_DELAY  = _env_float("BUTTON_TAP_DELAY", 0.10, minimum=0.0)
DECISION_INTERVAL = _env_float("DECISION_INTERVAL", 1.00, minimum=0.0)

# ── Reward ────────────────────────────────────────────────────────────────────
HP_HEAL_THRESHOLD = _env_float("HP_HEAL_THRESHOLD", 0.30, minimum=0.0, maximum=1.0)

# ── Paths ─────────────────────────────────────────────────────────────────────
SAVE_DIR          = PROJECT_ROOT / "saves"
JOURNAL_PATH      = PROJECT_ROOT / "logs" / "battles.jsonl"
PROGRESS_PATH     = PROJECT_ROOT / "logs" / "progress.json"
# Screenshot frame path. Default to a PER-PROCESS temp dir, not a fixed name in the
# shared temp dir: a predictable /tmp path lets another user pre-plant a symlink the
# native writer would follow/truncate (CWE-379), and two concurrent runs would clobber
# each other's frames (run B's screenshot fed to run A's model). #67
# The dir is created lazily on the first screenshot (not at import) and removed at
# exit — but only when we created it ourselves; a user-supplied SCREENSHOT_PATH is
# returned as-is and never deleted.
_SCREENSHOT_DIR = None


class _ScreenshotPath:
    """str()-/fspath()-compatible handle to the screenshot PNG.

    Resolves to the real path on first use, so importing config never creates a
    temp dir (USE_VISION=false runs and every import would otherwise leak one).
    """

    def __init__(self, explicit):
        self._explicit = explicit

    def _resolve(self):
        global _SCREENSHOT_DIR
        if self._explicit:
            return self._explicit
        if _SCREENSHOT_DIR is None:
            _SCREENSHOT_DIR = tempfile.mkdtemp(prefix="pokemon-agent-")
            atexit.register(shutil.rmtree, _SCREENSHOT_DIR, ignore_errors=True)
        return str(Path(_SCREENSHOT_DIR) / "frame.png")

    def __str__(self):
        return self._resolve()

    def __fspath__(self):
        return self._resolve()

    def __repr__(self):
        return repr(self._resolve())


SCREENSHOT_PATH   = _ScreenshotPath(os.getenv("SCREENSHOT_PATH"))
