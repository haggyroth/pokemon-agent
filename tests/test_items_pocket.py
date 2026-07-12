"""read_items_pocket: the ordered/decrypted Items-pocket list that use_item navigates
by. Pure logic with a fake memory client — pins the slot order, the XOR quantity
decrypt, and empty-slot skipping (an offset/key regression would silently misselect
items in battle)."""
from game.constants import Addr
from game.memory_reader import LeafGreenReader

SB1 = 0x02030000
SB2 = 0x02031000
KEY = 0x9ABCDEF1


class _FakeClient:
    """Serves a fixed SaveBlock1/2, an encryption key, and the Items pocket bytes.
    Item slots are 4 bytes: id (u16 LE) then quantity ^ (key & 0xFFFF) (u16 LE)."""
    def __init__(self, items):
        self.k16 = KEY & 0xFFFF
        self.items_raw = bytearray()
        for iid, qty in items:
            self.items_raw += bytes([iid & 0xFF, (iid >> 8) & 0xFF])
            enc = qty ^ self.k16
            self.items_raw += bytes([enc & 0xFF, (enc >> 8) & 0xFF])
        # pad to the full pocket size with empty (id 0) slots
        self.items_raw += bytes(4 * Addr.ITEMS_SLOTS - len(self.items_raw))

    def read32(self, addr):
        if addr == Addr.SAVEBLOCK1_PTR:
            return SB1
        if addr == Addr.SAVEBLOCK2_PTR:
            return SB2
        if addr == SB2 + Addr.ENCRYPTION_KEY_OFFSET:
            return KEY
        return 0

    def read_range(self, addr, length):
        if addr == SB1 + Addr.ITEMS_OFFSET:
            return bytes(self.items_raw[:length])
        return bytes(length)


def _reader(items):
    r = LeafGreenReader.__new__(LeafGreenReader)
    r.client = _FakeClient(items)
    return r


def test_orders_items_as_stored_and_decrypts_quantities():
    # Potion x2 then Antidote x1 — order preserved, quantities decrypted.
    assert _reader([(13, 2), (14, 1)]).read_items_pocket() == [(13, 2), (14, 1)]


def test_skips_empty_slots():
    # An empty (id 0) slot between items must not appear or shift the order.
    r = _reader([(13, 5), (0, 0), (22, 3)])
    assert r.read_items_pocket() == [(13, 5), (22, 3)]


def test_empty_pocket():
    assert _reader([]).read_items_pocket() == []


def test_index_matches_use_item_navigation():
    # use_item picks target_index = position in this list; a non-top item is at 1.
    order = [i for i, _ in _reader([(13, 1), (14, 1), (22, 1)]).read_items_pocket()]
    assert order.index(14) == 1 and order.index(22) == 2
