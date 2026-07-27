# Police-Thief P2P — Distributed Cops-and-Robbers over a Peer-to-Peer Network

Final project for the University of Haifa "Orchestration of AI Agents" course (AY26). Two autonomous agents — a **cop** and a **thief** — play a partial-information pursuit game over a decentralized peer-to-peer network, with no central server, no shared memory between sides, and a cryptographic commit-reveal protocol standing in for a referee.

> **Status: practical overview.** This README describes the current state of the codebase and how to run it. The full academic report required for submission (Dec-POMDP model discussion, design-decision justification, learning curves, mandatory screenshots) is a separate, later pass — see `docs/TODO.md` Section O.6 / rule 42 for what's still outstanding there.

## What's built

The project follows `docs/tasks.md` (the full rulebook extraction) chapter by chapter. All 11 numbered chapters are implemented, tested, and documented:

| Chapter | What it built |
|---|---|
| 1 | Dec-POMDP formal model (`domain/dec_pomdp.py`) |
| 2 | P2P networking over FastMCP — every peer is simultaneously server and client (`services/mcp_server.py`, `mcp_client.py`) |
| 3 | Board physics: movement, barriers, capture, scoring (`domain/board.py`, `capture.py`, `scoring.py`) |
| 4 | Pheromone scent trails — mandatory emission/decay formula (`domain/scent.py`) |
| 5 | Commit-reveal cryptographic protocol (SHA-256) + Step-0 hardware fairness declaration (`services/commit_reveal.py`, `step0.py`) |
| 6 | Strategy module: Bayesian belief map + Manhattan-heuristic brain + natural-language hints/bluff detection (`domain/belief.py`, `strategy/`, `hints.py`) |
| 7 | Live GUI (local-truth-only) + Replay Viewer with cryptographic verification (`domain/live_view_model.py`, `replay.py`, `gui/`) |
| 8 | Reliability layer: legal state machine, Deadline Tracker, Watchdog, Orchestrator (`services/state_machine.py`, `deadline_tracker.py`, `watchdog.py`, `orchestrator.py`) |
| 9 | League scoring, Gatekeeper (rate limiter + quota + anomaly detector), Gmail JSON reporting (`domain/league.py`, `services/gatekeeper.py`, `match_reports.py`, `gmail_report_sender.py`) |
| 10 | Milestone reconciliation against the rulebook's own recommended build order |
| 11 | Full 55-mandatory-rule compliance sweep |

Two things were added after Chapter 11, prompted by direct user requests:
- **A richer GUI** (`gui/board_canvas.py`): agent markers, a visited-cell trail, and a Replay Viewer that now actually renders the board with Play/Pause and jump-to-step — inspired by, but not copied from, the course's reference example repo.
- **Real Gmail OAuth** (`services/gmail_oauth.py`): a working `send`-scope-only OAuth transport, ported from a proven pattern in a separate prior project and plugged directly into the existing reporting pipeline.

Every chapter's design rationale, constraints, and test evidence lives in its own `docs/PRD_<mechanism>.md`. The full chapter-by-chapter build log — what was implemented, what broke and how it was fixed, what was deliberately deferred and why — is in **`ProgressDoc.md`**.

## Quick start

```bash
uv sync                    # install dependencies
uv sync --extra email      # add if you want the real Gmail OAuth transport (optional)
```

**See the belief-map GUI live** (no networking, just the scent/belief mechanics driving a chase):

```bash
uv run python -m police_thief demo
```

**Run a full local match** (single process, placeholder policies, prints the result):

```bash
uv run python -m police_thief simulate
```

**Play locally with Gemini-powered agents:**

Copy `.env-example` to `.env`, set your Google AI Studio key, and launch the
interactive command center:

```env
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.6-flash
```

```bash
uv run python -m police_thief play
```

Gemini selects among the moves already approved by the deterministic rules
engine and its tactical rationale appears in the sidebar. Invalid model output
or an API failure safely falls back to the Manhattan heuristic. Human vs Human
remains fully offline.

### Agent vs Agent on two computers (MCP)

Choose **Agent vs Agent (Two Computers)** from the same `play` launcher on
both computers. Each side selects a different role (`cop` / `thief`) and runs
an ngrok or Localtonet HTTP tunnel to the local port shown in the setup screen.

The launcher pre-fills every field from `config/network_match.json`. Edit that
file before launching to set the peer role and URLs, game ID, both teams and
members, four repository URLs, output directory, and email defaults. Do not
put Gemini keys or Gmail OAuth tokens in this file; those remain in `.env`,
`credentials.json`, and `token.json`.

- Put the **other computer's public URL** in **Opponent public URL**. It must
  include the FastMCP route, for example `https://abc123.ngrok.app/mcp`.
- Put your own tunnel address in **This peer's public tunnel URL** and give it
  to the opponent.
- Use the same game ID, sub-game number, shared `config/game.json`, and shared
  match secret on both computers.
- Enter Team 1 and Team 2 names, both individual member fields for each team,
  plus all four repository URLs;
  they are recorded in the final result schema.

For the lower-level `serve` command, the same opponent address belongs in
`[network].opponent_url` inside the private role file
`config/cop/game.toml` or `config/thief/game.toml`; never put it in the shared
`config/game.json`.

Both peers act as MCP server and client simultaneously. Every move is
commit-verified. The final score and log hash are authenticated and compared
on both computers before `mutual_sign_off` becomes `true`. Each peer writes:

```text
declaration_<game_id>.json
config_<game_id>_g<NN>.json
log_<game_id>_g<NN>.json
result_<game_id>.json
```

Enable **Automatically email result JSON** to send the final JSON-only report.
The assignment address `rmisegal+uoh26finalgame@gmail.com` is pre-filled, but
the recipient field can be changed before starting. Install the email extra first, place
Google OAuth `credentials.json` in the project root, and complete browser
consent once; its reusable token is stored as `token.json`. Email is sent only
after both computers agree on the result.

**Run two real, separate peer processes talking over FastMCP** (two terminals):

```bash
uv run python -m police_thief serve --role cop
uv run python -m police_thief serve --role thief
```

Each loads only its own `config/cop/game.toml` or `config/thief/game.toml` — never the other's.

**Replay a saved, cryptographically-sealed match log:**

```bash
uv run python -m police_thief replay --log-file path/to/log.json
```

## Testing & quality gates

```bash
uv run pytest --cov     # 380 tests, 99%+ coverage (85% required, pyproject.toml)
uv run ruff check .     # zero violations required
```

Tests favor real behavior over mocks wherever feasible: real local FastMCP HTTP servers in background threads, real Tkinter widgets, real file round-trips, real `google-api-python-client` objects against hand-built fake services. The one consistent, honest exception is the true external boundary — a real Gmail send, a real OAuth browser consent, a real `ngrok` tunnel — which cannot happen inside an automated session and is documented as a manual step wherever it applies.

## Project layout

```
src/police_thief/
  domain/       # pure game logic: board, scent, belief, replay, league, strategy
  services/     # crypto, networking, reliability layer, Gmail/Gatekeeper
  gui/          # Tkinter Live GUI + Replay Viewer
  shared/       # config loading, constants, versioning
  main.py       # CLI: serve / simulate / demo / replay
config/
  game.json           # shared, signed match config (both sides must load byte-identical)
  cop/, thief/         # private per-role config (network port, strategy class, etc.)
docs/
  tasks.md            # full rulebook extraction (single source of truth for requirements)
  PRD.md, PLAN.md      # master design documents
  PRD_<mechanism>.md   # one focused design doc per subsystem
  TODO.md              # ~900 granular tasks, honestly checked off chapter by chapter
tests/
  unit/, integration/
ProgressDoc.md    # the chapter-by-chapter development log
```

## What's genuinely still outstanding

Tracked in detail in `docs/TODO.md` and `ProgressDoc.md`'s Chapter 11 entry — the short version:

- The full academic report in this README (Rule 42) — the next planned pass.
- A real Google Cloud OAuth consent flow (the code is ready; someone needs to create the project and run it once).
- A real `ngrok`/tunnel session for cross-machine play.
- Actual league matches against other teams' agents.
- A real 8-character team identity code (currently placeholder `"TBD"` in both `config/*/game.toml`).
- One open rulebook-interpretation question found during the Chapter 11 sanity sweep (rule 47 — see `docs/TODO.md`).
