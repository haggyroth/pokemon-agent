# Live tests

Replay real bugs against the **real ROM** through the in-process libmgba binding. They are skipped when
the binding, ROM or fixtures are missing, so CI (no ROM) simply skips them.

```bash
python -m pytest tests/live -v          # needs: built binding, ROM, fixtures in saves/live/
```

## Fixtures (`saves/live/`, gitignored — ROM-derived)
| file | what it is |
|---|---|
| `work.sav` | battery save the runtime boots from (Pallet/Viridian, Bulbasaur L8) |
| `threemon.ss1` | Viridian City, party Bulbasaur L8 / Pikachu L5 / Caterpie L5 |
| `disabled.ss1` | mid-battle, the lead's Tackle is Disabled (found via `gDisableStructs` 0x02023E0C) |
| `post_misty.ss1` | Route 24 (north of Cerulean), Misty beaten, Ivysaur L26, no SS Ticket yet |
| `forced.ss1` | mid-battle, the active mon fainted → forced party screen |

Point `LIVE_DIR` elsewhere to use another folder; `ROM_PATH` for the ROM.

## Staging tricks (see `harness.py`)
- `patch_mon(slot, moves, pps, level, exp)` rewrites the encrypted party struct (+ checksum). Keep **exp
  consistent with level** or the game freezes on the "gained EXP" text.
- Heal HP by writing `max_hp` into the current-HP word of each party struct (`heal_hp`).
- `wild_battle()` wanders on grass until an encounter starts; `set_foe_hp()` writes gBattleMons[1].
- To make a fixture: reach the state with a script, then `m.save_state_file("saves/live/<name>.ss1")`.
