# Police-Thief P2P — Cop Agent (Distributed Cops-and-Robbers over a Peer-to-Peer Network)

Final project for the University of Haifa "Orchestration of AI Agents" course (AY26). Two autonomous agents — a **cop** and a **thief** — play a partial-information pursuit game over a decentralized peer-to-peer network, with no central server, no shared memory between sides, and a cryptographic commit-reveal protocol standing in for a referee.

> **This is the COP repo.** It implements and runs the cop side only, and is designed to work fully independently of the thief side — the only thing the two sides must agree on is the shared, byte-identical `config/game.json` (Sec. 3.2.2) and the wire protocol described below. Sibling (thief) repo: https://github.com/aishadahesh/uoh-ay26-final-project-thief

> **Status: practical overview.** This README describes the current state of the codebase and how to run it. The full academic report required for submission (Dec-POMDP model discussion, design-decision justification, learning curves, mandatory screenshots) is a separate, later pass — see `docs/TODO.md` Section O.6 / rule 42 for what's still outstanding there.

## Table of contents

- [What's built](#whats-built)
- [The cop's strategy](#the-cops-strategy)
- [Installation instructions](#installation-instructions)
- [Usage instructions](#usage-instructions)
- [Configuration guide](#configuration-guide)
- [Testing & quality gates](#testing--quality-gates)
- [Project layout](#project-layout)
- [Contribution guidelines](#contribution-guidelines)
- [License & credits](#license--credits)
- [What's genuinely still outstanding](#whats-genuinely-still-outstanding)

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

After Chapter 11, four more things were added, each prompted by direct user requests:
- **A richer GUI** (`gui/board_canvas.py`): agent markers, a visited-cell trail, and a Replay Viewer that now actually renders the board with Play/Pause and jump-to-step — inspired by, but not copied from, the course's reference example repo.
- **Real Gmail OAuth** (`services/gmail_oauth.py`): a working `send`-scope-only OAuth transport, ported from a proven pattern in a separate prior project and plugged directly into the existing reporting pipeline.
- **Interactive Play Mode** (`domain/interactive_match.py`, `gui/play_app.py`, `gui/mode_select.py`): a mode-select screen offering Human vs Human, Human vs Gemini, Agent vs Agent (same process), and Agent vs Agent across two computers over the real MCP network — with click-to-move and a move-pad on a shared board, not just a text log.
- **The four-tool reference wire protocol** (`services/network_protocol.py`, `mcp_server.py`, `mcp_client.py`): `negotiate` / `receive_turn` / `submit_audit` / `receive_control`, replacing an earlier placeholder single-tool design, so this cop's server interoperates with any peer built against the same course rulebook (see `docs/PRD_fastmcp_networking.md`).

Most recently, this session **wired the cop's barrier-placement mechanic into the live two-computer match loop** (it previously existed only as a tested-in-isolation `Board`/`ManhattanHeuristicBrain` capability, never actually exercised during a real match) — see [The cop's strategy](#the-cops-strategy) below, and `tests/integration/test_network_match.py::test_two_peers_synchronize_barriers_and_resolve_a_boxed_in_capture` for an end-to-end proof of a genuine barrier-driven capture.

Every chapter's design rationale, constraints, and test evidence lives in its own `docs/PRD_<mechanism>.md`. The full chapter-by-chapter build log — what was implemented, what broke and how it was fixed, what was deliberately deferred and why — is in **`ProgressDoc.md`**.

## The cop's strategy

The cop's decision-making lives in `domain/strategy/manhattan_brain.py::ManhattanHeuristicBrain(role=AgentRole.COP)` — one of three algorithmically-equal tracks the rulebook allows (heuristic / custom / optional RL); per `docs/PLAN.md` ADR-010, this project's chosen baseline is the Manhattan-distance heuristic combined with a Bayesian belief map (`domain/belief.py`). RL is explicitly out of scope (`docs/PRD_strategy_module.md` §3: "the course does not require RL at all").

The cop never sees the thief's true position. Every decision is made from its own local belief:

1. **Chase the belief peak, not the truth.** Each turn, `BeliefMap.arg_max()` returns the board cell the cop currently believes is most likely to hold the thief — a posterior built only from the thief's own scent trail (`domain/scent.py`), updated Bayesian-style and renormalized after every observation. `_decide_move` then picks the orthogonal move (`greedy_manhattan_move`) that most reduces the Manhattan distance to that believed peak.
2. **Barrier the cell closest to the belief peak — the cop's "spatial-engineering" advantage (Sec. 3.3.3/3.3.8).** After moving, `_pick_move` looks at the cop's own (post-move) neighbors, excludes any that are already blocked, and permanently barricades whichever remaining neighbor is closest to the believed peak — one barrier per turn, budget permitting (`max_barriers`, default 14). This progressively narrows the thief's viable path space rather than relying on movement alone.
3. **Declare every barrier live, in the clear.** Per Sec. 3.3.6, a barrier placement — unlike a move — is never sealed inside the commit-reveal envelope. `services/network_match.py` broadcasts it immediately as a plaintext field on that turn's `TurnMessage`, and the opponent applies it to its own board the same turn (`Board.apply_declared_barrier`), so both sides' local board state stays in sync in real time without waiting for the end-of-match reveal.
4. **Two ways to win.** A cop wins either by moving onto the thief's true cell (a direct capture claim) or by barricading the thief into a corner with zero legal moves left (`domain/capture.py::is_boxed_in`, Sec. 3.3.5) — both resolve identically through the same `MatchOutcome.CAPTURE` path, verified independently by both peers via the end-of-match mutual audit before either side commits to reporting the result.

**A real, empirically-found bug and its fix** (documented here rather than hidden, per this project's own testing discipline): the first version of `_pick_move` didn't exclude already-blocked neighbors from consideration, so once the closest candidate cell was blocked, the heuristic kept re-targeting *that same cell* every subsequent turn — spending the entire barrier budget on placements `Board.place_barrier` should have rejected as redundant. Found by hand-driving a real two-peer match with `MemoryTransport` before writing any formal assertions, and fixed in three places: `_pick_move` now filters out blocked neighbors, `Board.place_barrier` defensively rejects an already-blocked target, and `Board.apply_declared_barrier` (the receiving peer's own board-sync path) is now idempotent against a redundant re-declaration.

**Known, honestly-documented limitation:** the barrier-targeting heuristic is a single-step greedy choice ("whichever open neighbor is closest to the belief peak"), not a multi-turn cornering plan. From some starting-position combinations it reliably produces a genuine boxed-in capture well before `max_moves`; from others, the thief's belief-driven flight simply outpaces a purely local, one-cell-at-a-time barrier strategy, and the match resolves to survival instead. This is a heuristic-quality ceiling, not a wiring bug — the underlying win-detection and cross-peer synchronization are proven correct by the integration test referenced above; a deeper multi-turn "flanking" strategy (`docs/TODO.md` T0253/T0256) is a natural future refinement, not built here.

An optional Gemini-backed tactical advisor (`services/gemini_agent.py::GeminiAgentAdvisor`) can additionally narrate/select among the moves the deterministic rules engine already approves, in the local `play` GUI only — it never controls barrier placement, always falls back to the deterministic heuristic on invalid output or an API failure, and is architecturally prevented from ever making the actual move decision (`BrainBase` never accepts an LLM handle or hint text) per Sec. 6.4.1.

## Installation instructions

Requires Python 3.12+ and [`uv`](https://docs.astral.sh/uv/) (this project uses `uv` exclusively — never `pip`/`venv` directly, per the course's software-quality guidelines).

```bash
git clone https://github.com/aishadahesh/uoh-ay26-final-project-cop.git
cd uoh-ay26-final-project-cop
uv sync                    # install dependencies
uv sync --extra email      # optional: adds the real Gmail OAuth transport
```

To enable the optional Gemini-powered advisor, copy `.env-example` to `.env` and set your own key:

```env
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.6-flash
```

Nothing else needs installing to run a local match, the GUI, or the two-process networked match over `localhost`.

## Usage instructions

**See the belief-map GUI live** (no networking, just the scent/belief mechanics driving a chase):

```bash
uv run python -m police_thief demo
```

**Run a full local match** (single process, placeholder policies, prints the result):

```bash
uv run python -m police_thief simulate
```

**Play interactively, with the mode-select launcher:**

```bash
uv run python -m police_thief play
```

This opens a mode-select screen offering:
- **Human vs Human** — fully offline, click-to-move or the move-pad on a shared board.
- **Human vs Gemini** — Gemini selects among the moves already approved by the deterministic rules engine; its tactical rationale appears in the sidebar. Invalid model output or an API failure safely falls back to the Manhattan heuristic.
- **Agent vs Agent (same process)** — both roles run the shipped heuristic locally, useful for quickly observing the cop's strategy end to end.
- **Agent vs Agent (Two Computers)** — a real networked match over MCP; see below.

### Agent vs Agent on two computers (MCP)

Choose **Agent vs Agent (Two Computers)** from the same `play` launcher on both computers, and run an ngrok or Localtonet HTTP tunnel to the local port shown in the setup screen on each. This repo's setup screen locks **This computer's role** to `cop` — it has no thief config to run as the thief with; the other computer runs the sibling thief repo's own `play` launcher, whose equivalent screen is locked to `thief`.

The launcher pre-fills every other field from `config/network_match.json`. Edit that file before launching to set your own tunnel URL, game ID, both teams and members, four repository URLs, output directory, and email defaults. Do not put Gemini keys or Gmail OAuth tokens in this file; those remain in `.env`, `credentials.json`, and `token.json`.

- Put the **other computer's public URL** in **Opponent public URL**. It must include the FastMCP route, for example `https://abc123.ngrok.app/mcp`.
- Put your own tunnel address in **This peer's public tunnel URL** and give it to the opponent.
- Use the same game ID, sub-game number, shared `config/game.json`, and shared match secret on both computers.
- Enter Team 1 and Team 2 names, both individual member fields for each team, plus all four repository URLs; they are recorded in the final result schema.

For the lower-level `serve` command, the same opponent address belongs in `[network].opponent_url` inside the private role file `config/cop/game.toml`; never put it in the shared `config/game.json`.

Both peers act as MCP server and client simultaneously, over the four-tool reference protocol (`negotiate` / `receive_turn` / `submit_audit` / `receive_control` — see `docs/PRD_fastmcp_networking.md`). Every move is commit-verified; every barrier placement is publicly declared in real time. The final score and log hash are authenticated and compared on both computers before `mutual_sign_off` becomes `true`. Each peer writes:

```text
declaration_<game_id>.json
config_<game_id>_g<NN>.json
log_<game_id>_g<NN>.json
result_<game_id>.json
```

Enable **Automatically email result JSON** to send the final JSON-only report. The assignment address `rmisegal+uoh26finalgame@gmail.com` is pre-filled, but the recipient field can be changed before starting. Install the email extra first, place Google OAuth `credentials.json` in the project root, and complete browser consent once; its reusable token is stored as `token.json`. Email is sent only after both computers agree on the result.

**Run this side as a real, standalone FastMCP peer process** (`localhost` only, no tunnel needed) — always the cop, reading only `config/cop/game.toml`:

```bash
uv run python -m police_thief serve
```

This repository ships no thief config, no thief private per-peer settings, and no way to run this process as the thief — `serve` always starts a cop server. Run the sibling thief repo's own `serve` in a second terminal (or on a second computer, per the tunneled setup above) to get the opposing peer.

**Replay a saved, cryptographically-sealed match log:**

```bash
uv run python -m police_thief replay --log-file path/to/log.json
```

The Replay Viewer independently recomputes every step's commit hash from the revealed nonce and flags `TAMPERED` in red the instant a saved log has been altered — it trusts nothing it wasn't shown proof of.

## Configuration guide

Two distinct configuration layers, deliberately kept separate (`docs/tasks.md` Chapter 2, "Total Separation of Working Environments"):

- **`config/game.json`** — the shared, signed match config. Both sides load a byte-identical copy (`config_fingerprint`, checked at negotiation time); nothing in here may be team-specific. Sections: `board_and_agents` (grid size, start positions), `movement_and_barriers` (`max_barriers`, `max_moves`, `survival_threshold`), `scoring`, `pheromones` (scent decay/emission, fixed — not team-negotiable), `world`, `network_and_league` (fixed league parameters, e.g. `num_games`), `rate_limiter_gatekeeper` (minimum floors, may be raised but never lowered). `shared/game_config.py::load_match_parameters` validates every field against the rulebook's Mandatory Parameters Table and raises `GameConfigError` on any violation — including a below-floor `grid_size`/`max_barriers`, an unsupported `schema_version`, or `thief_start`/`cop_start` that are identical or out of bounds.
- **`config/cop/game.toml`** — private, per-peer settings never shared with or read by the thief process: `[network]` (`my_port`, `opponent_url`, `turn_timeout_seconds`), an optional `[strategy] cop_class` dotted path to swap in a different `BrainBase` subclass (defaults to `ManhattanHeuristicBrain`), an optional `[trash_talk] provider` (only `template`, zero-token, is implemented today), and an optional `[email]` section for Gmail reporting.
- **`config/network_match.json`** — pre-fills the two-computer GUI launcher's fields (team names, members, repo URLs, output directory, email defaults) so they don't need retyping every session; never put secrets here.
- **`.env`** — `GEMINI_API_KEY`/`GEMINI_MODEL` for the optional advisor; never committed (`.gitignore`).
- **`credentials.json` / `token.json`** — real Gmail OAuth artifacts; never committed.

`group_name`/`group_id` in `config/cop/game.toml` are still the placeholder `"TBD"` — see [What's genuinely still outstanding](#whats-genuinely-still-outstanding).

## Testing & quality gates

```bash
uv run pytest --cov     # 447 tests, 85%+ coverage required (pyproject.toml)
uv run ruff check .     # zero violations required
```

Tests favor real behavior over mocks wherever feasible: real local FastMCP HTTP servers in background threads, real Tkinter widgets, real file round-trips, real `google-api-python-client` objects against hand-built fake services, and real two-peer network matches (in-memory transport, real threads, real commit-reveal sealing) rather than a single mocked side. The one consistent, honest exception is the true external boundary — a real Gmail send, a real OAuth browser consent, a real `ngrok` tunnel — which cannot happen inside an automated session and is documented as a manual step wherever it applies.

## Project layout

```
src/police_thief/
  domain/       # pure game logic: board, scent, belief, replay, league, strategy
  services/     # crypto, networking, reliability layer, Gmail/Gatekeeper
  gui/          # Tkinter Live GUI + Replay Viewer + interactive Play mode
  shared/       # config loading, constants, versioning
  main.py       # CLI: serve / simulate / demo / play / replay
config/
  game.json           # shared, signed match config (both sides must load byte-identical)
  cop/                # private per-role config (network port, strategy class, etc.)
  network_match.json  # GUI launcher field defaults for two-computer matches
docs/
  tasks.md            # full rulebook extraction (single source of truth for requirements)
  PRD.md, PLAN.md      # master design documents
  PRD_<mechanism>.md   # one focused design doc per subsystem
  TODO.md              # ~900 granular tasks, honestly checked off chapter by chapter
tests/
  unit/, integration/
ref/
  police_thief_p2p.pdf                 # the course's project rulebook (source of `docs/tasks.md`)
  software_submission_guidelines-V3.pdf  # the course's software-quality submission guidelines
ProgressDoc.md    # the chapter-by-chapter development log
LICENSE           # educational-use license (see below)
```

## Contribution guidelines

This is a single-author academic submission for the cop side of the project (the thief side is deliberately a separate, independently-maintained repository — see the link at the top of this file). There is no external contribution workflow to describe beyond the practices actually followed while building it:

- **Branching:** feature work happens on short-lived branches off `main`; `main` is kept in a runnable, test-passing state.
- **Commits:** small, behavior-scoped commits with messages describing *why* a change was made, not just what changed; every commit reflects the actual author, never a fabricated co-author to simulate collaboration that didn't happen.
- **Before every commit:** `uv run pytest --cov` and `uv run ruff check .` must both pass — the same two commands in [Testing & quality gates](#testing--quality-gates) above.
- **Code style:** no code duplication beyond a 50/50 similarity threshold before extracting a shared helper (`docs/tasks.md` §3.2); pure functions in `domain/`, I/O and networking isolated to `services/`; a new module always ships with its own test module (TDD: red → green → refactor).
- **Docs stay in sync with code:** every mechanism has a matching `docs/PRD_<mechanism>.md`, and `docs/TODO.md`/`ProgressDoc.md` are updated in the same pass as the code that resolves an item — including honestly documenting *why* an item stays unchecked, rather than silently leaving it stale.

If you are a future student reusing parts of this repository for your own coursework, see [License & credits](#license--credits) below for the terms.

## License & credits

This repository is released under an **educational-use license** — see [`LICENSE`](LICENSE) for the full terms. In short: reuse and adaptation for your own coursework is welcome and consistent with the course's own reuse terms for its reference example repo (`docs/tasks.md` Appendix D, Sec. 15.5.1), but this repository is a learning artifact, not a submission template, and any reused portion should retain attribution.

Credits:
- Course rulebook, Mandatory Parameters Table, and the four-tool reference wire protocol: the "Orchestration of AI Agents" course staff, University of Haifa (`ref/police_thief_p2p.pdf`).
- Software-quality guidelines this repository follows (`uv`-only tooling, Ruff linting, 85% coverage floor, TDD workflow, mandatory README sections): `ref/software_submission_guidelines-V3.pdf`, Dr. Yoram Segal.
- GUI interaction model (shared board, click-to-move): inspired by, but not copied from, a course reference example repository shared with all students.
- Gmail OAuth transport pattern: adapted from the author's own prior, separate project for the same course track.

## What's genuinely still outstanding

Tracked in detail in `docs/TODO.md` and `ProgressDoc.md`'s Chapter 11 entry — the short version:

- The full academic report in this README (Rule 42) — the next planned pass.
- A real Google Cloud OAuth consent flow (the code is ready; someone needs to create the project and run it once).
- A real `ngrok`/tunnel session for cross-machine play.
- Actual league matches against other teams' agents.
- A real 8-character team identity code (currently placeholder `"TBD"` in `config/cop/game.toml`).
- A deeper, multi-turn barrier-cornering strategy — the current one-step-greedy heuristic reliably produces a barrier-driven capture from favorable starting positions (proven in `tests/integration/test_network_match.py`), but not from every possible start.
- One open rulebook-interpretation question found during the Chapter 11 sanity sweep (rule 47 — see `docs/TODO.md`).
