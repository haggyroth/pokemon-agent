"""Purchase policy for the Poké Mart — the "approved to buy" list with par levels
and badge-gated unlocks. Pure data + logic (no I/O), so it unit-tests without an
emulator. `compute_shopping_list` takes the current bag, badge count, and money and
returns what to restock, in priority order, capped by what you can afford.

The agent reads the bag/money from memory (memory_reader.read_bag/read_money) and
feeds them here; the deterministic `buy` skill (separate) executes the result.
"""
from dataclasses import dataclass

# Item ids (pokefirered constants/items.h) and display names — only the consumables
# the agent restocks. Balls, healing, status, escape.
ITEM_NAMES: dict[int, str] = {
    1: "Master Ball", 2: "Ultra Ball", 3: "Great Ball", 4: "Poké Ball",
    13: "Potion", 22: "Super Potion", 21: "Hyper Potion", 20: "Max Potion",
    19: "Full Restore",
    14: "Antidote", 18: "Paralyze Heal", 17: "Awakening", 15: "Burn Heal",
    16: "Ice Heal", 23: "Full Heal", 24: "Revive",
    86: "Repel", 83: "Super Repel", 84: "Max Repel", 85: "Escape Rope",
}

# Mart buy prices (¥), from pokefirered src/data/items.json.
ITEM_PRICES: dict[int, str] = {
    2: 1200, 3: 600, 4: 200,
    13: 300, 22: 700, 21: 1200,
    14: 100, 18: 200, 17: 250, 15: 250, 16: 250, 23: 600, 24: 1500,
    86: 350, 83: 500, 85: 550,
}


@dataclass(frozen=True)
class BuyRule:
    """Keep `par` of `item_id` in the bag, but only while your badge count is in
    [min_badges, max_badges). max_badges lets a better item SUPERSEDE a worse one
    (e.g. stop buying Potions once Super Potions unlock)."""
    item_id: int
    par: int
    min_badges: int = 0
    max_badges: int = 99


# Ordered by PRIORITY (most important first) — when money is tight, earlier rules
# are funded first. Badge windows implement the "upgrade as you progress" idea:
#   Balls: Poké → Great(≥3) → Ultra(≥5)
#   Heals: Potion → Super Potion(≥3, after Surge) → Hyper Potion(≥5)
#   Status: individual cheap cures early → Full Heal(≥4) supersedes them
BUY_POLICY: list[BuyRule] = [
    # Catching stock — always keep balls on hand.
    BuyRule(4,  10, min_badges=0, max_badges=3),   # Poké Ball
    BuyRule(3,  10, min_badges=3, max_badges=5),   # Great Ball
    BuyRule(2,  10, min_badges=5),                  # Ultra Ball
    # Main healing — par grows as fights get harder.
    BuyRule(13, 6,  min_badges=0, max_badges=3),   # Potion
    BuyRule(22, 8,  min_badges=3, max_badges=5),   # Super Potion
    BuyRule(21, 8,  min_badges=5),                  # Hyper Potion
    # Status: cheap single-status cures early; Full Heal covers everything later.
    BuyRule(23, 5,  min_badges=4),                  # Full Heal
    BuyRule(14, 2,  min_badges=0, max_badges=4),   # Antidote
    BuyRule(18, 2,  min_badges=0, max_badges=4),   # Paralyze Heal
    BuyRule(17, 2,  min_badges=0, max_badges=4),   # Awakening
    BuyRule(15, 1,  min_badges=0, max_badges=4),   # Burn Heal
    BuyRule(16, 1,  min_badges=0, max_badges=4),   # Ice Heal
    # Revival — worth carrying a couple once fights can spike-KO.
    BuyRule(24, 2,  min_badges=4),                  # Revive
]


def compute_shopping_list(bag: dict[int, int], badges: int, money: int,
                          reserve: int = 0) -> dict:
    """Given the current bag ({item_id: qty}), badge count, and money, return the
    restock plan. Buys up to each active rule's par, in priority order, spending no
    more than (money - reserve). Returns:
      {"lines": [{item_id, name, qty, unit_price, subtotal}, ...],
       "total": <¥>, "affordable": bool}
    An empty `lines` means nothing to buy (already stocked, or can't afford any)."""
    budget = max(0, money - reserve)
    lines = []
    total = 0
    fully_affordable = True
    for rule in BUY_POLICY:
        if not (rule.min_badges <= badges < rule.max_badges):
            continue
        price = ITEM_PRICES.get(rule.item_id)
        if not price:
            continue
        need = rule.par - bag.get(rule.item_id, 0)
        if need <= 0:
            continue
        affordable_qty = min(need, (budget - total) // price)
        if affordable_qty < need:
            fully_affordable = False
        if affordable_qty <= 0:
            continue
        subtotal = affordable_qty * price
        total += subtotal
        lines.append({
            "item_id": rule.item_id,
            "name": ITEM_NAMES.get(rule.item_id, f"item#{rule.item_id}"),
            "qty": affordable_qty,
            "unit_price": price,
            "subtotal": subtotal,
        })
    return {"lines": lines, "total": total, "affordable": fully_affordable}


def shopping_summary(bag: dict[int, int], badges: int, money: int) -> str:
    """One-line human/agent-readable restock recommendation, or '' if nothing to buy."""
    plan = compute_shopping_list(bag, badges, money)
    if not plan["lines"]:
        return ""
    parts = [f"{ln['qty']}× {ln['name']} (¥{ln['subtotal']})" for ln in plan["lines"]]
    return f"Restock (¥{plan['total']} of ¥{money}): " + ", ".join(parts)
