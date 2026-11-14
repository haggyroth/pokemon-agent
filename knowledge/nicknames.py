"""Nickname rules (pure). The MODEL invents the names; this module only makes sure the one it
chose can actually be typed on the Gen III naming keyboard and isn't a bland non-name."""
import re
import unicodedata

MAX_NAME = 10
# Keys the naming driver can type (game/naming.py): letters, digits, space, '.', ',', '!', '?'.
_ALLOWED = re.compile(r"[^A-Za-z0-9 .,!?]")
_FANCY = {"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-", "&": " and "}


def _clean(name: str) -> str:
    s = (name or "").strip()
    for k, v in _FANCY.items():
        s = s.replace(k, v)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[-_/]+", " ", s)
    s = _ALLOWED.sub("", s)
    return re.sub(r"\s+", " ", s).strip()


def sanitize(name: str) -> str:
    """Best-effort conversion of what the model wrote into something typeable: accents folded
    (Pokémon → Pokemon), '-' '_' '/' become spaces, anything else untypeable is dropped, runs of
    spaces collapse, and it is cut to 10 characters. May return '' (nothing usable)."""
    return _clean(name)[:MAX_NAME].strip()


def critique(name: str, species_name: str = "", taken=()) -> str | None:
    """Why `name` is a poor pick (so the model should try again), or None if it's fine.
    Poor = empty/one character, too long for the keyboard, just the species name (± a number),
    or already used on the team."""
    full = _clean(name)
    if len(full) < 2:
        return "that name is empty or a single character"
    if len(full) > MAX_NAME:
        return f"'{full}' is {len(full)} characters — the limit is {MAX_NAME}, so shorten it yourself"
    low = full.lower()
    squash = lambda t: re.sub(r"[\s\d]+", "", t.lower())
    if species_name and squash(low) == squash(species_name):
        return f"'{full}' is just the species name (with or without a number)"
    if low in {t.lower().strip() for t in taken if t}:
        return f"'{full}' is already on your team"
    return None


GUIDANCE = (
    "Give every Pokémon you catch a name with PERSONALITY — you choose, be inventive and a little funny: "
    "a pun on its species or moves, a pop-culture or food reference, a dramatic title, an old-timey "
    "name, a grumpy nickname that fits how it looks or fights. Never just the species name, never a "
    "number suffix, and no two alike. Max 10 characters; letters, digits, space . , ! ? only."
)
