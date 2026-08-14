# Cop replay evidence

This directory contains the two representative examples used by the root academic report. Each animation is stored beside the signed source log from which it was generated. The copies are immutable documentation evidence; active match output remains under `results/` and is not committed as part of this documentation change.

| Example | Role outcome | Signed source | Rendered view |
|---|---|---|---|
| G002 sub-game 3 | Cop win by capture after 15 steps | `cop-win-G002-g03.json` | `cop-win-G002-g03.gif` |
| G009 sub-game 1 | Cop loss by Thief survival after 35 steps | `cop-loss-G009-g01.json` | `cop-loss-G009-g01.gif` |

Regenerate either animation from the repository root:

```powershell
uv run python scripts/visualize_game_log.py `
  --input assets/replays/cop-win-G002-g03.json `
  --output assets/replays/cop-win-G002-g03.gif

uv run python scripts/visualize_game_log.py `
  --input assets/replays/cop-loss-G009-g01.json `
  --output assets/replays/cop-loss-G009-g01.gif
```

The JSON is authoritative. The GIF is a reviewer-friendly visualization produced by the same replay parser and commitment checks.
