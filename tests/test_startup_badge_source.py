"""Guard the startup badge-reconciliation call site (#60).

main.py imports heavy deps (openai, cffi, …) not present in the dependency-light
CI job, so we can't import it. Instead we statically assert the reconcile call is
fed from the relocation-safe reader — never the fixed Addr.BADGES, whose live read
drifts off the badge byte after a DMA relocation and permanently poisons LTM.
"""
import ast
from pathlib import Path

MAIN = Path(__file__).resolve().parent.parent / "main.py"


def _reconcile_call() -> ast.Call:
    tree = ast.parse(MAIN.read_text())
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "reconcile_badges_from_ram"):
            return node
    raise AssertionError("no reconcile_badges_from_ram() call found in main.py")


def test_reconcile_is_fed_from_reader_read_badges():
    call = _reconcile_call()
    assert call.args, "reconcile_badges_from_ram called with no argument"
    arg_src = ast.dump(call.args[0])
    # The argument must be reader.read_badges()[...] — an attribute call on `reader`.
    assert "read_badges" in arg_src, (
        "startup reconcile must read badges via reader.read_badges() "
        "(relocation-safe), not a raw memory read")


def test_reconcile_does_not_read_fixed_badges_address():
    call = _reconcile_call()
    arg_src = ast.dump(call.args[0])
    # Addr.BADGES is the fixed, DMA-unsafe address — must not feed reconcile.
    assert "BADGES" not in arg_src or "read_badges" in arg_src.lower(), (
        "startup reconcile must not pass the fixed Addr.BADGES to the reconciler")
