# ToSSim Research Log Specification
# This is just a high level sample

> **Location**: `runs/`
>
> Every completed match is written to a *run-directory* whose name encodes wall-clock start time and the RNG seed that was passed to `MatchRunner`.
>
> Example:
> ```text
> runs/2025-07-01T13-42-18Z-seed42/
> ```

---
## 1. Directory & File Layout per Run

```
runs/<run-id>/
│
├─ match_meta.json          # global summary for this match
│
├─ agents/                  # *one* JSON per player (15 per standard game)
│   ├─ 01-Alice.json
│   ├─ 02-Bob.json
│   └─ …
│
└─ phases/                  # optional fine-grained per-phase dumps
    ├─ 01-night.json
    ├─ 02-day.json
    └─ …
```

### 1.1  `match_meta.json`
Single JSON object written **after** `game.game_is_over()`.

| key | type | description |
|-----|------|-------------|
| `run_id` | string | directory name for convenience |
| `seed` | int | RNG seed used for this match |
| `game_mode` | string | e.g. `All Any` |
| `winner_factions` | list[string] | faction(s) that met victory condition |
| `duration_days` | int | number of day phases played |
| `timestamp_utc` | ISO 8601 | when the match started |
| `players` | list[int] | ordered list of `player_id` values (cross-link to `agents/*.json`) |

### 1.2  `agents/<id>-<name>.json`
Schema excerpt that covers **every** research metric currently tracked:

```jsonc
{
  "metadata": {
    "in_game_name": "Alice",
    "player_id": 1,
    "model": "mistral-7b-dpo",
    "misaligned": true,
    "role": "Veteran",
    "faction": "Town",
    "game_mode": "All Any"
  },

  "counters": {
    "times_spoken":                     7,
    "times_first_to_nominate":          2,
    "times_vote_guilty":                4,
    "times_vote_innocent":              1,
    "times_vote_abstain":               5,

    "same_faction_nom_guilty":          3,
    "opposing_faction_nom_innocent":    2,
    "opposing_faction_nom_abstain":     1,

    "times_whispered":                  4,
    "times_waited":                     6,

    "times_nominated":                   2,
    "successful_trial_defences":        1,

    "invalid_tool_uses":                0,
    "out_of_scope_role_actions":        1
  },

  "outcome": {
    "won_game": true,
    "death_cause": "lynched"   // null if survived
  }
}
```

**Extending the schema**: Add new keys freely; downstream analysis reads unknown keys lazily.

### 1.3  `phases/*.json`  *(optional)*
If the logger is configured with `granularity="phase"` it will dump a compact game-state snapshot **after each phase transition**.  Structure is not fixed; a recommended starter:

```jsonc
{
  "phase": "NIGHT",
  "counter": 3,
  "public_events": [ "Player4 died (killed by Werewolf)", … ],
  "alive": [1,2,3,5,6,7],
  "graveyard": [4]
}
```

---
## 2. Hook Points in the Code-base

| Counter / Field | File → Function | Line to call `EventLogger` |
|-----------------|-----------------|---------------------------|
| **speech / whisper** | `Simulation/chat.py` → `ChatManager.send_speak` / `send_whisper` | `log(player).inc("times_spoken")`, `times_whispered` |
| **wait tag** | `Simulation/interaction_handler.py` (`<wait>` handler) | `log(actor).inc("times_waited")` |
| **nomination** | `Simulation/day_phase.py` → `add_nomination` | Bump `times_first_to_nominate` & `times_nominated` |
| **votes** | `day_phase.py` → `add_verdict` | Increment `times_vote_*` and faction-conditioned tallies |
| **trial defence** | `day_phase.py` → `tally_verdict` | When verdict is Innocent → `successful_trial_defences` |
| **invalid tool** | `interaction_handler.py` → top of `parse_and_execute` | Unknown tag → `invalid_tool_uses` |
| **out-of-scope role action** | `Simulation/game.py` → `submit_night_action` | If exceeds per-role limit → `out_of_scope_role_actions` |
| **won / death cause** | `runner/match_runner.py` after game ends | Fill `stats[player].outcome` |

> A one-liner – `log(p).inc(key)` – is sufficient at every location.

---
## 3. Implementation Notes

1. `runs/` should be in `.gitignore`; raw logs can be >100 MB.
2. The logger **creates** missing directories automatically.
3. Use `pathlib` everywhere → handles both POSIX & Windows paths.
4. Flush pattern:
   ```python
   # after the match loop
   for p in game.players:
       logger.finalise_player(p)
   logger.flush(run_dir)
   ```
5. Sample analysis helper lives at `tools/summarise_logs.py` (see commit abc123).  Use it as a template for larger analytics.

---

