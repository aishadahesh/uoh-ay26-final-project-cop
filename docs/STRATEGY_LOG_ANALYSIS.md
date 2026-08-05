# Strategy Log Analysis and Anti-Loop Upgrade

## Evidence from the supplied games

The recorded state transitions were inspected directly rather than inferred
from hints. A reversal means returning to the position occupied two personal
moves earlier; an ABAB loop is the repeated position pattern `A -> B -> A -> B`.

| Log | Role | Moves | Unique cells | Reversals | ABAB loops |
|---|---:|---:|---:|---:|---:|
| `log_G001_g01.json` | Police | 16 | 14 | 3 | 2 |
| `log_G001_g01.json` | Thief | 17 | 7 | 9 | 7 |
| `log_G001_g02.json` | Police | 34 | 7 | 26 | 24 |
| `log_G001_g02.json` | Thief | 35 | 7 | 19 | 12 |

Game 2's dominant failure is visible after the opening: police repeatedly
switches between `(0,5)` and `(0,6)`, while the thief switches between `(6,5)`
and `(6,6)` or stays. Distance therefore alternates instead of converging.

## Root causes

1. The original policy optimized only one-step Manhattan distance to one belief
   peak. It had no obstacle-aware path cost, continuation value, or memory.
2. Equal-distance edge moves were resolved deterministically, so the same local
   choice was selected again after returning to an earlier state.
3. The Bayesian posterior multiplied old belief by scent repeatedly without a
   hidden-opponent transition step, allowing historical scent to over-anchor a
   stale peak.
4. Gemini previously received too little board/history context. In the older
   cop implementation, malformed or unavailable actions fell directly through
   to fallback without a corrective retry.
5. Fallback inherited the same one-step weakness, so it could legally continue
   the loop rather than recover from it.

## Implemented strategy

`TacticalPlanner` evaluates every move already declared legal by `Board`.
Its score uses breadth-first shortest-path distance around barriers, a weighted
set of the five strongest belief cells, two-ply continuation value, future
mobility, dead-end risk, visit frequency, repeated actions, immediate reversal,
STAY, and detected-loop penalties. Police minimizes expected path distance and
values continued pursuit. Thief values capture margin, future escape distance,
multiple exits, and open space.

The planner records the action actually executed, including a Gemini override.
It detects ABAB position/action patterns, repeated cells, and consecutive STAY.
When a loop is detected and alternatives exist, moves into the last two cells
and STAY are removed from Gemini's allowed action set. The best-scoring allowed
move is the deterministic fallback.

Gemini now receives the board size, blocked cells, own position, weighted belief
candidates, legal actions with destinations and planner scores, recent positions
and actions, loop warnings, role objective, and strict JSON schema. Output is
parsed, validated against the supplied allowed set, corrected with one repair
prompt, and validated again against live board state before execution.

## Rules compliance

The implementation follows `ProgressDoc.md`, `docs/tasks.md`, and
`ref/police_thief_p2p.pdf`:

- movement remains exactly one orthogonal cell or STAY;
- `Board.legal_moves` and `Board.apply_move` remain the authority;
- the policy never receives the opponent's true coordinate;
- opponent estimates come only from the local scent-derived belief map;
- no diagonal, invented, blocked, or off-board action can execute;
- the cop barrier policy uses only legal adjacent/current cells and spends a
  barrier only when it closes a genuine chokepoint.

## Controlled replay comparison

A same-start 7x7, no-barrier replay used the recorded `(0,0)` police and `(3,3)`
thief starts. Each policy was updated only from the opponent's scent field; true
positions were retained solely by the simulation observer for capture checking.

| Role | Moves | Unique cells | Reversals | ABAB loops |
|---|---:|---:|---:|---:|
| Improved police | 10 | 11 | 0 | 0 |
| Improved thief | 11 | 8 | 0 | 0 |

The improved run ended in capture at `(5,5)` after 10 police moves. This is not
a claim that every match must end identically; it is a regression comparison
showing that the supplied edge oscillation is no longer stable behavior.
