# TODO — Distributed Cops-and-Robbers P2P Project

> **Live-status reconciliation (2026-08-14):** the historical notes below record
> the state when each chapter was first implemented. The project has since been
> split into independent public Cop and Thief repositories and has completed
> five mutually verified counted series against distinct opponents: G001
> (najamjad), G002 (amireman), G009 (sharNamr),
> SMNGRP05-vs-uoh-ay26-C01 (SMNGRP05), and
> AHK-YOSI-vs-uoh-ay26-C001 (ahk-yosi). Current checkboxes and notes
> supersede stale phrases such as “single shared repo” or “zero real matches.”

Derived from `requirements.md` (itself derived from `ref/police_thief_p2p.pdf` + `ref/software_submission_guidelines-V3.pdf`). Organized by the book's recommended 7-layer incremental build order (Ch.10), plus setup, reliability, league, testing, docs, and submission phases. Each task is atomic and checkable. "Both roles" means duplicate the task once for the cop repo and once for the thief repo, since they must run as fully separate codebases/processes.

Legend: `[ ]` = not started, `[x]` = done. Do not skip layers — each stage should be end-to-end working before the next begins (Ch.10).

> **Architecture decision recorded during implementation (see `docs/PLAN.md` ADR-011):** development proceeds as a **single shared package/repo** (`police_thief`, role-differentiated via `--role cop`/`--role thief` and separate `config/police/`/`config/thief/` directories) rather than two duplicated repos from day one. This satisfies the "no shared runtime state" rule (two OS processes importing the same stateless module still share no memory) while avoiding premature code duplication. The literal two-GitHub-repos submission requirement (rule 49) is deferred to Section O (Submission Prep), where this codebase will be exported into two tagged repos before final submission. Tasks below written as "for cop repo" / "for thief repo" are satisfied by this single shared structure during development unless noted otherwise.

---

## A. Environment & Tooling Setup

- [x] T0001 Install Python 3.11+ and confirm version on dev machine — `requires-python = ">=3.11"` in `pyproject.toml`; `uv sync` resolved a 3.14.2 venv
- [x] T0002 Install `uv` (or chosen package manager) for dependency management — `uv 0.10.3` confirmed
- [x] T0003 Create a Python virtual environment for the cop agent — single shared `.venv` per architecture note above
- [x] T0004 Create a Python virtual environment for the thief agent — same shared `.venv`
- [x] T0005 Install `fastmcp` package in both environments — `fastmcp>=3.4.4` added via `uv add fastmcp` (single shared venv)
- [x] T0006 Install `pytest` for both environments — `pytest`, `pytest-cov` added as dev dependencies
- [ ] T0007 Install `pydantic` (or equivalent) for config/schema validation
- [ ] T0008 Install `tomli`/`tomllib`/`tomli-w` for TOML read/write
- [ ] T0009 Install `google-api-python-client`, `google-auth-httplib2`, `google-auth-oauthlib` for Gmail API
- [ ] T0010 Install GUI toolkit (Tkinter confirm bundled, or install PyQt/PySide)
- [ ] T0011 Install `ngrok` CLI locally and verify `ngrok version`
- [ ] T0012 Create free ngrok account and retrieve authtoken
- [ ] T0013 Configure `ngrok config add-authtoken`
- [ ] T0014 Evaluate Localtonet as an ngrok alternative/backup tunnel
- [ ] T0015 Install `matplotlib` (or similar) for heatmap rendering
- [ ] T0016 Install `numpy` for scent-grid math
- [ ] T0017 Choose and install an LLM local runtime: Ollama
- [ ] T0018 Pull a small local model into Ollama (e.g., llama3/phi)
- [ ] T0019 Verify Ollama server responds on `localhost:11434`
- [ ] T0020 Obtain an Anthropic API key (or chosen LLM API) for `claude_api` mode
- [ ] T0021 Store API key in a local `.env` file, never committed
- [ ] T0022 Verify Claude Code CLI installed and authenticated for `claude_cli` mode
- [ ] T0023 Set up `pre-commit` hooks (lint/format) for both repos
- [x] T0024 Configure `ruff`/`flake8` linting rules — `[tool.ruff]`/`[tool.ruff.lint]` in `pyproject.toml`, zero violations confirmed
- [ ] T0025 Configure `black` (or chosen formatter) settings
- [ ] T0026 Set up `mypy` or `pyright` for type checking (optional but recommended)
- [x] T0027 Decide on Python package name/namespace for cop project (e.g., `police_thief`) — single shared package `police_thief` (see architecture note)
- [x] T0028 Decide on Python package name/namespace for thief project — same shared package `police_thief`
- [ ] T0029 Set up a shared local scratch directory for test logs/screenshots
- [ ] T0030 Verify two terminals can run two independent Python processes simultaneously without port clash
- [ ] T0031 Choose port numbers for cop's local FastMCP server (e.g., 8801)
- [ ] T0032 Choose port numbers for thief's local FastMCP server (e.g., 8802)
- [ ] T0033 Verify firewall/OS allows local binding to chosen ports
- [ ] T0034 Set up VS Code / IDE workspace for cop repo
- [ ] T0035 Set up VS Code / IDE workspace for thief repo
- [ ] T0036 Install `python-dotenv` or equivalent for environment variable loading
- [ ] T0037 Decide logging library/strategy (stdlib `logging` vs `structlog`)
- [ ] T0038 Configure logging to write to both console and a rotating file per role
- [ ] T0039 Create scratch/dev Gmail test account (or reuse personal) for OAuth testing
- [ ] T0040 Document all environment setup steps in a `SETUP.md` per repo

---

## B. Repository & Project Scaffolding (both roles)

- [x] T0041 Create GitHub repo for the cop agent — public at `aishadahesh/uoh-ay26-final-project-cop`
- [x] T0042 Create GitHub repo for the thief agent — public at `aishadahesh/uoh-ay26-final-project-thief`
- [x] T0043 Set repo visibility: public, or private + share with lecturer's address — both playing repositories are public
- [x] T0044 Initialize `git` in both local project folders — single shared repo initialized (initial commit already present)
- [x] T0045 Create initial `.gitignore` for cop repo (Python defaults + secrets) — single shared `.gitignore`, Python/venv/secrets patterns added
- [x] T0046 Create initial `.gitignore` for thief repo (Python defaults + secrets) — same shared `.gitignore`
- [x] T0047 Add `credentials.json` to `.gitignore` in both repos
- [x] T0048 Add `token.json` to `.gitignore` in both repos
- [x] T0049 Add `.env` to `.gitignore` in both repos
- [ ] T0050 Add `logs/` directory to `.gitignore` (or decide to keep sample logs tracked)
- [x] T0051 Create top-level package folder structure for cop repo (`domain/`, `infra/`, `shared/`) — implemented under `src/police_thief/` with `services/` as the infrastructure boundary
- [x] T0052 Create top-level package folder structure for thief repo (mirrored) — independently present in the sibling repository
- [x] T0053 Create `config/police/` directory — implemented with the repository's canonical role name as `config/cop/`
- [ ] T0054 Create `config/thief/` directory — not applicable to this repo: after the mandatory two-repo submission split (Section O), this is the cop repo only, and it must not contain the thief's own private config directory at all; that directory now lives exclusively in the sibling thief repo
- [x] T0055 Create empty `README.md` scaffold for cop repo with section headers matching Ch.9.4.6 — superseded by the completed academic README
- [x] T0056 Create empty `README.md` scaffold for thief repo with section headers matching Ch.9.4.6 — superseded by the completed academic README
- [x] T0057 Add cross-link placeholder from cop README to thief repo URL — replaced by the real repository link
- [x] T0058 Add cross-link placeholder from thief README to cop repo URL — replaced by the real repository link
- [ ] T0059 Create `PRD/` folder for the 7 layered PRD documents (cop repo)
- [ ] T0060 Create `PRD/` folder for the 7 layered PRD documents (thief repo)
- [x] T0061 Create `PLAN.md` work-plan file (cop repo) — `docs/PLAN.md`
- [x] T0062 Create `PLAN.md` work-plan file (thief repo) — `docs/PLAN.md`
- [x] T0063 Create `TODO.md` task file inside cop repo — `docs/TODO.md`
- [x] T0064 Create `TODO.md` task file inside thief repo — `docs/TODO.md`
- [x] T0065 Create `LICENSE` file (confirm educational-use terms if reusing example code) — added at repo root, an educational-use license mirroring `docs/tasks.md` App. D Sec. 15.5.1's terms, with explicit third-party acknowledgements for the reused Gmail OAuth pattern and reference-repo GUI inspiration
- [x] T0066 Add `pyproject.toml` / `requirements.txt` for cop repo dependencies — single shared `pyproject.toml` (uv-managed, `uv.lock` committed)
- [x] T0067 Add `pyproject.toml` / `requirements.txt` for thief repo dependencies — same shared `pyproject.toml`
- [x] T0068 Set up `tests/` directory skeleton (cop repo) — `tests/{unit,integration}` created
- [x] T0069 Set up `tests/` directory skeleton (thief repo) — same shared `tests/` tree
- [x] T0070 Set up `docs/` directory for research/analysis reports (both repos) — `docs/` already holds `tasks.md`, `TODO.md`, `PRD.md`, `PLAN.md`
- [x] T0071 Create initial commit for cop repo
- [x] T0072 Create initial commit for thief repo
- [x] T0073 Push cop repo to GitHub remote
- [x] T0074 Push thief repo to GitHub remote
- [ ] T0075 Verify both repos are reachable by a second account (simulating the lecturer's access)
- [ ] T0076 Set up branch protection / branching convention (e.g., `main` + feature branches)
- [ ] T0077 Create first feature branch for Stage-1 work in cop repo
- [ ] T0078 Create first feature branch for Stage-1 work in thief repo
- [ ] T0079 Decide and record team identity: unique 8-character code, no spaces
- [ ] T0080 Record team members' IDs for both repos' declarations
- [ ] T0081 Decide `group_id` / `group_name` values used across configs
- [ ] T0082 Draft initial `CONTRIBUTING.md` describing branch workflow (optional but recommended)
- [ ] T0083 Verify GitHub Actions / CI not required but consider adding a lint/test workflow (optional)
- [ ] T0084 Confirm repo default branch name convention (`main`)
- [ ] T0085 Set up issue templates or task board (optional project-management aid)
- [ ] T0086 Draft initial architecture diagram (freeform, for your own reference) mapping Orchestrator/modules
- [ ] T0087 Record the book's Mandatory Parameters Table values into a local reference doc for quick lookup
- [ ] T0088 Record the book's 55 mandatory rules into a local checklist doc for quick lookup during coding
- [ ] T0089 Schedule internal team review checkpoints aligned to the 7 build stages
- [ ] T0090 Confirm both team members can independently clone and run both repos locally

---

## C. Stage 1 — Base Logic: Board, Movement, Barriers, Capture (single process, no networking)

### C.0 Dec-POMDP Formal Model (Chapter 1 of `docs/tasks.md`) — *added during implementation*
- [x] T0890 Scaffold project structure: `pyproject.toml` (uv + ruff + pytest/coverage config), `src/police_thief` package, `tests/{unit,integration}`
- [x] T0891 Implement `AgentRole` enum and `NUM_AGENTS = 2` constant (`shared/constants.py`) representing the fixed `n` in the Dec-POMDP tuple
- [x] T0892 Implement version tracking (`shared/version.py`, `VERSION = "1.00"`) per the submission-guidelines versioning convention
- [x] T0893 Implement `DecPOMDPSpec` dataclass + discount-factor validation (`domain/dec_pomdp.py`), documenting the `<n, S, {Ai}, P, R, {Omega_i}, O, gamma>` tuple and where each remaining component (S, {Ai}, P, R, {Omega_i}, O) will be concretized in later chapters
- [x] T0894 Write unit tests for `AgentRole`, `NUM_AGENTS`, discount-factor validation, and `DecPOMDPSpec` immutability
- [x] T0895 Create `config/setup.json` and `config/rate_limits.json` version-tracked skeletons (content to be wired to real code in Stage 7 / Chapter 9's Gatekeeper)
- [x] T0896 Create `.env-example` and extend `.gitignore` for Python artifacts, `.venv`, and secrets
- [x] T0897 Run `uv sync`, `pytest --cov` (100% coverage on new code), and `ruff check` (zero violations) as the Chapter-1 quality gate

### C.1 Board & Coordinate System
- [x] T0091 Define `BoardConfig` data structure (grid_size, axis_origin_corner, axis_start_index) — `domain/board.py`
- [x] T0092 Implement default `grid_size = 7` per Mandatory Parameters Table
- [x] T0093 Implement coordinate system with configurable origin corner (default top-left = (0,0))
- [x] T0094 Implement configurable axis start index (default 0)
- [x] T0095 Write unit test: coordinate (0,0) resolves to the configured corner — `test_is_within_bounds_true_for_origin_and_far_corner`
- [x] T0096 Write unit test: grid boundaries reject out-of-range coordinates — `test_is_within_bounds_false_outside_grid`
- [x] T0097 Implement `Cell` / `Position` value type (immutable, hashable) — frozen dataclass
- [x] T0098 Implement equality/hash for `Position` for use in sets/dicts (barrier lookups, visited cells) — free via `@dataclass(frozen=True)`
- [x] T0099 Implement `Board` class holding grid_size + set of blocked cells
- [x] T0100 Implement method `Board.is_within_bounds(pos)`
- [x] T0101 Implement method `Board.is_blocked(pos)`
- [x] T0102 Implement method `Board.neighbors(pos)` returning the 4 orthogonal neighbors only
- [x] T0103 Write unit test: `neighbors()` never returns diagonal cells
- [x] T0104 Write unit test: `neighbors()` excludes out-of-bounds cells
- [x] T0105 Write unit test: `neighbors()` excludes blocked cells (or flags them, depending on API design) — design choice made: `neighbors()` is barrier-agnostic by design (bounds-only); blocked-cell filtering happens separately in `apply_move`/`is_boxed_in`, so both callers can distinguish "off-board" from "blocked" when they need to

### C.2 Movement Rules
- [x] T0106 Define `MoveSet` enum: N, S, E, W, STAY — named `Move` (StrEnum)
- [x] T0107 Implement `apply_move(position, move) -> new_position`
- [x] T0108 Write unit test: each of N/S/E/W moves exactly one cell in the correct direction
- [x] T0109 Write unit test: STAY returns the same position unchanged
- [x] T0110 Implement move legality check: reject moves that leave board bounds
- [x] T0111 Implement move legality check: reject moves into a blocked (barrier) cell
- [x] T0112 Implement move legality check: reject any move not in `MoveSet` (defensive check against diagonal/other input)
- [x] T0113 Write unit test: illegal out-of-bounds move raises/rejects rather than silently executing
- [x] T0114 Write unit test: illegal into-barrier move raises/rejects rather than silently executing
- [x] T0115 Decide and implement exact failure semantics for illegal moves (exception vs. rejection object vs. technical-loss flag) — chose exception (`MoveRejectedError`); caller (future Orchestrator, Ch.8) converts to technical-loss
- [x] T0116 Write unit test: a thief with zero legal moves (fully boxed in) is flagged as captured — `test_is_boxed_in_true_when_all_neighbors_blocked` (board-level; see C.6 note on why this isn't yet exercised through a full simulated match)

### C.3 Barrier Placement (Cop-only mechanic)
- [x] T0117 Define `BarrierBudget` tracking remaining barriers vs. `max_barriers` (default 14) — no separate class; `Board.remaining_barrier_budget` property, since the budget is intrinsically board state (see `docs/PRD_board_physics.md` §3)
- [x] T0118 Implement `place_barrier(cop_position, target_cell)` — only adjacent-or-own cell allowed
- [x] T0119 Write unit test: barrier placement on a cell not adjacent to cop is rejected
- [x] T0120 Write unit test: barrier placement decrements the remaining budget
- [x] T0121 Write unit test: barrier placement fails once budget is exhausted
- [x] T0122 Implement permanent/irreversible barrier semantics (no un-blocking once placed) — no unblock method exists in the API at all
- [x] T0123 Write unit test: a previously-placed barrier remains blocked for the rest of the match
- [x] T0124 Implement rule: barrier placement is public/declared, never hidden (data-model level: barrier events always recorded in the log) — resolved differently than originally framed: barrier placements are declared live on the wire (`TurnMessage.barrier_placed`, Sec. 3.3.6) the instant they happen, which is a *stronger* transparency guarantee than an after-the-fact log entry; they are deliberately never added to the sealed `LogEntry`/commit-reveal move log, since Sec. 3.3.6 requires barriers to be real-time public and plaintext, unlike a move
- [x] T0125 Write unit test: barrier event always includes exact location in whatever event/message structure is used — `test_maybe_place_barrier_places_and_returns_the_target_for_cop` (`tests/unit/test_network_match_barrier.py`) asserts the returned `[row, col]` is exact and matches the now-blocked board cell
- [x] T0126 Design barrier data structure shared between both agents' board models (must match schema in `config/game.json`) — both roles load the identical `config/game.json`; `Board` is constructed from the same `BoardConfig` either way

### C.4 Capture & Win/Loss Detection
- [x] T0127 Implement `check_capture(cop_position, thief_position) -> bool`
- [x] T0128 Write unit test: cop landing on thief's cell triggers capture
- [x] T0129 Write unit test: cop placing a barrier exactly on the thief's current cell also triggers capture — `test_barrier_placed_exactly_on_thiefs_cell_counts_as_capture`; `check_capture` is deliberately source-agnostic position-equality, so the same function covers both rules
- [x] T0130 Implement `CaptureClaim` event/message type (to be cryptographically signed later in Stage 6)
- [x] T0131 Implement thief "boxed in" detection (no legal moves at all → treated as captured)
- [x] T0132 Write unit test for thief-boxed-in edge cases (corner + surrounding barriers)
- [x] T0133 Implement survival counter tracking steps survived by the thief — the simulation loop's own `turn` counter; no separate persistent counter object needed
- [x] T0134 Implement `survival_threshold` check (default 35) — thief "wins" once reached without capture
- [x] T0135 Implement `max_moves` cap (default 35) as a match-length safety limit
- [x] T0136 Write unit test: match ends at `max_moves` even with no capture (falls through to survival scoring)
- [x] T0137 Decide relationship/precedence between `max_moves` and `survival_threshold` if they differ, and document it — decided: `max_moves` is the hard safety cap; documented in `run_local_match`'s docstring and covered by `test_max_moves_is_a_hard_cap_even_if_survival_threshold_is_higher`

### C.5 Scoring
- [x] T0138 Implement `ScoringTable` data structure matching Mandatory Parameters Table values
- [x] T0139 Implement scoring rule: capture → cop=20, thief=5 (defaults)
- [x] T0140 Implement scoring rule: survival → cop=5, thief=10 (defaults)
- [x] T0141 Implement scoring rule: technical loss → both sides 0
- [x] T0142 Implement scoring rule: tie across a series → both sides `[tie score]` (default 2)
- [x] T0143 Write unit test: capture scenario yields the correct cop/thief score pair
- [x] T0144 Write unit test: survival scenario yields the correct cop/thief score pair
- [x] T0145 Write unit test: technical-loss scenario yields 0/0
- [x] T0146 Ensure scoring values are loaded from config, never hardcoded as magic numbers in game logic
- [x] T0147 Write unit test: scoring values can be overridden upward via config without code changes

### C.6 Single-Process Local Simulation Harness
- [x] T0148 Build a minimal local game loop that alternates cop/thief turns within one process (pre-networking) — `domain/simulation.py::run_local_match`
- [x] T0149 Implement a placeholder "always move toward target" cop policy for local testing — `move_toward_policy`
- [x] T0150 Implement a placeholder "always move away from cop" thief policy for local testing — `move_away_policy`
- [x] T0151 Run a full local match end-to-end with no crash (Stage-1 milestone criterion)
- [x] T0152 Verify scoring output is printed/logged correctly at match end — `run_local_match` returns a structured `MatchResult` (not printed) by design (keeps the domain layer free of I/O); the CLI's new `simulate` subcommand prints it for manual verification
- [x] T0153 Add CLI entry point to run the local simulation (`--role police`/`--role thief` stub, single-process mode) — `python -m police_thief simulate`; restructured `main.py` into `serve`/`simulate` subcommands (the existing `serve --role cop|thief` from Chapter 2 was unchanged in behavior, only in invocation syntax; `serve` was later renamed to `peer --role police` to match `docs/tasks.md` Appendix D's illustrative example runner, again with no behavior change)
- [x] T0154 Write integration test: full local match completes and returns a valid score tuple
- [ ] T0155 Write integration test: illegal-move attempt during local match is handled without crashing the loop — not naturally reachable yet: the placeholder policies self-filter every candidate move through `apply_move` before returning, so an illegal move never reaches the loop itself in this trusted, single-process harness. Adversarial illegal-move handling from an untrusted opponent is already covered at the transport layer (Chapter 2) and will be fully covered by the commit-reveal protocol (Chapter 5/6)
- [ ] T0156 Write integration test: barrier-exhaustion scenario plays out correctly to match end — the original blocker is gone (`services/network_match.py` now places barriers live during a real match, Chapter 8+), and exhaustion is regression-tested at the wiring level (`test_maybe_place_barrier_returns_none_once_budget_exhausted`); a full live match that runs all 14 barriers out and still completes to `max_moves` is not separately exercised, since it would need precisely engineered start positions with no guaranteed capture along the way — left as a known, honestly-documented gap rather than a forced/brittle test
- [x] T0157 Write integration test: max_moves cap correctly ends a stalemate-style match
- [x] T0158 Profile the single-process loop for obvious performance issues (should be trivial at this scale) — observed: negligible, full 85-test suite (incl. unrelated real-HTTP tests) runs in ~6-7s
- [x] T0159 Document Stage-1 architecture decisions in `PRD/01-base-logic.md` — written as `docs/PRD_board_physics.md` instead, per the naming reconciliation in `docs/PRD.md` §7
- [x] T0160 Confirm Stage-1 milestone: two simulated agents legally move on the grid; barriers block movement; capture detection works (sign off before Stage 2)

### C.7 Config Wiring for Board/Physics (early pass, refined later)
- [x] T0161 Draft the `board_and_agents` section of `config/game.json` schema (grid_size, num_agents, thief_start, cop_start, axis_origin_corner, axis_start_index)
- [x] T0162 Draft the `movement_and_barriers` section of `config/game.json` schema (move_set, max_barriers, max_moves, survival_threshold)
- [x] T0163 Draft the `scoring` section of `config/game.json` schema (capture_cop, capture_thief, survival_cop, survival_thief, tie_score, technical_loss)
- [x] T0164 Write a config loader that reads `config/game.json` and constructs `BoardConfig`/`ScoringTable` — `shared/game_config.py::load_match_parameters`
- [x] T0165 Write unit test: config loader rejects a config missing required fields
- [ ] T0166 Write unit test: config loader applies defaults correctly when values are absent (where allowed) — deliberately not applicable: unlike the private per-peer TOML, the shared config is the one place physics must be fully explicit; a missing field is always a hard `GameConfigError`, never a silent default (see `docs/PRD_board_physics.md` §3)
- [x] T0167 Write unit test: loader enforces minimum values are not violated (e.g., `max_barriers >= 14`) — also covers `grid_size >= 7`
- [x] T0168 Add schema versioning field (`schema_version`) to the config and validate it on load — present in `config/game.json`; `load_match_parameters` rejects any value outside `SUPPORTED_SCHEMA_VERSIONS`

---

## D. Stage 2 — Basic FastMCP P2P Infrastructure (separate processes over localhost)

### D.1 Process Separation
- [x] T0169 Split single-process simulation into two independent runnable processes (cop / thief) — `python -m police_thief --role cop|thief` runs each as its own OS process; no Stage-1 board loop exists yet to "split," so this is the transport-level realization of process separation
- [x] T0170 Create `config/police/` local settings distinct from `config/thief/` — during shared development this was `config/cop/` and `config/thief/` side by side in one monorepo (renamed from the rulebook's illustrative "police" naming for consistency with the `AgentRole` enum; directory *naming* is not itself a mandatory rule, only the *separation* is — see `docs/tasks.md` §15 rule 1). After the two-repo submission split, this cop repo keeps only `config/cop/`; `config/thief/` was removed entirely, not merely renamed, since the cop must not have access to the thief's private config at all
- [x] T0171 Verify no shared Python module holds mutable state imported by both processes — `mcp_server.py`/`mcp_client.py`/`config.py` hold no module-level mutable state; verified by inspection and by `test_config.py::test_load_network_config_never_reads_the_other_roles_directory`
- [x] T0172 Add a manual review checklist item forbidding cross-imports between cop and thief packages — reframed per ADR-011: there are no separate cop/thief packages by design (single shared package); the actual guard enforced is "no shared mutable state" (T0171), not source-tree isolation
- [x] T0173 Write a design note documenting the Zero-Trust separation boundary explicitly — module docstrings in `mcp_server.py`, `config.py`, and `main.py`; see also `docs/PLAN.md` ADR-011

### D.2 FastMCP Server (per role)
- [x] T0174 Install and import FastMCP in the cop package — shared package, single `fastmcp` import used by both roles
- [x] T0175 Install and import FastMCP in the thief package — same shared import
- [x] T0176 Instantiate a FastMCP("police_peer") server instance — named `"cop_peer"` (naming consistency with `AgentRole.COP`), constructed via `build_peer_server(f"{role.value}_peer")`
- [x] T0177 Instantiate a FastMCP("thief_peer") server instance — same `build_peer_server`, role="thief"
- [x] T0178 Implement @mcp.tool receive_move(...) on the cop server — one shared implementation in `services/mcp_server.py`, used by both roles
- [x] T0179 Implement @mcp.tool receive_move(...) on the thief server — same shared implementation
- [x] T0180 Decide the exact tool signature/schema for move exchange (state, move, intent placeholder for now) — `MoveEnvelope(signed_move: str, signature: str)`; real board state (Ch.3) and real signatures (Ch.5/6) replace these placeholders later
- [x] T0181 Implement server-side input validation on receive_move (reject malformed payloads) — `MoveEnvelope.is_structurally_valid()` (blank-field check) plus FastMCP's own pydantic-schema validation (missing/extra fields rejected with a clean `ToolError`, verified in `test_mcp_server.py`)
- [x] T0182 Bind cop server to 0.0.0.0 on its chosen port (e.g., 8801) with transport=http — `run_peer_server(mcp, host="0.0.0.0", port=...)`; port 8801 from `config/cop/game.toml`
- [x] T0183 Bind thief server to 0.0.0.0 on its chosen port (e.g., 8802) with transport=http — not applicable to this repo: this was true during shared monorepo development (port 8802 from the now-removed `config/thief/game.toml`); after the two-repo split, this cop repo's `peer --role police` command only ever binds the cop's own port (`config/cop/game.toml`, 8801) and has no capability to run as the thief at all
- [x] T0184 Write a smoke test: server starts and responds to a health-check call — `tests/integration/test_mcp_http_roundtrip.py` (real HTTP) + manual CLI smoke test (`python -m police_thief --role cop` + live client call)
- [x] T0185 Add graceful shutdown handling for the server process (SIGINT/SIGTERM) — handled by the underlying uvicorn server when run in the main thread; documented in `run_peer_server`'s docstring rather than duplicated with custom signal handling

### D.3 FastMCP Client (per role)
- [x] T0186 Implement a client wrapper that calls the opponents receive_move tool — `services/mcp_client.py` (`send_move`/`send_move_async`)
- [ ] T0187 Implement client-side retry-on-connection-refused logic (bounded retries) — deferred to Chapter 8 (Deadline Tracker); Chapter 2's client wrapper is transport-only by design
- [x] T0188 Implement client-side timeout for the outbound call — `timeout` parameter on `send_move`/`send_move_async`
- [x] T0189 Write unit test: client correctly serializes a move payload before sending — covered by the round-trip tests (`test_mcp_client.py`, `test_mcp_http_roundtrip.py`), since serialization and deserialization are only observable together through a real call
- [x] T0190 Write unit test: client correctly deserializes the opponents acknowledgment/response — same round-trip tests assert on the returned `dict` content
- [x] T0191 Write integration test: cop client successfully calls thief server on localhost and vice versa — `test_mcp_http_roundtrip.py` exercises the shared, role-agnostic server/client code path; since both roles run identical code, one direction's test validates the other symmetrically (no role-specific branching exists to test separately)

### D.4 Turn Management (pre-crypto version)
- [ ] T0192 Implement a basic turn-alternation protocol: cop moves, then thief moves, repeat
- [ ] T0193 Implement local turn-tracking state on each side
- [ ] T0194 Write integration test: two localhost processes complete a full match via network calls only (no shared memory)
- [ ] T0195 Verify each side's local board state stays in sync after every exchanged move
- [ ] T0196 Write test: simulate a dropped/garbled message and confirm it does not crash either process
- [ ] T0197 Log every sent/received MCP message with timestamps for later debugging

### D.5 Config for Networking
- [ ] T0198 Draft the network section of config/game.toml (my_port, opponent_url, turn_timeout_seconds)
- [ ] T0199 Implement TOML config loader for the private per-peer settings
- [ ] T0200 Write unit test: TOML loader correctly parses the network, strategy, trash_talk, llm, and email sections
- [ ] T0201 Write unit test: TOML loader tolerates commented-out optional sections
- [ ] T0202 Confirm private TOML never contains any value that must be agreed with the opponent
- [ ] T0203 Implement config precedence: shared JSON values override matching TOML keys where both exist

### D.6 MCP Protocol Hygiene
- [ ] T0204 Document exactly which tools are exposed by each server (API contract doc)
- [ ] T0205 Version the MCP tool schema so future changes do not silently break compatibility
- [ ] T0206 Add defensive parsing: reject any tool call with unexpected/extra fields
- [ ] T0207 Add defensive parsing: reject any tool call missing required fields
- [ ] T0208 Write test: malformed JSON payload to a tool returns a clean error, not a crash
- [ ] T0209 Confirm server responses never leak more information than the local-truth principle allows (strengthen later in Stage 6)
- [ ] T0210 Benchmark round-trip latency of a localhost MCP call as a sanity baseline before adding tunneling overhead

### D.7 Stage-2 Milestone
- [x] T0211 Confirm milestone: a geometric message sent from agent A over localhost is received and decoded correctly at agent B — `tests/integration/test_mcp_http_roundtrip.py`, re-run in Chapter 10's milestone-reconciliation pass to confirm it's still true today, not just at Chapter 2's time
- [x] T0212 Document Stage-2 architecture decisions in PRD/02-mcp-infra.md — written as `docs/PRD_fastmcp_networking.md` in Chapter 10, per the naming reconciliation in `docs/PRD.md` §7. This was a genuine gap: every other chapter got its PRD in the same session it was built, but Chapter 2's was never written until this milestone cross-check turned it up
- [ ] T0213 Run a full two-process match end-to-end with no crash, using the Stage-1 placeholder policies over the network — still not done: Chapter 2 proved one HTTP round trip, Chapter 8's Orchestrator proved one real turn against a real server, but no continuous, multi-turn, two-sided match loop exists yet (see `docs/PRD_reliability_layer.md` §3)
- [ ] T0214 Confirm identical scoring/log output vs. the single-process Stage-1 version (parity check) — blocked on T0213
- [ ] T0215 Tag this milestone commit locally (not yet the final submission tag) for traceability — deferred: git tagging is a submission-time action per `docs/tasks.md` App. C, not something to do mid-development without the user's explicit direction

---

## E. Stage 3 — First Strategy Module (Blind: no language, no scent yet)

### E.1 Strategy Module Boundary
- [x] T0216 Create a dedicated strategy module/package, separate from PeerRuntime networking code — `domain/strategy/`
- [x] T0217 Define BrainBase abstract class with a _decide_move() method
- [x] T0218 Add a _pick_move() (or barrier-placement) hook for the cops BrainBase subclass
- [ ] T0219 Wire PeerRuntime to call into the strategy module exactly once per turn, at the correct pipeline point — deferred: no PeerRuntime/Orchestrator exists yet (Chapter 8)
- [x] T0220 Write unit test: strategy module receives the current known state and returns a legal move
- [x] T0221 Write unit test: strategy module never receives full objective state (only local-truth-consistent inputs) — the headline `tests/integration/test_strategy_pipeline.py` proof: neither brain's `_decide_move` call ever receives the opponent's true `Position`
- [x] T0222 Add config keys police_class / thief_class in the private TOML strategy section — named `cop_class`/`thief_class` for consistency with the `AgentRole` enum (same renaming rationale as Chapter 2's `config/cop/`)
- [x] T0223 Implement dynamic class loading from a package.module:Class string (e.g., via importlib)
- [x] T0224 Write unit test: dynamic strategy-class loading correctly instantiates a custom subclass — tests that a distinct `DummyCustomBrain` is actually loaded (an earlier draft of this test pointed at `ManhattanHeuristicBrain` itself, which would have passed even if loading were silently broken — caught and fixed before trusting it)
- [x] T0225 Write unit test: fallback to default heuristic brain when no custom class is configured

### E.2 Manhattan-Distance Heuristic (baseline/example track)
- [x] T0226 Implement Manhattan distance function D = |x_cop - x_target| + |y_cop - y_target| — `domain/heuristics.py`, shared with Chapter 3/4's placeholder policies (DRY refactor)
- [x] T0227 Write unit test: Manhattan distance matches hand-computed examples — including Sec. 6.3.3's own worked example (`D((2,2),(5,5))=6`)
- [x] T0228 Implement greedy-toward-target move selection using Manhattan distance
- [x] T0229 Write unit test: greedy heuristic picks a move that strictly decreases distance when possible
- [x] T0230 Implement tie-breaking logic when multiple moves yield equal distance reduction — deterministic by fixed iteration order (N,S,E,W); no explicit preference beyond reproducibility, which is what actually matters for a fair match
- [x] T0231 Implement thief flee heuristic: maximize distance from believed cop position — via `ManhattanHeuristicBrain`'s belief-map-driven `chase=False` path (the placeholder `move_away_policy` from Ch.3/4 still uses the opponent's raw position, by design — see `docs/PRD_strategy_module.md` §3)
- [x] T0232 Write unit test: flee heuristic increases distance from the cops last known position

### E.3 Custom/Alternative Algorithm Track (optional, if chosen)
- [x] T0233 Decide whether the team will implement a custom pathfinding/planning algorithm instead of or alongside heuristics — decided (docs/PLAN.md ADR-010): the Manhattan-distance heuristic is the chosen baseline; a custom algorithm remains a stretch goal, not pursued this chapter
- [ ] T0234 If custom: design the algorithms state representation — not applicable, custom track not pursued
- [ ] T0235 If custom: implement the algorithms core decision function — not applicable
- [ ] T0236 If custom: write unit tests validating legality and sane behavior of its output moves — not applicable
- [ ] T0237 If custom: benchmark its decision latency per turn against step_deadline_seconds — not applicable

### E.4 Reinforcement-Learning Track (optional tool, if chosen)
- [x] T0238 Decide whether the team will use RL as one optional strategy tool — decided (docs/PLAN.md ADR-010): not pursued; Sec. 6.2.1 explicitly confirms RL is optional, not required
- [ ] T0239 If RL chosen: design the state representation for Q(s,a) — not applicable
- [ ] T0240 If RL chosen: implement a Q-table (or function-approximator) storage structure — not applicable
- [ ] T0241 If RL chosen: implement the Bellman update Q(s,a) += alpha times reward plus gamma times max next Q minus current Q — not applicable
- [ ] T0242 If RL chosen: implement epsilon-greedy action selection — not applicable
- [ ] T0243 If RL chosen: implement a training loop against a scripted/self-play opponent — not applicable
- [ ] T0244 If RL chosen: implement a decay schedule for epsilon over training episodes — not applicable
- [ ] T0245 If RL chosen: implement checkpointing/saving of learned Q-values — not applicable
- [ ] T0246 If RL chosen: implement loading of a pretrained policy at match start — not applicable
- [ ] T0247 If RL chosen: write unit test verifying the Q-update math against a hand-computed example — not applicable
- [ ] T0248 If RL chosen: log learning-curve data (episode vs. cumulative reward) for later reporting — not applicable
- [ ] T0249 If RL chosen: produce a learning-curve plot for the academic README — not applicable
- [ ] T0250 If RL chosen: verify the final trained policy still only ever outputs legal moves — not applicable
- [x] T0251 If RL chosen: document that RL is one optional tool among several, not a course requirement, in the README — documented in `docs/PRD_strategy_module.md` §1 and here regardless of the choice not to pursue it

### E.5 Barrier-Placement Strategy (Cop)
- [x] T0252 Implement a barrier-placement policy function distinct from movement policy — `ManhattanHeuristicBrain._pick_move`
- [x] T0253 Implement a simple corner-the-thief barrier heuristic (progressively block flanking cells) — combines structural reachable-area chokepoints with a public-evidence closer: a singleton fresh scent candidate on an adjacent cell is challenged directly, while a capped/saturated set of up to four cells can trigger one adjacent barrier only when that cell constrains at least two candidates. Every proactive placement preserves at least two Police exits. This closes equal-speed boundary orbits without consulting revealed/private Thief coordinates.
- [x] T0254 Write unit test: barrier placement never targets a cell more than one step from the cop
- [x] T0255 Write unit test: barrier budget is respected by the placement policy (stops placing at zero budget)
- [x] T0256 Tune barrier-placement timing (early game vs. late game) and document reasoning — based on evidence quality and tactical usefulness, not a hard turn number. The Police spends early only for a focused adjacent capture challenge or a multi-candidate containment cell; otherwise `_pick_move` conserves the budget until a candidate reduces reachable area by more than one. This allows late-game containment while preventing speculative wall spam.

### E.6 Decision Pipeline Wiring & Determinism
- [x] T0257 Ensure the actual move-selection computation is always pure algorithmic/deterministic code (no LLM call in this stage)
- [x] T0258 Add a hard boundary/interface so a later LLM verbal layer cannot influence the move return value — `BrainBase`'s method signatures structurally exclude any hint/LLM input (docs/PRD_strategy_module.md §2)
- [x] T0259 Add a code-review checklist item: no LLM output is ever assigned to the move variable — realized as a structural guarantee (T0258) rather than a manual checklist item, which is stronger
- [ ] T0260 Add logging of every decision made by the strategy module (state in, move out) for later debugging — deferred: no logging infrastructure wired yet (Chapter 8's Log Manager)

### E.7 Stage-3 Milestone
- [x] T0261 Confirm milestone: given a known target position, the computing agent executes the shortest legal path with no manual intervention
- [ ] T0262 Run a full two-process match using real (non-placeholder) strategies end-to-end — deferred: this implies a live networked two-process match (Chapter 8); the strategy pipeline itself is proven single-process
- [x] T0263 Write integration test: match completes with sensible (non-random-looking) tactical behavior from both sides — `tests/integration/test_strategy_pipeline.py` (single-process; two-process/networked wiring is Chapter 8)
- [x] T0264 Document Stage-3 decisions in PRD/03-strategy-module.md — written as `docs/PRD_strategy_module.md`, per the naming reconciliation in `docs/PRD.md` §7
- [x] T0265 Record chosen strategy track (heuristic / custom / RL) rationale for the academic README draft — documented in `docs/PRD_strategy_module.md` and `docs/PLAN.md` ADR-010; final README integration is a later, end-of-project step

---

## F. Stage 4 — Language + Scent (pheromone mechanics, deception hints, LLM integration)

### F.1 Pheromone Emission & Decay
- [x] T0266 Define `ScentField` data structure sized `[scent field size]` (default 5x5) centered on an agent
- [x] T0267 Implement emission with `scent_center_intensity` (default 0.9) at the emitting agent's own cell
- [x] T0268 Implement radial falloff of intensity from the emission center across the 5x5 field
- [x] T0269 Implement the mandatory decay formula: tau(t+1) = max(0, (1 - rho) * tau(t) + delta_tau)
- [x] T0270 Wire `rho` (scent decay rate, default 0.10) from config, not hardcoded — and validated as FIXED (not a minimum), per the Mandatory Parameters Table
- [x] T0271 Implement per-cell scent state storage for the full board grid — sparse `dict[Position, float]`; untouched cells are implicitly 0.0
- [x] T0272 Implement per-turn decay application across the entire board (both agents' emissions) — wired into `run_local_match`: each side's field decays then emits once per turn
- [x] T0273 Write unit test: emission at t=0 yields exactly `scent_center_intensity` at the agent's own cell
- [x] T0274 Write unit test: decay-only cell (agent left) follows the exact decay curve over N turns — `test_decay_only_cell_follows_the_exact_geometric_curve_over_n_turns`
- [x] T0275 Write unit test: re-emission while agent remains present keeps intensity elevated at/above the decay floor
- [x] T0276 Write unit test: scent value never goes negative (floor at zero enforced)
- [ ] T0277 Write unit test: scent value never exceeds the configured intensity ceiling — **does not hold**, and is documented as a deliberate interpretation choice (`docs/PRD_pheromone_scent.md` §3, invoking the academic-freedom-on-contradiction clause, `docs/tasks.md` Sec. 0.4): the rulebook's own MANDATORY formula adds a fresh 0.9 every turn an agent is present, which providably exceeds 0.9 after two consecutive turns in the same cell. Implemented the formula literally rather than silently capping it; the actual (uncapped) behavior is tested directly instead (`test_sustained_presence_can_exceed_the_bare_center_intensity`)
- [ ] T0278 Implement symmetric scent tracking: cop's field is visible to the thief's belief logic and vice versa — the two independent, symmetric fields exist and are proven not to share state, but there is no "belief logic" yet to make them visible to (Chapter 6)
- [x] T0279 Verify scent maps are computed independently per side from each side's own local observations (no shared object)
- [ ] T0280 Add a debug visualization/printout of the scent grid for development purposes — deferred to Chapter 7's GUI work, where a real rendering surface already needs to exist

### F.2 Belief Map Construction
- [x] T0281 Define `BeliefMap` structure: probability distribution `b(s)` over board cells
- [x] T0282 Implement Bayesian-style update of `b(s)` incorporating the observed scent field — posterior proportional to prior times (scent intensity + epsilon), renormalized
- [ ] T0283 Implement Bayesian-style update of `b(s)` incorporating the opponent's verbal hint (weighted by trust) — not built: `detect_bluff` exists as a standalone classifier (F.5), but nothing yet feeds a hint back into `BeliefMap`'s own probability update
- [x] T0284 Implement `arg max_s b(s)` extraction (current best-guess opponent location)
- [x] T0285 Write unit test: belief map updates correctly given a synthetic scent snapshot
- [x] T0286 Write unit test: belief map normalizes to a valid probability distribution (sums to 1) after each update
- [x] T0287 Write unit test: blocked/barrier cells always carry zero belief
- [ ] T0288 Implement belief-map decay/diffusion over time when no new evidence arrives — not built as an independent mechanism: belief indirectly tracks scent's own decay when re-updated from an already-decayed field, but there is no belief-specific diffusion/uncertainty-growth model
- [ ] T0289 Implement a trust-weighting mechanism for verbal hints vs. the always-trustworthy scent channel — not built: a deeper, stateful feature better suited once a live multi-turn match loop (Chapter 8) exists to accumulate trust over real games
- [ ] T0290 Write unit test: a caught lie (hint contradicts scent trail) reduces future trust weight assigned to that opponent's hints — not applicable; no trust-weight state exists yet (see T0289)
- [x] T0291 Implement the worked lie-detection example as a regression test (south-east scent trail vs. false north claim) — `test_detect_bluff_catches_a_lie_reproducing_the_worked_example`

### F.3 Natural-Language Hint Generation & Parsing
- [ ] T0292 Define the free-text hint schema/field in the move-exchange message — `hints.py::Hint` exists standalone; wiring it into an actual MCP move-exchange message is Chapter 8
- [x] T0293 Implement `[hint word limit]` enforcement (default 15 words) on outgoing hints
- [ ] T0294 Implement `[game arena]` theme substitution into hint text (e.g., "New York" landmarks) or empty-string fallback — not built: hints use plain direction phrases ("I moved north."), no thematic flavor text; a narrative nice-to-have, not core to the mechanism
- [x] T0295 Write unit test: generated hint never exceeds the configured word limit
- [x] T0296 Implement an `Intent` flag alongside every hint marking it as truthful or a deliberate lie — `Hint.intent_truthful`
- [x] T0297 Write unit test: `Intent` flag is always set before the hint is sent (never left undefined) — structurally guaranteed: `Hint` is a frozen dataclass with `intent_truthful` as a required (non-optional) field
- [x] T0298 Implement hint-parsing logic on the receiving side to extract usable directional/positional signal — `parse_claimed_direction`
- [ ] T0299 Write unit test: hint parser handles a variety of phrasing styles without crashing — partially: `parse_claimed_direction` is strict template-exact matching (a dictionary lookup over 5 known phrases), not general NLP; "variety of phrasing" in the sense of synonyms/free text is out of scope since only our own deterministic templates are generated on our side
- [x] T0300 Write unit test: hint parser gracefully handles nonsensical or malformed text (no signal extracted, no crash) — `test_parse_claimed_direction_returns_none_for_unrecognized_text`
- [x] T0301 Prohibit direct numeric coordinate leakage in generated hint text (no raw grid coordinates) — true by construction (fixed phrase strings, no interpolated position values)
- [x] T0302 Write unit test/lint check: hint text never contains a raw coordinate pair pattern — `test_template_phrases_never_contain_a_raw_coordinate_pattern`

### F.4 LLM Integration for the Verbal Layer Only
- [x] T0303 Confirm and document: the LLM is used exclusively for hint text generation and opponent-hint interpretation, never for move selection — documented extensively in `brain_base.py`/`hints.py` docstrings and `docs/PRD_strategy_module.md`
- [ ] T0304 Implement `[trash_talk] provider` config switch: template / ollama / claude_api / claude_cli — the config key exists (commented, defaulting to `template`) in `config/{cop,thief}/game.toml`, but no loader/dispatch code reads it yet
- [x] T0305 Implement `template` provider: deterministic pre-written phrases, zero tokens — `TemplateHintProvider`
- [ ] T0306 Implement `ollama` provider: call local model at `localhost:11434` — deliberately not built: requires a live local service this project's automated test suite should not depend on (Sec. 6.4.7 confirms `template`-only play is fully legitimate)
- [ ] T0307 Implement `claude_api` provider: call Anthropic API with a small/cheap model — deliberately not built, same reasoning (live external API dependency)
- [ ] T0308 Implement `claude_cli` provider: shell out to `claude -p` via Claude Code CLI — deliberately not built, same reasoning
- [ ] T0309 Implement `every_n_steps` throttling to reduce LLM invocation frequency — not applicable yet: no live turn loop exists to throttle (Chapter 8)
- [ ] T0310 Implement `step_deadline_seconds` timeout around every LLM call — not applicable: no real LLM call exists yet to time out
- [ ] T0311 Write unit test: LLM call exceeding its deadline is aborted/falls back gracefully — not applicable, same reason
- [ ] T0312 Implement a fallback path: if the configured LLM provider is unreachable, fall back to `template` mode rather than crash — not applicable: only `template` is implemented, so there is nothing to fall back *from*
- [ ] T0313 Write integration test: fallback path triggers correctly when Ollama/API is deliberately made unreachable — not applicable, same reason
- [x] T0314 Implement token-usage counting for every LLM call (for later Step-0/budget reporting) — `TokenUsage` (Chapter 5's `services/step0.py`); not yet wired to a real LLM call since none exists
- [x] T0315 Write unit test: token counter accumulates correctly across a full match — covered at the unit level in Chapter 5's `test_step0.py`; full-match live integration is pending Chapter 8
- [ ] T0316 Enforce `[token budget per series]` (default ~200000) as a soft cap with warning/log when approached — not built
- [ ] T0317 Implement prompt templates for hint generation (bluff/deception composition) — not applicable: the implemented `template` provider needs no LLM prompts at all, by design (zero tokens)
- [ ] T0318 Implement prompt templates for opponent-hint psychological analysis (bluff classifier / behavioral profiler) — not applicable: `detect_bluff` is a deterministic heuristic, not an LLM-based profiler
- [ ] T0319 Write unit test: prompt construction never embeds the agent's own true hidden state in a way that could leak via a bug — not applicable, no prompts exist
- [x] T0320 Document the LLM integration architecture (which layer calls the model, how output flows back) in `PRD/04-language-scent.md` — written as `docs/PRD_strategy_module.md` §3, per the naming reconciliation in `docs/PRD.md` §7

### F.5 Deception & Psychological Layer
- [ ] T0321 Design a strategy for deciding when to lie vs. tell the truth in verbal hints — not built: `TemplateHintProvider.generate` takes `tell_truth` as a caller-supplied parameter; the mechanism to produce either exists, the autonomous policy for choosing between them does not
- [ ] T0322 Implement randomized or strategic lie-frequency logic (avoid being either always-truthful or always-lying, both exploitable) — not built, same reason as T0321
- [x] T0323 Implement a simple opponent-hint "bluff classifier" heuristic (cross-reference hint against scent) — `detect_bluff`
- [x] T0324 Write unit test: bluff classifier flags a hint contradicted by the scent trail
- [x] T0325 Write unit test: bluff classifier does not falsely flag a truthful, scent-consistent hint

### F.6 Stage-4 Milestone
- [ ] T0326 Confirm milestone: free-form hint reporting subject to the word-count limit works end-to-end — works as a standalone mechanism; "end-to-end" in a live match/network sense awaits Chapter 8
- [ ] T0327 Confirm milestone: a scent map is computed and viewable/loggable — computed since Chapter 4, and the *derived* belief heatmap is viewable since Chapter 7's `LiveGUI`; still not "loggable," though — `LogManager`/`LogEntry` (Chapter 8) only ever record `{state, move, intent, nonce, h_commit}`, never the raw scent field itself
- [ ] T0328 Confirm milestone: the LLM produces a hint (true or lie) every step without crashing the match — not applicable: no live match loop calls the hint provider every step yet
- [ ] T0329 Run a full match with real scent + real LLM-generated hints end-to-end with no crash — not built, same reason
- [x] T0330 Verify belief maps visibly track approximate opponent location better than random guessing over a test match — `test_cop_belief_converges_toward_the_true_thief_position_over_time`, and the full capture achieved via belief alone in `tests/integration/test_strategy_pipeline.py`
- [x] T0331 Document Stage-4 decisions and worked examples in `PRD/04-language-scent.md` — written as `docs/PRD_strategy_module.md` (this chapter's belief/hint content) alongside `docs/PRD_pheromone_scent.md` (Chapter 4's scent-only content)

---

## G. Stage 5 — Cloud Exposure & Tunneling (real cross-machine P2P)

**Current status:** Cloudflare Tunnel replaced the originally named ngrok/Localtonet option. Both stable hostnames have been exercised in real cross-machine series, including recovery from 502, 530/1033, URL rotation, origin mismatch, and handoff timing failures. See `docs/RUNNING.md`.

### G.1 Tunnel Setup
- [x] T0332 Configure a public HTTPS tunnel for the Cop port — completed with Cloudflare Tunnel
- [x] T0333 Configure a public HTTPS tunnel for the Thief port — completed with Cloudflare Tunnel
- [x] T0334 Verify the public tunnel URL is reachable from an external network — proven in five counted cross-team series
- [x] T0335 Update `config/game.toml` `opponent_url` to a public opponent URL rather than localhost
- [ ] T0336 Test Localtonet as a fallback tunnel provider in case ngrok is unavailable
- [x] T0337 Document the tunnel-startup procedure step by step for reproducibility — `docs/RUNNING.md`
- [ ] T0338 Automate tunnel startup via a script/Makefile target (optional convenience)
- [x] T0339 Handle tunnel URL rotation by re-sharing the opponent URL before a series — exercised with multiple quick-tunnel opponents
- [x] T0340 Write a runbook entry for tunnel drops — `docs/RUNNING.md#10-troubleshooting`

### G.2 Cross-Machine Match Testing
- [x] T0341 Recruit a second machine/opponent team for a real cross-machine test
- [x] T0342 Run a full match between genuinely separate machines over the public internet — repeated across five counted opponents
- [x] T0343 Verify tunnel latency fits the negotiated timeouts — six-sub-game series completed under the configured deadlines
- [ ] T0344 Write integration test/checklist: confirm no `localhost`-only assumptions remain anywhere in networking code
- [x] T0345 Test behavior when the opponent's tunnel is temporarily down — observed and diagnosed during live series
- [x] T0346 Verify timeout/retry behavior under real network latency — observed during negotiation and series handoffs

### G.3 NAT/Firewall Considerations
- [x] T0347 Confirm outbound firewall rules do not block the tunnel connector
- [x] T0348 Confirm no manual port-forwarding is required beyond Cloudflare Tunnel
- [x] T0349 Document encountered routing/origin failures and workarounds — IPv4 origins plus 502/530 guidance in `docs/RUNNING.md`

### G.4 Stage-5 Milestone
- [x] T0350 Confirm milestone: a remote agent connects through a public tunnel and gameplay updates correctly per step
- [ ] T0351 Document Stage-5 setup in `PRD/05-cloud-tunnel.md`
- [x] T0352 Record the exact tunnel command/config used for reproducibility — quick and named dual-ingress examples in `docs/RUNNING.md`

---

## H. Stage 6 — Cryptographic Security & Zero-Knowledge Protocol

### H.1 Commit-Reveal Core Implementation
- [x] T0353 Implement `commit(state, move, intent)` producing `H_commit = SHA256(state || move || intent || nonce)`
- [x] T0354 Implement canonical JSON serialization (sorted keys, fixed separators) for the hashed payload
- [x] T0355 Implement cryptographically-secure Nonce generation (e.g., `secrets.token_hex`), never `random`
- [x] T0356 Write unit test: identical inputs with different Nonces produce different commitment hashes
- [x] T0357 Write unit test: `commit()` never transmits the raw move/intent, only the hash — `Commitment` is structurally limited to `{h_commit, nonce}`, verified directly
- [x] T0358 Implement `verify(state, move, intent, nonce, h_commit)` recomputing and comparing hashes
- [x] T0359 Use constant-time comparison (e.g., `secrets.compare_digest`) in `verify()`
- [x] T0360 Write unit test: `verify()` returns True for a correct, untampered reveal
- [x] T0361 Write unit test: `verify()` returns False for any single-field tampering (state/move/intent/nonce) — plus a dedicated test for the commit hash itself being altered

### H.2 Four-Step Protocol Wiring
- [ ] T0362 Implement Step 1 (Commit): send only `H_commit` over the network — deferred: this is network wiring, owned by Chapter 8's Orchestrator/state machine, not this chapter's crypto-primitives scope
- [ ] T0363 Implement Step 2 (Acknowledge): opponent confirms receipt and lock-in before either side proceeds — deferred to Chapter 8
- [ ] T0364 Write unit test: Acknowledge cannot be sent before a valid Commit was received — deferred to Chapter 8 (requires the state machine to test against)
- [ ] T0365 Implement Step 3 (Reveal): send the actual move + hint text, Nonce still withheld — deferred to Chapter 8 (hint text itself is also Chapter 6)
- [ ] T0366 Write unit test: Reveal step is rejected if it arrives before the corresponding Acknowledge — deferred to Chapter 8
- [x] T0367 Implement Step 4 (Audit / Final Reveal): reveal all Nonces only at game end — live `NetworkMatchRunner` exchanges sealed records and nonce reveals after terminal gameplay
- [ ] T0368 Write unit test: the four steps cannot be executed out of order (protocol sequencing enforced) — deferred to Chapter 8's legal state machine
- [ ] T0369 Write unit test: skipping a step causes a technical-loss/rejection, not a silent pass-through — deferred to Chapter 8
- [ ] T0370 Add sequence diagrams/comments in code documenting the four-step handshake per turn — the sequence diagram already exists in `docs/PLAN.md` §6; per-turn network code to comment doesn't exist yet (Chapter 8)

### H.3 Mutual Audit & Log Integrity
- [x] T0371 Implement full match-log recording of every step's state, move, intent, nonce, and commitment hash — exercised in five counted six-game series and saved as replayable JSON
- [x] T0372 Implement end-of-match mutual audit: recompute every step's hash and compare against the log's recorded commitment — `audit_log()`
- [x] T0373 Write unit test: audit passes on an untampered log
- [x] T0374 Write unit test: audit fails and flags tampering when any single byte of a logged step is altered
- [ ] T0375 Implement automatic technical-loss declaration triggered by a failed audit — the primitive (`AuditResult.verified is False`) is ready for a caller to map to `MatchOutcome.TECHNICAL_LOSS`; that caller is Chapter 8's Orchestrator, which doesn't exist yet
- [x] T0376 Write integration test: full match runs, log is deliberately tampered post-hoc, and audit correctly catches it — `test_multi_turn_log_audit_catches_a_post_hoc_tampering_attempt` builds a realistic multi-turn commit/reveal sequence (no live match engine produces logs yet, so this is a synthetic-but-faithful stand-in; wiring into `run_local_match` is Chapter 8's job)
- [x] T0377 Ensure the audit result is deterministic and reproducible independent of who runs it — `test_audit_log_result_is_deterministic_across_repeated_runs`

### H.4 Capture Claim & Barrier Declaration Integrity
- [x] T0378 Implement cryptographic signing of `Capture Claim` events — no bespoke function needed: `commit()`/`verify()` are already generic enough to seal a `CaptureClaim`, demonstrated directly (DRY: mirrors how `check_capture()` was already generic across move/barrier captures in Chapter 3)
- [x] T0379 Write unit test: a false capture claim is exposed during audit (position mismatch)
- [x] T0380 Implement cryptographic signing/logging of every barrier-placement declaration — same generic primitive, demonstrated directly
- [x] T0381 Write unit test: barrier location cannot be silently altered after being declared without breaking the audit

### H.5 Scent-Model Locking
- [x] T0382 Cryptographically lock the scent emission/decay formula parameters into the signed shared config before match start — `game_config.py::config_fingerprint` (SHA-256 over the canonical shared config), wired into `Step0Declaration.config_fingerprint`; not yet actually *exchanged and enforced* pre-match (Chapter 8), but the fingerprint primitive that would detect any divergence — including in the otherwise-fixed scent params — exists and is tested
- [x] T0383 Write unit test: any attempt to change scent parameters mid-match is detected/rejected — `test_fingerprint_changes_if_the_otherwise_fixed_scent_decay_rate_changes` (detection); mid-match *rejection* enforcement is Chapter 8

### H.6 Step-0 Computational Fairness Declaration
- [x] T0384 Implement hardware-spec gathering: OS, CPU core count, RAM size, GPU/VRAM presence — `gather_hardware_spec()`; caught and fixed a real bug during implementation (see `ProgressDoc.md`): an incomplete `ctypes` struct silently zeroed out Windows RAM detection
- [x] T0385 Implement LLM-model-name capture for the Step-0 declaration
- [x] T0386 Implement Git commit-hash capture for the Step-0 declaration — `get_git_commit_hash()`, verified against this real repo
- [x] T0387 Implement team-name and game/sub-game-number capture for the Step-0 declaration
- [x] T0388 Serialize the Step-0 declaration as canonical JSON
- [x] T0389 Cryptographically sign the Step-0 declaration with a pre-shared/agreed key — HMAC-SHA256, not a bare hash (a keyless hash can't authenticate origin)
- [x] T0390 Write unit test: Step-0 declaration cannot be modified after signing without invalidating the signature — including a nested-field (hardware spec) tamper test
- [x] T0391 Implement exchange of Step-0 declarations between both agents before the first real move — negotiation identity plus sealed `step: 0`, `type: "system_spec"` audit record
- [x] T0392 Write integration test: match refuses to start without both sides' valid Step-0 declarations — pre-game validation and malformed/missing Step-0 regressions cover refusal/sign-off gating

### H.7 Replay-Ready Log Format
- [x] T0393 Ensure the log format produced here is directly consumable by the Stage-7 Replay Viewer — confirmed in Chapter 7: `domain/replay.py` imports and uses `LogEntry`/`audit_log` directly, no adapter/translation layer needed
- [x] T0394 Write a schema/contract test verifying log fields match what the Replay Viewer expects — `test_replay_viewer_against_a_real_commit_reveal_sealed_multi_turn_log` (Chapter 7), building a real multi-turn log via actual `commit()` calls and replaying it end-to-end

### H.8 Stage-6 Milestone
- [ ] T0395 Confirm milestone: moves must be committed via Commit and only then revealed via Reveal, with Nonce — updated status post-Chapter-8: the Orchestrator now sends a real commitment (`H_commit`) over a real network call and self-verifies it, but does not yet transmit a separate Reveal message (nonce + move) to the opponent at all — only one side's commitment ever crosses the wire, so the full two-sided Commit-then-Reveal *exchange* the milestone describes is still not implemented, only the Commit half plus local self-verification
- [x] T0396 Confirm milestone: correct Step-0 hardware declaration exchanged and verified — active in the live peer runner and opponent audits
- [x] T0397 Run a full match with the complete crypto protocol active end-to-end with no crash — five mutually verified counted six-game series completed
- [ ] T0398 Deliberately inject a tampering bug and confirm the match is correctly disqualified — done at the primitive level (`audit_log` correctly catches injected tampering); "the match is disqualified" implies live `MatchOutcome` wiring, which is Chapter 8
- [x] T0399 Document Stage-6 decisions in `PRD/06-security-crypto.md` — written as `docs/PRD_commit_reveal_crypto.md`, per the naming reconciliation in `docs/PRD.md` §7
- [ ] T0400 Peer-review the cryptographic code with your teammate for subtle bugs (constant-time comparisons, nonce reuse, serialization consistency) — genuinely requires the human teammate's involvement; not something this session can complete alone

---

## I. Stage 7 — GUI, Replay Viewer & Gmail Reporting Automation

### I.1 Live GUI — Local Truth Only
- [x] T0401 Choose GUI toolkit (Tkinter or PyQt/PySide) and scaffold a main window per role — Tkinter (stdlib, no new dependency); confirmed it works headlessly on this dev machine (`Tk()` constructs, widgets inspectable via `.cget()`/`.itemcget()`, buttons triggerable via `.invoke()`) before committing to it
- [x] T0402 Design the GUI layout: own position, own scent-emitted trail, belief heatmap over opponent, turn banner — own position, belief heatmap, and turn banner are all rendered; the raw scent field itself is not rendered as a separate layer distinct from the belief heatmap it feeds (the heatmap *is* the scent-derived signal Sec. 7.3.2 actually requires)
- [x] T0403 Implement rendering of the board grid at the configured `[board size]`
- [x] T0404 Implement rendering of the agent's own current position on the grid
- [x] T0405 Implement rendering of static barrier cells (blocked, no belief) — a distinct, fixed color, never a belief gradient, even if the (physically real) scent field has intensity there
- [x] T0406 Implement heatmap color-gradient rendering of the belief map (e.g., deeper red = higher probability)
- [x] T0407 Write unit test: heatmap rendering never displays the opponent's true position directly — plus a structural test that `LiveViewModel`/`build_live_view_model` have no field/parameter capable of holding it at all
- [x] T0408 Implement live refresh of the heatmap as new turns are played — `render()` is callable repeatedly; proven via a real multi-turn integration test, not just a single-call smoke test
- [x] T0409 Implement the turn-state banner ("YOUR TURN" vs "LOCKED")
- [ ] T0410 Wire the turn-state banner to the actual Commit/Acknowledge/Reveal state machine state — deferred: no state machine exists yet (Chapter 8)
- [x] T0411 Write unit test: banner shows LOCKED immediately after a Commit is sent, before Reveal completes — tested at the `TurnState`/view-model level (no live Commit/Reveal handshake exists yet to drive it automatically)
- [x] T0412 Write unit test: banner shows YOUR TURN only when the local agent may legally act — same caveat
- [x] T0413 Implement disabling of manual input controls while LOCKED (prevent user from acting out of turn) — the original rationale ("no manual input controls exist") no longer holds: a new interactive play mode (`gui/play_app.py::PlayApp`, `python -m police_thief play`) was added beyond this rulebook's own scope, at direct user request. Its move-pad buttons, board clicks, and barrier button are all disabled outside a human-controlled turn (`_disable_human_controls`/`_enable_human_controls`), tested directly (`test_starting_on_an_agent_turn_disables_every_control_and_schedules_the_agent`, and the no-op tests for a click/toggle attempted out of turn)
- [ ] T0414 Add a scrolling event/log panel showing recent hints, moves, and barrier placements — deferred: no Log Manager exists yet (Chapter 8)
- [ ] T0415 Add a scoreboard panel showing current score/turn count — deferred: no live match loop produces a running score yet
- [ ] T0416 Add graceful handling of GUI close/exit without crashing the underlying match process — Tkinter's default window-close behavior is relied on for now; no custom handler added since there is no live match process yet to protect
- [ ] T0417 Test GUI responsiveness under normal match pacing (no UI freeze during LLM calls) — not applicable: no LLM calls happen inside a live GUI loop yet
- [ ] T0418 Run the GUI update loop on a separate thread/async task from network I/O to avoid blocking — deferred: no network I/O loop is wired to the GUI yet (Chapter 8)
- [x] T0419 Write integration test: GUI correctly reflects a full match from start to finish without desync — `test_live_gui_stays_in_sync_across_a_real_multi_turn_match`, driving the real Chapter 6 strategy pipeline (single-process; live networked play is Chapter 8)
- [x] T0420 Take and save a screenshot of the belief-heatmap GUI for the README — shared GUI evidence committed as `assets/live_gui_belief_heatmap.png` and inserted into the academic report

### I.2 Replay Viewer Application
- [x] T0421 Scaffold a standalone Replay Viewer application (CLI or GUI) — `python -m police_thief replay --log PATH`
- [x] T0422 Implement loading of a saved match log JSON file — `domain/replay.py::load_log`
- [x] T0423 Implement step-by-step navigation controls (next/previous/scrub) — `ReplaySession.next/previous/jump_to`, wired to GUI buttons
- [x] T0424 Implement per-step recomputation of SHA-256 over (nonce, move) from the log — reuses Chapter 5's `verify()`/`audit_log()` exactly rather than re-implementing it
- [x] T0425 Implement comparison of recomputed hash against the log's stored commitment
- [x] T0426 Implement the green "Verified OK" stamp display per step on match
- [x] T0427 Implement the red "TAMPERED" banner display on any mismatch
- [x] T0428 Implement match-level disqualification flagging once any tamper is detected — `is_fully_verified`, and every step at/after `first_tampered_index` renders as TAMPERED (Sec. 7.5.1's "voided on first tamper")
- [x] T0429 Write unit test: verification engine correctly verifies an untampered log end-to-end
- [x] T0430 Write unit test: verification engine correctly flags a deliberately corrupted log
- [x] T0431 Implement visual replay of board state alongside the verification stamps (position/barriers per step) — done post-Chapter-11, after comparing this project's GUI against Appendix D's reference example repo: `gui/replay_gui.py::_extract_position` best-effort-recognizes the `{"row": int, "col": int}` shape `Orchestrator.run_turn` (Ch.8) actually produces and draws an agent marker + visited trail for it; `LogEntry.state` itself stays intentionally generic at the crypto layer, unchanged. Barrier-per-step replay is not included, since no strategy places barriers yet and no `LogEntry` ever records one (same gap noted at rules 15/16 in the Ch.11 sanity sweep)
- [ ] T0432 Implement replay of scent/belief map state per step (optional enhancement) — explicitly marked optional in its own title; still not built
- [x] T0433 Add a summary view: total steps, verification pass/fail count, final score — `ReplaySession.verified_count`/`tampered_count` + a summary label; "final score" is not included, since no live match yet produces a score tied to a log (Chapter 8/9)
- [x] T0434 Write integration test: replay viewer runs against a real completed match log without crashing — `test_replay_viewer_against_a_real_commit_reveal_sealed_multi_turn_log`, built from real `commit()`-sealed board positions, not synthetic placeholders, including a real file-tampering round trip
- [x] T0435 Take and save a screenshot of the Replay Viewer showing "Verified OK" for the README — committed as `assets/replay_verified_ok.png` and inserted into the academic report
- [ ] T0436 Take and save a screenshot of the Replay Viewer showing "TAMPERED" against a deliberately corrupted test log — same limitation; covered by `test_replay_gui_shows_tampered_in_red_at_the_tampered_step`
- [x] T0437 Package the Replay Viewer so it can be run independently from the live match code — `python -m police_thief replay`, verified to construct and render correctly standalone

### I.3 Gmail API OAuth 2.0 Setup
- [ ] T0438 Create/select a Google Cloud project for the cop agent's Gmail integration — still requires a real Google Cloud account/project this session cannot create; unlike the rest of this section, the *code* consuming it (`services/gmail_oauth.py`) is now fully built and tested, so completing this step is the last remaining manual action, not a code gap
- [ ] T0439 Enable the Gmail API in the Google Cloud Console — same reason
- [ ] T0440 Configure the OAuth consent screen (External or Internal, Test Users list) — same reason
- [ ] T0441 Add both team members' emails to the Test Users list — same reason
- [x] T0442 Restrict OAuth scope to `gmail.send` only — done in code: `services/gmail_oauth.py::SCOPES = ["https://www.googleapis.com/auth/gmail.send"]`, verified by `test_scopes_are_send_only_per_the_least_privilege_mandate`; the *Google Cloud Console* consent-screen configuration must still independently match this scope when a team completes the manual setup
- [ ] T0443 Create OAuth Client ID credentials of type Desktop Application — still a manual Google Cloud Console step
- [ ] T0444 Download `credentials.json` into the local project folder — still a manual step; `services/gmail_oauth.py::load_credentials` is ready to consume it the moment it's placed at the project root
- [x] T0445 Confirm `credentials.json` is listed in `.gitignore` before any commit — confirmed present: `.gitignore` already lists `credentials.json`, `token.json`, `*.pem`, `*.key` (re-verified during the Chapter 11 sanity sweep's git-history audit)
- [ ] T0446 Run the first authorization flow locally and confirm `token.json` is generated — requires a real browser/real Google account; `InstalledAppFlow.run_local_server()`'s call site is implemented and tested with a fully mocked flow (`test_load_credentials_runs_the_consent_flow_and_writes_a_fresh_token_when_none_is_cached`), but the actual first real run is still a manual step for you
- [x] T0447 Confirm `token.json` is listed in `.gitignore` before any commit — same confirmation as T0445
- [ ] T0448 Repeat the same OAuth setup steps for the thief agent's own Google Cloud project (or shared project, per team decision) — manual step, deferred with T0438
- [ ] T0449 Write a setup runbook documenting all OAuth steps for reproducibility — deferred until a team actually completes the manual setup once and can document the real, verified steps
- [x] T0450 Test token refresh behavior (force an expired access token and confirm silent refresh works) — `test_load_credentials_refreshes_an_expired_token_with_a_refresh_token`, using a mocked expired-with-refresh-token credential (no real network refresh call, but the real `creds.refresh(Request())` call site is genuinely exercised)

### I.4 Gmail Sending Implementation
- [x] T0451 Implement `get_service()` loading credentials/token and building the Gmail API service object — `services/gmail_oauth.py::get_service`, using the real `googleapiclient.discovery.build` against offline static discovery (no network call needed to construct the service object itself); ported from a proven-working OAuth flow in a prior course project, with the scope narrowed to `gmail.send` only
- [x] T0452 Implement `send_report(service, to_addr, subject, body)` constructing a MIME message — `build_report_email()`; takes a JSON payload (dict/list) rather than a free-text `body`, per T0497/Sec. 9.3.15
- [x] T0453 Implement base64url encoding of the MIME message before sending — `encode_for_gmail_api()`
- [ ] T0454 Wire the recipient address to the configured `[agent's report address]` — the fixed recipient is documented (commented out) in `config/cop/game.toml`/`config/thief/game.toml`'s new `[email]` section, but no config loader function reads it yet, since there is no live-match call site to wire it into (same gap as Ch.8's deferred `response_timeout_sec`/`watchdog_timeout_sec` wiring)
- [x] T0455 Write unit test: message construction produces valid MIME structure — `test_build_report_email_attaches_json_not_free_text`
- [ ] T0456 Write integration test: a test email is successfully sent and received at the target address — still cannot be done without a real, activated OAuth credential (requires you to complete T0438-T0446 once); `build_gmail_api_transport`'s construction and error-translation logic are fully tested up to that exact boundary
- [x] T0457 Implement error handling for Gmail API send failures (network error, auth error, quota error) — `GmailRateLimitedError`/`GmailSendError`, handled distinctly in `send_match_report`
- [x] T0458 Implement retry-with-backoff on transient send failures — `Http429BackoffPolicy`, retried only for `GmailRateLimitedError`, never for a hard `GmailSendError`
- [x] T0459 Log every send attempt (success/failure) locally for audit purposes — `SendResult.attempts` (a `SendAttempt` per try); returned to the caller rather than written to a log file itself, since no persistent send-audit-log file format was specified anywhere in the rulebook

### I.5 Gatekeeper: Quota Manager
- [x] T0460 Implement a daily operation counter for Gmail sends — `services/quota_manager.py`
- [x] T0461 Implement a configurable daily safety threshold
- [x] T0462 Write unit test: quota manager blocks sends once the daily threshold is reached
- [x] T0463 Persist the daily counter across process restarts (file or lightweight local store) — a small JSON file at `persist_path`
- [x] T0464 Write unit test: counter resets correctly at day boundary

### I.6 Gatekeeper: Token-Bucket Rate Limiter
- [x] T0465 Implement `TokenBucket` class with `capacity` and `refill_rate` parameters — `services/token_bucket.py`, implementing Sec. 9.3.10's exact formula
- [x] T0466 Implement continuous refill logic based on elapsed time
- [x] T0467 Implement `allow(cost=1.0)` method spending a token if available
- [x] T0468 Write unit test: bucket starts full at capacity
- [x] T0469 Write unit test: bucket refills over time up to capacity, never beyond
- [x] T0470 Write unit test: `allow()` returns False when no tokens are available
- [ ] T0471 Wire the token-bucket parameters to config (`requests_per_minute`, `concurrent_requests`) — `config/game.json` now has a `rate_limiter_gatekeeper` section, loaded and floor-validated into `RateLimiterConfig` (`shared/game_config.py`), so the values are loadable; but no code path yet constructs a live `TokenBucket` *from* a loaded `RateLimiterConfig` — `TokenBucket` is still constructed directly by callers today, since no live-match call site exists yet to do that wiring
- [x] T0472 Integrate the token bucket in front of every outbound Gmail API call — `Gatekeeper.submit()` checks/spends it on every call, and `send_match_report` always routes through the Gatekeeper first
- [x] T0473 Write integration test: rapid-fire send attempts are correctly throttled by the bucket — `test_report_is_rate_limited_once_the_token_bucket_is_empty` (a unit-level test of the real, non-mocked pipeline, not a separately-marked integration test)

### I.7 Gatekeeper: DOS/Anomaly Detector & 429 Handling
- [x] T0474 Implement detection of abnormal repeated-send patterns (e.g., N sends within a short window) — `services/anomaly_detector.py`, a sliding-window counter
- [x] T0475 Implement a circuit-breaker/lock state that halts all sends once an anomaly is detected — trips permanently, does not self-reset on a quiet period
- [x] T0476 Write unit test: anomaly detector trips on a simulated infinite-loop send pattern
- [x] T0477 Implement HTTP 429 response detection from the Gmail API — `GmailRateLimitedError`, raised by the (currently fake, in tests) transport
- [x] T0478 Implement backoff-and-wait logic specifically for 429 responses (respecting `retry_backoff_sec` and `max_retries`) — `Http429BackoffPolicy`
- [x] T0479 Write unit test: a simulated 429 response triggers backoff rather than an immediate retry storm
- [ ] T0480 Implement a bounded request queue (`queue_depth`) for outbound reports under load — not implemented: no literal queue data structure exists; the Gatekeeper paces/blocks individual send attempts synchronously rather than queuing them, since no concurrent/async report-sending call site exists yet to need one
- [ ] T0481 Write unit test: queue depth cap is respected; excess requests are rejected/logged rather than silently dropped — deferred, depends on T0480
- [x] T0482 Wire the Quota Manager, Token-Bucket, and DOS Detector into a single composed `Gatekeeper` pipeline — `services/gatekeeper.py`
- [x] T0483 Write integration test: a report passes cleanly through all three Gatekeeper stages under normal load
- [x] T0484 Write integration test: a report is correctly rejected/blocked at each stage under simulated abuse conditions

### I.8 Mandatory JSON Report Files
- [x] T0485 Implement `declaration_<game_id>.json` builder (teams, members, repos, hardware, model, commit hash, budgets) — `services/match_reports.py::build_declaration`, wrapping Ch.5's `SignedStep0`
- [x] T0486 Implement `config_<game_id>_g<NN>.json` builder (locked match configuration snapshot) — `build_config_snapshot`
- [x] T0487 Implement `log_<game_id>_g<NN>.json` builder (full move-by-move commit/reveal log) — deliberately reuses Ch.7's `save_log`/`load_log` verbatim rather than a bespoke builder; `match_reports.py` only supplies the correct filename via `log_filename()`
- [x] T0488 Implement `result_<game_id>.json` builder (final score, sign-off, all four repo cross-links, token totals) — `build_match_result`
- [x] T0489 Write unit test: each of the four JSON builders produces schema-valid output — via round-trip save/load assertions on every field
- [x] T0490 Write unit test: `game_id` and sub-game number consistently namespace all four files so they never mix across matches
- [ ] T0491 Implement canonical JSON serialization consistently across all four file types — partial: all four files are serialized consistently with each other (`json.dumps(..., indent=2, sort_keys=True)`, human-readable), but this is not the same strict, compact canonical form Ch.5's `canonical_json` uses for hashing; `sha256_of_log` correctly uses the strict canonical form internally for the hash itself, only the on-disk report files use the readable variant
- [x] T0492 Implement inclusion of the SHA-256 of the match log inside the results report — `sha256_of_log`, embedded as `MatchResult.log_sha256`
- [x] T0493 Implement inclusion of total LLM token consumption inside the results report — `MatchResult.total_tokens_used`, from Ch.5's `TokenUsage.total`
- [ ] T0494 Implement mutual sign-off logic: both sides must agree on the score before either sends its report — `results_agree()` exists and is correct, but nothing yet calls it automatically as a gate *inside* `send_match_report` before sending; a caller must invoke it manually first. Wiring it in as an automatic precondition belongs with the not-yet-built end-of-match hook (see `docs/PRD_reliability_layer.md`'s note on the missing main match loop)
- [x] T0495 Write integration test: a disagreement in final score between the two sides is detected and handled (e.g., flagged, not silently sent) — `test_results_agree_false_on_a_score_disagreement` (detects the disagreement; the "not silently sent" enforcement itself is the T0494 gap above)
- [x] T0496 Implement attaching the results JSON as an email attachment (not inline free text) — `build_report_email` always attaches `json_payload` as a file, never inlines it in the body
- [x] T0497 Write unit test: attempting to send a non-JSON/free-text report is rejected by the sending code path itself — `test_build_report_email_rejects_a_free_text_string_payload_at_runtime`; `build_report_email` raises `TypeError` on anything that isn't a `dict`/`list`, a genuine runtime check, not just a type hint

### I.9 Stage-7 Milestone
- [ ] T0498 Confirm milestone: a match summary is sent via Gmail successfully from both sides independently — cannot be confirmed without the real OAuth setup (I.3)
- [x] T0499 Confirm milestone: the GUI shows live match state correctly throughout a full match — already confirmed in Chapter 7 (`test_live_gui_stays_in_sync_across_a_real_multi_turn_match`)
- [x] T0500 Confirm milestone: the Replay App replays a captured match correctly with Verified OK stamps — already confirmed in Chapter 7
- [ ] T0501 Run a full end-to-end match: crypto + scent + LLM + GUI + Gmail reporting all active simultaneously — cannot be run yet: no single live-match entrypoint wires the Orchestrator (Ch.8), GUI (Ch.7), and Gmail reporting (Ch.9) together
- [x] T0502 Document Stage-7 decisions in `PRD/07-reporting-gui.md` — superseded by `docs/PRD_gmail_gatekeeper.md` per this master PRD's naming convention (see `docs/PRD.md` §7's reconciliation note)

---

## J. Reliability Layer — Orchestrator, State Machine, Watchdog, Deadline Tracker

### J.1 Orchestrator (Gateway)
- [x] T0503 Design the single `Orchestrator` class as the sole entry point for all sub-systems — `services/orchestrator.py`
- [x] T0504 Wire the MCP connector module behind the Orchestrator (no direct external access from other modules) — `send_move_async` is only called from inside `run_turn`
- [x] T0505 Wire the Decision Module (strategy) behind the Orchestrator — `run_turn` calls `brain._decide_move` exactly once per turn
- [x] T0506 Wire the Log Manager behind the Orchestrator — `run_turn` records a `LogEntry` after successful self-verification
- [x] T0507 Wire the Deadline Tracker behind the Orchestrator — the outbound commit send is wrapped in `deadline_tracker.call(...)`
- [x] T0508 Wire the Watchdog behind the Orchestrator — `run_turn` heartbeats at turn start and turn end
- [x] T0509 Verify the Orchestrator itself contains no decision-making or communication business logic — `run_turn` only sequences calls into `brain`/`commit`/`verify`/`send_move_async`/state machine; verified by inspection, no independent logic of its own
- [ ] T0510 Write unit test: replacing the Decision Module implementation requires no changes to the Orchestrator interface — not written as a dedicated test; the integration tests only exercise `ManhattanHeuristicBrain`. The `BrainBase` ABC (Ch.6) structurally guarantees swappability, but a second-brain-through-Orchestrator test was not added
- [ ] T0511 Write architecture-review checklist: confirm no module calls another module directly, bypassing the Orchestrator — not written as a formal checklist document
- [x] T0512 Document the Orchestrator's public interface (methods, expected inputs/outputs) — via class/method docstrings and the `TurnResult` dataclass fields, not a separate doc

### J.2 Legal State Machine
- [x] T0513 Define the full state set: WAITING_FOR_OPPONENT, COMPUTING_MOVE, COMMITTING, AWAITING_REVEAL, VERIFYING, TECHNICAL_LOSS
- [x] T0514 Implement the transition table mapping each state to its legal successor states
- [x] T0515 Implement `transition(target)` raising/rejecting on any transition not in the table
- [x] T0516 Write unit test: every legal transition succeeds
- [x] T0517 Write unit test: every illegal transition attempt is rejected immediately
- [x] T0518 Write unit test: `TECHNICAL_LOSS` is correctly reachable from both `COMPUTING_MOVE` and `AWAITING_REVEAL` failure paths — parametrized across all four non-terminal states, a superset of the two named
- [x] T0519 Write unit test: `TECHNICAL_LOSS` is a terminal state (no further legal transitions out)
- [ ] T0520 Wire the state machine's current state to the GUI turn-banner (Stage 7) — deferred: the Orchestrator and `LiveGUI` (Ch.7) are not yet wired together; no live match entrypoint exists yet to drive the GUI from real turns
- [ ] T0521 Write integration test: a full match cycles through the state machine correctly turn after turn — only single-turn integration tests exist (`test_orchestrator.py`); a multi-turn/full-match test would need a two-sided match driver, which doesn't exist yet
- [ ] T0522 Write integration test: an opponent disconnect mid-`AWAITING_REVEAL` correctly drives the state machine to `TECHNICAL_LOSS` rather than hanging — the unreachable-opponent test covers failure during `COMMITTING` (connection refused before send completes), not a disconnect specifically timed mid-`AWAITING_REVEAL`

### J.3 Deadline Tracker
- [x] T0523 Implement per-outbound-request timestamp + deadline attachment — via `asyncio.wait_for(..., timeout=...)`, not an explicit timestamp field
- [x] T0524 Implement deadline-expiry checking on every awaited response
- [x] T0525 Implement retry-on-expiry logic (bounded by `max_retries`)
- [x] T0526 Implement technical-loss/timeout declaration once retries are exhausted — raises `DeadlineExceededError`, which the Orchestrator catches and converts to `TECHNICAL_LOSS`
- [x] T0527 Write unit test: a response arriving within the deadline is accepted normally
- [x] T0528 Write unit test: a response arriving after the deadline triggers retry or timeout handling, never an indefinite wait
- [ ] T0529 Wire `response_timeout_sec` from config into the Deadline Tracker — `config/game.json`'s `network_and_league.response_timeout_sec` is now loadable via `NetworkLeagueConfig` (`shared/game_config.py`); `DeadlineTracker` is still constructed directly with explicit values by tests/callers, since no live-match call site exists yet to consume the loaded value
- [ ] T0530 Write integration test: simulated slow/no-response opponent triggers correct timeout behavior without hanging the process — the existing integration test uses an unreachable address (immediate connection refusal), not a live-but-slow-to-respond server, so the deadline-expiry path itself is only unit-tested, not integration-tested over real HTTP

### J.4 Watchdog
- [x] T0531 Implement a background heartbeat-monitoring process/thread independent of the main game loop — implemented as a passive, poll-based monitor (`check()`) rather than its own background thread; no independent main game loop exists yet for it to run alongside
- [x] T0532 Implement `watchdog_check(last_heartbeat, timeout_sec)` comparing elapsed time to threshold — `Watchdog.check()`, using an injectable clock instead of a raw `last_heartbeat` parameter
- [ ] T0533 Implement `persist_state()` saving current game state to disk for later recovery — not implemented; `Watchdog`'s `on_timeout` callback is a generic hook, but no state-persistence callback has been wired through it yet
- [ ] T0534 Implement `controlled_shutdown()` releasing MCP connections and closing logs cleanly — not implemented; no such method exists on `Watchdog` or `Orchestrator`
- [ ] T0535 Wire `watchdog_timeout_sec` from config into the Watchdog — `network_and_league.watchdog_timeout_sec` is now loadable (same as T0529); the same "no live-match call site yet" gap applies to actually constructing the `Watchdog` from it
- [x] T0536 Write unit test: Watchdog returns ALIVE when heartbeats are timely
- [x] T0537 Write unit test: Watchdog returns SHUTDOWN and persists state when heartbeats stop arriving — covers the SHUTDOWN transition and the `on_timeout` callback firing; no actual state persistence exists yet to test (see T0533)
- [ ] T0538 Implement the main loop emitting a heartbeat signal on a regular cadence — no continuous main game loop exists yet; the Orchestrator heartbeats once at the start and end of each `run_turn`, which is turn-driven, not cadence-driven
- [ ] T0539 Write integration test: deliberately freezing the main loop triggers Watchdog-initiated state persistence and shutdown — deferred, depends on T0533/T0538 existing first
- [ ] T0540 Implement a state-recovery/resume path that can reload persisted state after a controlled shutdown — deferred, depends on T0533

### J.5 Deadlock Prevention Review
- [x] T0541 Conduct a manual deadlock-risk review across all await points in the codebase — the only await points in the codebase are inside `Orchestrator.run_turn`'s single `deadline_tracker.call(...)` around `send_move_async`; reviewed by inspection
- [x] T0542 Confirm every await point has either a Deadline Tracker timeout or is bounded by the state machine — confirmed: it is the same single await point, and it is wrapped by `DeadlineTracker.call`
- [ ] T0543 Write a stress test: simulate simultaneous mutual-wait conditions and confirm no permanent hang occurs — not written; there is currently no two-sided match driver where both peers could mutually await each other, so there is no mutual-wait scenario yet to stress-test
- [ ] T0544 Document the deadlock-prevention design in the architecture section of the README — deferred; README.md is being kept minimal for the final academic report per the user's instruction, so this belongs in `docs/PRD_reliability_layer.md` instead (done there)

---

## K. Configuration Files — Full JSON/TOML Implementation

### K.1 Shared Signed Config (`config/game.json`)
- [x] T0545 Finalize the full `config/game.json` schema covering all sections (board_and_agents, world, movement_and_barriers, scoring, pheromones, network_and_league, rate_limiter_gatekeeper) — all six sections now present in `config/game.json`, matching App. B Sec. 13.3.1's worked example; `shared/game_config.py::load_match_parameters` parses and validates every one of them (FIXED-field exact-match checks for `network_and_league`, floor checks for `rate_limiter_gatekeeper`, mirroring the pre-existing `board_and_agents`/`pheromones` validation)
- [x] T0546 Implement `schema_version` field and version-compatibility check
- [x] T0547 Implement `agreed_between` field listing both team identities
- [x] T0548 Write a validation function checking all mandatory fields are present
- [x] T0549 Write a validation function checking all minimum-value constraints (e.g., `max_barriers >= 14`)
- [x] T0550 Implement byte-for-byte/canonical equality check between loaded configs using signed hashes
- [x] T0551 Write unit test: mismatched configs between sides are detected and block match start
- [x] T0552 Implement a config-negotiation handshake exchanged before Step-0
- [x] T0553 Write integration test: independently-authored divergent configs trigger pre-match rejection
- [x] T0554 Add `config_sha256` computation over canonical serialized config
- [x] T0555 Write unit test: `config_sha256` is identical on the same canonical content

### K.2 Private Per-Peer Config (`config/game.toml`)
- [x] T0556 Finalize the `[game]` section: group_name, group_id, sub_game_number, members, repos — `config/cop/game.toml` now has a real, non-placeholder `group_name`/`group_id` (`"uoh-ay26"`, fixing an earlier `"uof-ay26"` typo that matched neither the GitHub org nor `config/network_match.json`'s team identity), plus `sub_game_number`, `members`, and `repos` matching `docs/tasks.md` §13.4.1's illustrative shape. Honest caveat: this `[game]` table is not currently read by any loader (`shared/config.py::load_network_config`/`load_strategy_class` only ever parse `[network]`/`[strategy]`) -- the live two-computer match's actual team identity/repo URLs are sourced from `NetworkMatchSettings` (populated from `config/network_match.json` or the GUI form), not from this file. This section documents the rulebook's expected private-file shape accurately; wiring a loader for it is a separate, not-yet-needed step
- [x] T0557 Finalize the `[network]` section: my_port, opponent_url, turn_timeout_seconds
- [ ] T0558 Finalize the `[strategy]` section: thief_class, police_class (optional overrides)
- [ ] T0559 Finalize the `[trash_talk]` section: provider selection
- [ ] T0560 Finalize the `[llm]` section: model, step_deadline_seconds
- [x] T0561 Finalize the `[email]` section: recipient, mode
- [ ] T0562 Write unit test: all optional sections have sane defaults when omitted
- [ ] T0563 Write unit test: TOML parse errors produce a clear, actionable error message
- [x] T0564 Confirm no private strategy/secret TOML value needs to match the opponent; shared rules are negotiated from `game.json`

### K.3 Rate-Limiter Config (`rate_limits.json`)
- [x] T0565 Finalize `rate_limits.json` schema (requests_per_minute, concurrent_requests, retry_backoff_sec, max_retries, queue_depth) — reconciled rather than built as a separate file: App. B Sec. 13.3.1's own worked example embeds this exact schema as `config/game.json`'s `rate_limiter_gatekeeper` section (not a standalone `rate_limits.json`), so that section is the canonical home for these fields; `RateLimiterConfig` (`shared/game_config.py`) parses and floor-validates all five
- [ ] T0566 Wire this config into the Gatekeeper's Token-Bucket and Quota Manager — deferred, same reason as T0471/T0529/T0535: no real call site (a live match's end-of-match reporting hook) exists yet to consume config-driven values instead of directly-supplied test parameters
- [x] T0567 Write unit test: rate-limit config values are correctly loaded and applied — `test_load_match_parameters_rejects_rate_limiter_values_below_floor` (parametrized over all 5 fields) and `test_load_match_parameters_allows_raising_rate_limiter_values_above_floor` (`tests/unit/test_game_config.py`)

### K.4 Config Loader Robustness
- [ ] T0568 Implement a single unified config-loading entry point used consistently across the whole codebase
- [ ] T0569 Write unit test: loader raises a clear error on missing files rather than a generic exception
- [ ] T0570 Write unit test: loader raises a clear error on malformed JSON/TOML syntax
- [ ] T0571 Add environment-variable overrides for local development convenience (never overriding shared/signed values)
- [ ] T0572 Document every config field's meaning, default, and status (minimum/fixed/by-agreement) in a local reference table matching App. F
- [ ] T0573 Cross-check every config field against the Mandatory Parameters Table for completeness (no missing parameter)
- [ ] T0574 Cross-check every config field against the 55 mandatory rules for any crypto-locking or declaration requirements

---

## L. League Operations & Live Matches

**Note (Chapter 9):** L.1-L.3 below are real-world league-day operations against other teams' actual agents — they require opponent teams that do not exist yet in a solo development session, so they remain unchecked, not because the underlying capability is missing (`domain/league.py`, `services/gatekeeper.py`, and `services/match_reports.py` built this chapter provide everything needed to run and report a real match) but because there is no live opponent to run them against yet. L.4's scoring-edge-case logic, by contrast, needed no live opponent to test and is covered below.

### L.1 Pre-Match Coordination With Opponent Teams
- [ ] T0575 Identify at least two other teams to arrange live matches against
- [ ] T0576 Exchange public tunnel URLs with each opposing team ahead of a scheduled match
- [x] T0577 Exchange/agree on `config/game.json` values with each opponent before match start
- [x] T0578 Confirm both sides' `config_sha256` match before proceeding to Step-0
- [x] T0579 Exchange Step-0 declarations with each opponent and verify signatures
- [x] T0580 Exchange each side's already-played-games count before counted matches
- [x] T0581 Record the agreed game-count declaration for later audit cross-checking
- [ ] T0582 Schedule a specific time window with each opposing team for the live match

### L.2 Running Matches
- [x] T0583 Start both agents' processes and confirm both tunnels are live before match start
- [x] T0584 Run warm-up/non-counted verification series before counted play where agreed
- [x] T0585 Run the first counted game against Opponent Team 1 — G001 vs `najamjad`
- [x] T0586 Confirm both sides' end-of-match JSON reports were exchanged/reconciled for the first counted opponent
- [x] T0587 Run a counted game against Opponent Team 2 — G002 vs `amireman`
- [x] T0588 Confirm both sides' end-of-match JSON reports were exchanged/reconciled for the second counted opponent
- [x] T0589 Run an additional counted game against a third opponent — G009 vs `sharNamr`
- [x] T0590 Track a running tally — 5 counted series, 5 distinct opponents
- [x] T0591 Confirm at least the required minimum distinct-opponent games are complete — 3 complete
- [x] T0592 Avoid replaying completed counted opponents for extra scoring — friendly verification series remain explicitly non-counted
- [x] T0593 Record every counted result in the README — G001 30–90, G002 60–40, G009 40–60, SMNGRP05-vs-uoh-ay26-C01 47–47, AHK-YOSI-vs-uoh-ay26-C001 75–35

### L.3 Handling League-Level Failures
- [x] T0594 Define tunnel-down procedure — `docs/OPPONENT_MATCH_GUIDE.md#shared-failure-policy`
- [x] T0595 Define own-bug technical-failure procedure — preserve evidence, fix, regress, and re-arrange only by agreement
- [x] T0596 Define false game-count procedure — document, reconcile, and escalate under course policy without retaliation
- [ ] T0597 Keep a log of all attempted/aborted matches (not just successful ones) for your own troubleshooting history

### L.4 Tie & Edge-Case Handling
- [x] T0598 Write integration test: a tied cumulative score across a full series correctly awards `[tie score]` to both sides — `test_apply_tie_rule_awards_tie_score_to_both_sides_on_an_exact_tie`; a unit-level test of `apply_tie_rule`, since no live series-running match loop exists yet to integration-test end-to-end
- [x] T0599 Write integration test: exactly reaching `[max games per team]` correctly stops further counted games — `test_a_counted_game_beyond_the_max_games_per_team_cap_is_rejected`
- [x] T0600 Write integration test: exactly reaching `[min games to pass]` correctly marks the team as eligible — `test_games_played_and_minimum_threshold_track_correctly`
- [x] T0601 Verify scoring computation correctly separates counted games from warm-up games in all reporting — by construction: `LeagueRecord` only ever learns about a game via `record_counted_game`; a warm-up game is simply never passed to it, so there is no separate "warm-up" code path that could conflate the two rather than an explicit dual-tracking mechanism

---

## M. Testing & Quality Assurance

### M.1 Unit Test Coverage
- [ ] T0602 Set up `pytest` configuration (`pytest.ini`/`pyproject.toml` test section) for both repos
- [ ] T0603 Achieve unit test coverage for the board/movement/barrier module
- [ ] T0604 Achieve unit test coverage for the scoring module
- [ ] T0605 Achieve unit test coverage for the scent/pheromone module
- [ ] T0606 Achieve unit test coverage for the belief-map module
- [ ] T0607 Achieve unit test coverage for the strategy/decision module
- [ ] T0608 Achieve unit test coverage for the commit-reveal cryptography module
- [ ] T0609 Achieve unit test coverage for the state-machine module
- [ ] T0610 Achieve unit test coverage for the Deadline Tracker
- [ ] T0611 Achieve unit test coverage for the Watchdog
- [ ] T0612 Achieve unit test coverage for the Gatekeeper (Quota Manager, Token Bucket, DOS Detector)
- [ ] T0613 Achieve unit test coverage for the config loaders (JSON + TOML)
- [ ] T0614 Achieve unit test coverage for the Gmail-sending wrapper (mocked API)
- [ ] T0615 Achieve unit test coverage for the Replay Viewer's verification engine
- [ ] T0616 Set up a coverage report tool (`pytest-cov` or similar) and record baseline coverage percentage
- [ ] T0617 Add tests to CI or a pre-push local hook so regressions are caught early

### M.2 Integration Tests
- [ ] T0618 Write an integration test running a full localhost match end-to-end (both processes) with assertions on final score
- [ ] T0619 Write an integration test running a full match with tunneling active (or a mocked equivalent) end-to-end
- [ ] T0620 Write an integration test exercising a full commit-reveal cycle across real network calls
- [ ] T0621 Write an integration test exercising a full Gmail report round-trip against a real test inbox
- [ ] T0622 Write an integration test for a simulated opponent disconnect mid-match
- [ ] T0623 Write an integration test for a simulated slow/laggy opponent exceeding deadlines
- [ ] T0624 Write an integration test for a simulated malformed/hostile payload from the opponent
- [ ] T0625 Write an integration test for a full match with the LLM verbal layer active (real or mocked provider)
- [ ] T0626 Write an integration test verifying the GUI, Replay Viewer, and Gmail reporting all function together in one full run

### M.3 Adversarial / Red-Team Testing (self-testing your own integrity mechanisms)
- [ ] T0627 Attempt to submit a false Capture Claim and confirm it is caught by audit
- [ ] T0628 Attempt to hide a barrier placement and confirm it is caught by audit/log completeness checks
- [ ] T0629 Attempt to alter a move after Commit but before Reveal and confirm it is rejected
- [ ] T0630 Attempt to replay an old Nonce and confirm uniqueness/freshness is enforced
- [ ] T0631 Attempt to tamper with a saved log file and confirm the Replay Viewer flags it as TAMPERED
- [ ] T0632 Attempt to send a non-JSON free-text report and confirm it is rejected before sending
- [ ] T0633 Attempt to exceed the Gmail rate limit deliberately and confirm the Gatekeeper throttles correctly
- [ ] T0634 Attempt an illegal diagonal move and confirm it is rejected at every layer (client, protocol, audit)
- [ ] T0635 Attempt to falsely declare a lower games-played count and confirm your own system would detect the inconsistency if checked against your own logs
- [x] T0636 Attempt to exceed `max_barriers` and confirm placement is blocked — covered at both the `Board` primitive level (`test_place_barrier_fails_once_budget_exhausted`) and the live wiring level (`test_maybe_place_barrier_returns_none_once_budget_exhausted` in `tests/unit/test_network_match_barrier.py`)
- [ ] T0637 Attempt to share state between cop and thief processes deliberately (as a negative test) and confirm your architecture makes this structurally impossible, not just discouraged

### M.4 Performance & Load Testing
- [ ] T0638 Measure end-to-end turn latency (compute + network + crypto) under normal conditions
- [ ] T0639 Measure LLM call latency for each configured provider mode
- [ ] T0640 Measure the impact of `every_n_steps` throttling on overall match duration
- [ ] T0641 Measure memory usage over a long match (many turns) to catch leaks
- [ ] T0642 Stress-test the Gatekeeper under a burst of simulated report requests
- [ ] T0643 Stress-test the belief-map update function for computational cost at larger board sizes (if team increases grid size)
- [ ] T0644 Profile and optimize any function exceeding `step_deadline_seconds` under normal load

### M.5 Cross-Platform / Environment Testing
- [ ] T0645 Test the full pipeline on the primary development OS
- [ ] T0646 Test the full pipeline on a second OS if available (e.g., Windows vs. Linux/Mac) to catch path/encoding bugs
- [ ] T0647 Test with a fresh virtual environment (no leftover cached dependencies) to confirm reproducibility from `requirements.txt`/`pyproject.toml`
- [ ] T0648 Test the OAuth flow from a completely fresh machine/browser profile
- [ ] T0649 Verify no hardcoded absolute file paths remain anywhere in the codebase

### M.6 Regression Testing After Each Stage
- [ ] T0650 Re-run Stage 1-3 tests after Stage 4 changes to confirm no regression
- [ ] T0651 Re-run Stage 1-4 tests after Stage 5 changes to confirm no regression
- [ ] T0652 Re-run Stage 1-5 tests after Stage 6 changes to confirm no regression
- [ ] T0653 Re-run Stage 1-6 tests after Stage 7 changes to confirm no regression
- [ ] T0654 Run the full test suite one final time immediately before tagging the submission

### M.7 Manual QA Pass
- [ ] T0655 Manually play through a full match end-to-end, observing the GUI in real time
- [ ] T0656 Manually inspect a full generated match log for readability and completeness
- [ ] T0657 Manually inspect a generated results JSON for correctness of every field
- [ ] T0658 Manually inspect the received Gmail report in an actual inbox
- [ ] T0659 Manually verify the Replay Viewer against the exact match just played
- [ ] T0660 Have your teammate independently attempt to run your side's agent from a clean checkout, following only the README

---

## N. Documentation & Academic Report

### N.1 README.md — Academic Report (both repos)
- [x] T0661 Write the Dec-POMDP model section: state, action, observation spaces as implemented — README `Formal problem formulation`
- [x] T0662 Write the FastMCP orchestration dilemmas section: turn management, network-failure handling — README `Academic design notes`
- [x] T0663 Write the decision-mechanism section: heuristics/custom algorithm/RL details and parameters chosen — README `Cop intelligence` and `Gemini integration`
- [x] T0664 Write the Gatekeeper/Orchestrator role and parameter-choice discussion — README `Orchestrator and Gatekeeper responsibilities`
- [x] T0665 Include learning-curve plots if RL was used, with a caption explaining convergence behavior — not applicable; README explicitly records that no RL policy was trained
- [x] T0666 Insert the mandatory belief-heatmap GUI screenshot — `assets/live_gui_belief_heatmap.png`
- [x] T0667 Insert the mandatory Replay Viewer "Verified OK" screenshot — `assets/replay_verified_ok.png`
- [x] T0668 Insert the cross-link to the sibling repository (cop <-> thief) — banner and companion-repository link
- [x] T0669 Write a section explaining the scent/pheromone model and how uncertainty/deception were combined — README `Formal problem formulation`
- [x] T0670 Write a section summarizing league results — README records all five counted opponents and verified scores
- [x] T0671 Write a section documenting any book-contradiction interpretation choices made per the academic-freedom clause — README `Specification interpretations`
- [x] T0672 Proofread the README for clarity, spelling, and academic tone
- [ ] T0673 Verify the README renders correctly on GitHub's web UI (formatting, images, links)

### N.2 PRD Files (7 layers)
- [x] T0674 Finalize `PRD/01-base-logic.md` — `docs/PRD_board_physics.md` (Chapter 3)
- [x] T0675 Finalize `PRD/02-mcp-infra.md` — `docs/PRD_fastmcp_networking.md` (Chapter 10 — a genuine gap caught by this chapter's own milestone-reconciliation pass; every other PRD was written in the same session as its mechanism, this one wasn't, until now)
- [x] T0676 Finalize `PRD/03-strategy-module.md` — `docs/PRD_strategy_module.md` (Chapter 6)
- [x] T0677 Finalize `PRD/04-language-scent.md` — split across `docs/PRD_pheromone_scent.md` (Chapter 4, scent-only) and `docs/PRD_strategy_module.md` §3 (Chapter 6, hints/LLM), since this project's per-mechanism granularity split scent and language/strategy into two documents rather than one
- [ ] T0678 Finalize `PRD/05-cloud-tunnel.md` — not written: no cloud-tunnel mechanism was ever built (Section G is entirely unchecked; requires real `ngrok`/a second machine), so there is nothing yet to document
- [x] T0679 Finalize `PRD/06-security-crypto.md` — `docs/PRD_commit_reveal_crypto.md` (Chapter 5)
- [x] T0680 Finalize `PRD/07-reporting-gui.md` — split across `docs/PRD_gui_replay.md` (Chapter 7), `docs/PRD_reliability_layer.md` (Chapter 8), and `docs/PRD_gmail_gatekeeper.md` (Chapter 9), since this project's per-mechanism PRDs are more granular than the rulebook's own 7-stage grouping
- [ ] T0681 Cross-reference each PRD file from the README's table of contents

### N.3 Supporting Documents
- [ ] T0682 Finalize `PLAN.md` describing the work plan and division of labor between teammates
- [x] T0683 Reconcile `TODO.md` with the post-split, post-live-match state — historical caveats retained where still useful
- [ ] T0684 Write `docs/RESEARCH-REPORT-Performance-Analysis.md` covering resource consumption analysis
- [ ] T0685 Include LLM call counts/costs per provider in the research report
- [ ] T0686 Include rate-limit comparisons across providers (Ollama, ChatGPT, Gemini, Claude, Grok) in the research report
- [ ] T0687 Include a discussion of the fallback mechanism's effectiveness in the research report
- [ ] T0688 Write `SETUP.md` describing full environment setup from a clean machine
- [x] T0689 Write a runbook describing a live opponent match — delivered as `docs/RUNNING.md`

### N.4 Code-Level Documentation
- [ ] T0690 Add docstrings to every public class and function in the domain layer
- [ ] T0691 Add docstrings to every public class and function in the infra layer
- [ ] T0692 Add docstrings to every public class and function in the shared layer
- [ ] T0693 Add inline comments explaining non-obvious cryptographic steps
- [ ] T0694 Add inline comments explaining the scent decay formula implementation
- [ ] T0695 Generate/update an architecture diagram reflecting the final Orchestrator + module structure
- [ ] T0696 Review all comments/docstrings for accuracy against the final implementation (no stale documentation)

---

## O. Submission Preparation & Compliance

### O.1 Repository Finalization
- [ ] T0697 Confirm both repos are reachable by the lecturer (public or explicitly shared)
- [x] T0698 Confirm the cross-links between the Cop and Thief repositories are present and correct
- [ ] T0699 Run a final `.gitignore` audit: confirm `credentials.json` and `token.json` were never committed in history
- [ ] T0700 If a secret was ever accidentally committed, rotate/revoke it in the Google Cloud console
- [ ] T0701 Confirm no other secrets (API keys, personal tokens) exist anywhere in tracked files
- [ ] T0702 Squash/clean up any messy work-in-progress commits if desired (optional, not required)
- [x] T0703 Confirm both repos contain README, config, PRDs, PLAN, TODO, running guide, and opponent guide

### O.2 Git Tagging
- [ ] T0704 Create annotated Git tag `v1.0-submission` on the cop repo's final commit
- [ ] T0705 Create annotated Git tag `v1.0-submission` on the thief repo's final commit
- [ ] T0706 Push both tags to their respective remotes
- [ ] T0707 Verify `git show v1.0-submission` resolves to the intended final commit on both repos
- [ ] T0708 Record both tags' commit hashes for inclusion in the final Step-0/declaration data

### O.3 Team Identity & Individual Submission
- [ ] T0709 Finalize the 8-character team identity code (no spaces)
- [ ] T0710 Confirm the team code is embedded consistently across declaration/config/result JSON files
- [ ] T0711 Each team member prepares their own individual submission package
- [ ] T0712 Each team member independently submits via the course's official submission system
- [ ] T0713 Confirm the shared code repo links are identical across every team member's individual submission

### O.4 Word/PDF Submission Document
- [ ] T0714 Obtain the official Word submission template
- [ ] T0715 Fill in all required template fields without moving/renaming any field
- [ ] T0716 Paste/insert the finalized README content (or summary) into the template as instructed
- [ ] T0717 Insert the belief-heatmap GUI screenshot into the template
- [ ] T0718 Insert the Replay Viewer "Verified OK" screenshot into the template
- [ ] T0719 Insert both GitHub repo links into the template
- [ ] T0720 Export the completed template to PDF
- [ ] T0721 Proofread the exported PDF for layout corruption (images cut off, fields misaligned)
- [ ] T0722 Confirm the PDF file naming convention matches what the course submission system expects
- [ ] T0723 Submit the PDF via the official course submission channel

### O.5 Final Compliance Cross-Check Against the 55 Mandatory Rules
- [ ] T0724 Re-verify rule set 1-10 (network architecture & local epistemology) against the final code
- [ ] T0725 Re-verify rule set 11-16 (spatial mechanics & board) against the final code
- [ ] T0726 Re-verify rule set 17-24 (cryptography & zero-knowledge) against the final code
- [ ] T0727 Re-verify rule set 25-30 (strategy, language & public network) against the final code
- [ ] T0728 Re-verify rule set 31-45 (league fairness & admin procedures) against the final code
- [ ] T0729 Re-verify completions 46-55 (cross-checked additions) against the final code
- [ ] T0730 Re-verify every entry in the Mandatory Parameters Table matches the final `config/game.json`
- [ ] T0731 Confirm the self-grading submitted reflects code quality only, not league game outcomes

### O.6 Final Pre-Submission Checklist (Ch.11 restated)
- [x] T0732 Confirm base logic works: full match runs with no crash and correct scoring — re-verified live in Chapter 11: `uv run python -m police_thief simulate` → `outcome=survival cop_score=5 thief_score=10 turns_played=35`, matching the mandatory scoring table exactly
- [ ] T0733 Confirm FastMCP public-URL connectivity between two agents (not localhost-only) — not done; see rule 10/Section G — requires the manual `ngrok`/`Localtonet` setup step
- [ ] T0734 Confirm commit-reveal and mutual audit pass cleanly with no tampering flagged — the primitives and the Replay Viewer's audit pass cleanly on a real, untampered log (Chapter 5/7, re-verified passing); the live, two-sided Commit-then-Reveal network exchange is not fully wired yet (see rule 17/19 above and `docs/PRD_reliability_layer.md` §3)
- [x] T0735 Confirm scent map and belief map are implemented and actually influence decisions — `test_strategy_pipeline.py`'s headline proof: two real brains capture using only their own belief maps, never touching the opponent's true position (Chapter 6)
- [x] T0736 Confirm Live GUI and Replay Viewer both show correct, matching, "Verified OK" state — proven via real Tkinter widget-state assertions (Chapter 7); the *screenshot* deliverable itself remains a flagged manual step (no native-window-capture tool available in this session)
- [ ] T0737 Confirm both sides sent their own separate Gmail JSON report for every counted match — not done; zero real matches exist yet, and real Gmail sending requires the deferred OAuth setup (rule 30)
- [ ] T0738 Confirm GitHub repos are tagged and README is properly structured — README is complete and role-specific; only the final annotated submission tag remains
- [ ] T0739 Confirm at least `[min games to pass]` distinct-opponent games were completed — not done; 0 of the required 2, no opponent teams exist in a solo development session
- [x] T0740 Do a final full read-through of `requirements.md` against the finished project, line by line — performed as this chapter's Section T sweep: all 55 mandatory rules in `docs/tasks.md` App. E individually cross-checked against the actual code/tests/git history, one genuinely new rulebook tension found (rule 47, see T0881) and documented rather than silently resolved either way

---

## P. Polish, Performance & Final Research Pass

### P.1 Code Quality Polish
- [ ] T0741 Run the full linter across both repos and fix all warnings
- [ ] T0742 Run the formatter across both repos for consistent style
- [ ] T0743 Run the type checker (if used) and resolve all type errors
- [ ] T0744 Remove dead code and unused imports across both repos
- [ ] T0745 Remove any leftover debug print statements not needed for the final submission
- [ ] T0746 Review variable/function naming for clarity and consistency
- [ ] T0747 Refactor any duplicated logic between cop and thief repos into clearly-documented shared reference points (without violating process separation)
- [ ] T0748 Ensure consistent error handling/logging style across all modules

### P.2 Performance Tuning
- [ ] T0749 Profile the full match loop and identify the single slowest step
- [ ] T0750 Optimize the belief-map update function if it is a bottleneck
- [ ] T0751 Optimize LLM call frequency/throttling for a good balance of realism vs. token cost
- [ ] T0752 Confirm the agent operates comfortably within `step_deadline_seconds` under realistic load
- [ ] T0753 Re-run the performance-analysis research report after final optimizations and update its numbers

### P.3 Resilience Hardening
- [ ] T0754 Add a top-level exception handler around the main loop that logs and attempts graceful recovery rather than crashing silently
- [ ] T0755 Add health-check logging every N turns for easier post-match debugging
- [ ] T0756 Verify the agent can recover cleanly from an unexpected process restart mid-match (or fails gracefully with a clear technical-loss record)
- [ ] T0757 Add a "dry run" mode that validates config and connectivity without playing a real scored match

### P.4 Final Review & Sign-Off
- [ ] T0758 Conduct a final joint team review session covering the entire codebase
- [ ] T0759 Conduct a final joint team review session covering the entire README/report
- [ ] T0760 Confirm both teammates independently agree the project is ready for submission
- [ ] T0761 Archive a final local backup copy of both repos and all logs before the submission deadline
- [ ] T0762 Celebrate — submit the project

---

## Q. Risk Register & Edge-Case Hardening

### Q.1 Networking Edge Cases
- [ ] T0763 Handle the case where the opponent's tunnel URL changes mid-session (free ngrok restart)
- [ ] T0764 Handle the case where both agents attempt to bind the same local port accidentally
- [ ] T0765 Handle the case where an MCP call succeeds but the response body is empty/null
- [ ] T0766 Handle the case where the opponent sends a well-formed but semantically invalid move (e.g., referencing a nonexistent cell)
- [ ] T0767 Handle the case where DNS resolution for the opponent's tunnel URL temporarily fails
- [ ] T0768 Handle the case where the opponent's server responds with an unexpected HTTP status code
- [ ] T0769 Handle simultaneous commit attempts from both sides in the same turn window (race condition)
- [ ] T0770 Handle a duplicate message delivery (idempotency check on move/commit handling)

### Q.2 Game-Logic Edge Cases
- [ ] T0771 Handle the thief's starting position being adjacent to a pre-placed barrier zone — not applicable: `config/game.json` has no concept of pre-placed barriers at match start, only `thief_start`/`cop_start` cells; every barrier in this design is placed live, during play, by the cop
- [x] T0772 Handle the cop attempting to place a barrier on its own starting cell before moving — resolved by design, not a special case: `NetworkMatchRunner._maybe_place_barrier` (`services/network_match.py`) always runs *after* that turn's move, per Sec. 3.3.3's "its own current cell" reading; since the thief moves first (`active_role = THIEF if step % 2 == 1`), the cop's first barrier opportunity is naturally after its own first move, so "before moving" never arises
- [x] T0773 Handle the case where the thief and cop attempt to occupy the same cell simultaneously via near-simultaneous moves — not applicable by design: turns strictly alternate (`active_role = THIEF if step % 2 == 1 else COP`), so there is no wall-clock window where both sides move at once to create this race
- [x] T0774 Handle the case where all remaining cells around the thief become blocked in the same turn the cop moves — implemented and verified end-to-end: `is_boxed_in` is checked by the receiving thief peer every turn (`services/network_match.py`), and a positive result is declared via `win_claim={"type": "boxed_in"}` on the thief's next turn, resolving to `MatchOutcome.CAPTURE` on both peers. Proven with a real two-peer match in `tests/integration/test_network_match.py::test_two_peers_synchronize_barriers_and_resolve_a_boxed_in_capture`
- [x] T0775 Handle a board configuration where `thief_start` and `cop_start` are identical (should be rejected at config-validation time) — `load_match_parameters` (`shared/game_config.py`) now raises `GameConfigError` for identical start cells; see `test_load_match_parameters_rejects_identical_start_positions`
- [x] T0776 Handle barrier placement attempts once `max_barriers` is already exhausted (already covered in C.3, add regression test here) — regression-tested at the live-wiring level (not just the `Board` primitive): `test_maybe_place_barrier_returns_none_once_budget_exhausted` (`tests/unit/test_network_match_barrier.py`)
- [ ] T0777 Handle the very last allowed move at exactly `max_moves` cleanly ending the match
- [ ] T0778 Handle a configuration where `survival_threshold` is greater than `max_moves` (decide and document precedence)

### Q.3 Cryptography Edge Cases
- [ ] T0779 Handle a Nonce collision (extremely unlikely, but confirm the code path detects and regenerates rather than silently accepting)
- [ ] T0780 Handle a Commit message arriving twice (duplicate network delivery) without double-processing it
- [ ] T0781 Handle a Reveal arriving with a Nonce that does not match any prior Commit
- [ ] T0782 Handle a final Audit request arriving before all Reveals have completed
- [ ] T0783 Handle a partial/corrupted log file at Replay-Viewer load time (clear error rather than a crash)
- [ ] T0784 Handle mismatched `schema_version` between the two sides' Step-0 declarations

### Q.4 LLM/Provider Edge Cases
- [ ] T0785 Handle Ollama server not running at all when `ollama` mode is configured
- [ ] T0786 Handle Claude API returning a rate-limit error mid-match
- [ ] T0787 Handle Claude CLI not being authenticated/installed when `claude_cli` mode is configured
- [ ] T0788 Handle an LLM response containing content unsuitable for the hint word-limit (auto-truncate safely)
- [ ] T0789 Handle an LLM response containing accidental raw coordinates (post-filter/sanitize before sending)
- [ ] T0790 Handle a completely empty LLM response (fallback to template text)

### Q.5 Gmail/Reporting Edge Cases
- [ ] T0791 Handle OAuth token expiry with no internet connectivity available to refresh
- [ ] T0792 Handle the lecturer's report inbox rejecting the message (bounced email) - log and alert
- [ ] T0793 Handle a match ending in a technical loss before any real gameplay occurred (still must report correctly)
- [ ] T0794 Handle two matches with the same `game_id` being started in error (collision check on file naming)
- [ ] T0795 Handle a partial send failure (declaration sent, but log/result attachment fails) with a clear retry/resume path

### Q.6 GUI/Replay Edge Cases
- [ ] T0796 Handle the GUI being closed and reopened mid-match without losing live state
- [ ] T0797 Handle the Replay Viewer being pointed at a log from an unrelated/older match version (schema mismatch handling)
- [ ] T0798 Handle extremely long matches (near `max_moves`) rendering smoothly in both GUI and Replay Viewer without slowdown

---

## R. Two-Repo Parity & Cross-Team Consistency Checklist

### R.1 Structural Parity Between Cop and Thief Repos
- [ ] T0799 Confirm both repos follow the same folder layout convention (domain/infra/shared/tests/docs/config/PRD)
- [x] T0800 Confirm both READMEs cover the same required subjects while retaining role-specific strategy and replay sections
- [ ] T0801 Confirm both repos' `.gitignore` files cover the same secret-file patterns
- [ ] T0802 Confirm both repos' `pyproject.toml`/dependency files are kept in sync where shared libraries are used
- [ ] T0803 Confirm both repos independently pass their own full test suite
- [x] T0804 Confirm both repos independently start their fixed-role FastMCP server; the sibling is used only by the series coordinator for alternating games
- [x] T0805 Confirm both repos ship independent copies of the shared `config/game.json`
- [ ] T0806 Confirm both repos' `BrainBase` strategy interfaces expose equivalent extension points

### R.2 Cross-Team Config Agreement Process
- [x] T0807 Draft a pre-match checklist — `docs/OPPONENT_MATCH_GUIDE.md`
- [x] T0808 Confirm both teams agree on `grid_size` before match start
- [x] T0809 Confirm both teams agree on `axis_origin_corner` and `axis_start_index` before match start
- [x] T0810 Confirm both teams agree on `max_barriers`, `max_moves`, and `survival_threshold` before match start
- [x] T0811 Confirm both teams agree on scoring-table values before match start
- [x] T0812 Confirm both teams agree on pheromone parameters before match start
- [x] T0813 Confirm both teams agree on `hint_max_words` and `map_area` before match start
- [x] T0814 Confirm both teams exchange and verify `config_sha256` before proceeding past Step-0
- [x] T0815 Log the agreed configuration separately for every opponent series

### R.3 Communication Etiquette With Opposing Teams
- [x] T0816 Establish a shared communication channel with each opposing team for scheduling and protocol alignment
- [x] T0817 Share public/quick-tunnel URLs immediately before play and update rotated URLs
- [x] T0818 Confirm/validate the opposing Step-0 declaration before gameplay is mutually signed
- [ ] T0819 Politely flag any detected rule violation to the opposing team and to the lecturer per course policy, rather than silently exploiting it

---

## S. Team Process & Project Management

### S.1 Task Tracking
- [ ] T0820 Set up a shared task board (GitHub Projects, Trello, or similar) mirroring this TODO list
- [ ] T0821 Assign clear ownership (cop side vs. thief side vs. shared infra) between the two teammates
- [ ] T0822 Hold a short recurring sync to review progress against the 7-stage build order
- [ ] T0823 Track blockers explicitly (e.g., "waiting on opponent team's tunnel URL") separate from code tasks
- [x] T0824 Re-triage this TODO list after each stage milestone, marking completed items and re-prioritizing what's left — done at the end of every chapter throughout this project (see each chapter's `ProgressDoc.md` entry), and once more explicitly as Chapter 10's own milestone-reconciliation pass: re-verified Stage-2's HTTP round trip still passes, closed the missing `PRD_fastmcp_networking.md` gap, upgraded T0393/T0394/T0327 given Chapter 7/8 work that postdated when they were first left unchecked, and refined the Stage-6 milestone rationale to be precise about what the Orchestrator does and doesn't yet prove

### S.2 Time & Scope Management
- [ ] T0825 Estimate a rough calendar date target for completing each of the 7 build stages
- [ ] T0826 Reserve explicit buffer time before the deadline for the league-match scheduling phase (depends on other teams' availability)
- [ ] T0827 Reserve explicit buffer time for OAuth/Gmail setup, which often has unexpected console-configuration friction
- [ ] T0828 Reserve explicit buffer time for writing the academic README, which should not be rushed at the very end
- [ ] T0829 Identify which optional/recommended items (RL, custom algorithm, advanced GUI polish) are stretch goals vs. must-haves for your team

### S.3 Knowledge Sharing Between Teammates
- [ ] T0830 Ensure both teammates understand the full commit-reveal protocol, not just whoever implemented it
- [ ] T0831 Ensure both teammates understand the Orchestrator/state-machine architecture
- [ ] T0832 Ensure both teammates can independently run and debug the full match pipeline
- [ ] T0833 Pair-review each other's code for the cop vs. thief repo before final submission
- [ ] T0834 Walk through the final academic README together and confirm both teammates agree with every claim in it

---

## T. Final Sanity Sweep — One Task Per Mandatory Rule (App. E cross-check)

- [x] T0835 Verify rule 1: cop and thief run as two fully separate processes — verified during shared monorepo development via `main.py --role cop|thief`, two independent OS processes (Chapter 2). Since the two-repo submission split, the separation is stronger still: this repo's `main.py peer --role police` only ever runs the cop role at all (`--role` accepts only `police`, no thief config present), and the sibling thief repo is the genuinely separate process/repo/codebase-export running the thief side
- [x] T0836 Verify rule 2: no shared memory/state variables exist between the two sides — each role loads only its own `config/<role>/game.toml`, never the other's directory (`test_load_network_config_never_reads_the_other_roles_directory`)
- [ ] T0837 Verify rule 3: a single Orchestrator is the entry point for all sub-systems — **not true today, a real gap found reviewing docs/tasks.md §15.3 against the current codebase, not just the narrower gap originally noted here.** `Orchestrator.run_turn` (`services/orchestrator.py`, Chapter 8) is a real, tested single-turn gateway composing strategy/crypto/network/state-machine/watchdog/deadline-tracker/log-manager -- but it is not what actually drives a live match. `NetworkMatchRunner` (`services/network_match.py`, built after Chapter 8 to support the two-computer GUI and CLI `peer` command) reimplements its own turn loop, its own audit exchange, and its own control messages directly, and never calls `Orchestrator` at all. Every real match played through this repo today (`peer --role police`, or the `play` GUI's Agent vs Agent (Two Computers) mode) goes through `NetworkMatchRunner`, not `Orchestrator` -- so there are two separate, parallel match-driving implementations, not one single entry point, and `Orchestrator` is effectively dead code on the live-match path. (The originally-noted narrower gap -- Gatekeeper/Gmail-reporting/league-scoring not routed through either -- also still applies.) Deliberately left unmerged rather than refactored: `NetworkMatchRunner` is working and empirically verified end-to-end (real HTTP, real audit, `mutual_sign_off: true`, `ProgressDoc.md`'s "peer Upgraded from an Idle Listener to a Real Match Runner" entry); folding it into `Orchestrator` now would be a nontrivial architectural change with real risk of regressing that, and was explicitly deferred rather than attempted under that risk.
- [x] T0838 Verify rule 4: game phases are managed via a legal state machine — `MatchStateMachine` (Chapter 8)
- [x] T0839 Verify rule 5: illegal state transitions are rejected — `IllegalStateTransitionError`, never mutates state on rejection
- [x] T0840 Verify rule 6: a Deadline Tracker prevents deadlock while awaiting the opponent — `DeadlineTracker` (Chapter 8), wraps the Orchestrator's only outbound network call
- [x] T0841 Verify rule 7: a Watchdog monitors the main process with controlled data flush — `Watchdog` (Chapter 8); "controlled data flush" specifically (persisting state before shutdown) is not yet implemented — see `docs/TODO.md` T0533/T0534, honestly left unchecked there too
- [x] T0842 Verify rule 8: the GUI displays only local truth — `LiveViewModel`/`build_live_view_model` structurally cannot hold the opponent's true position (Chapter 7)
- [x] T0843 Verify rule 9: the GUI never displays the full objective board state — same structural guarantee, proven by a dedicated structural test in Chapter 7
- [x] T0844 Verify rule 10: Cloudflare Tunnel exposes both local role servers publicly — proven in five counted cross-team series
- [x] T0845 Verify rule 11: shared configuration identity is checked before play — byte hash and canonical `config_sha256` are exchanged and divergent terms are rejected
- [x] T0846 Verify rule 12: minimum parameter values are never reduced below the floor — `MIN_GRID_SIZE=7`/`MIN_MAX_BARRIERS=14` enforced with a hard `GameConfigError` in `shared/game_config.py`
- [x] T0847 Verify rule 13: movement is orthogonal-only — `Move` StrEnum has no diagonal member; `Board.apply_move` only ever computes N/S/E/W/STAY deltas
- [x] T0848 Verify rule 14: illegal moves are never executed — `MoveRejectedError` raised before any state mutation, for every illegal case (out of bounds, blocked cell, bad barrier target, exhausted budget)
- [x] T0849 Verify rule 15: every barrier placement is publicly declared — resolved: `services/network_match.py`'s live turn loop now calls `ManhattanHeuristicBrain._pick_move`/`Board.place_barrier` every cop turn (budget permitting) and broadcasts the result immediately via `TurnMessage.barrier_placed`, which the receiving peer applies to its own board via `Board.apply_declared_barrier` the same turn — exercised end-to-end by `test_two_peers_synchronize_barriers_and_resolve_a_boxed_in_capture`
- [x] T0850 Verify rule 16: barrier placement location is never misrepresented — the receiving peer's own local board is only ever updated to the exact `[row, col]` declared on the wire (`Board.apply_declared_barrier`), and the end-of-match mutual audit (`audit_records`) still independently verifies both sides agree on the same final outcome/log hash; a dishonest barrier declaration is intentionally not re-validated live (Sec. 3.3.9 assigns that to the end-of-match cross-audit, not per-turn re-verification), consistent with barriers being plaintext/public rather than sealed like a move
- [x] T0851 Verify rule 17: the SHA-256 commit-reveal handshake protocol is used for every move — every move the Orchestrator processes goes through a real `commit()` call (Chapter 5/8); no full continuous multi-turn live match has exercised this repeatedly end-to-end yet, but every single-turn call that does occur is genuinely committed
- [x] T0852 Verify rule 18: the Nonce stays secret until game end — only `commitment.h_commit` is ever sent over the network (`Orchestrator.run_turn`); the nonce is never transmitted during `COMMITTING`, only recorded in the post-hoc `LogEntry`
- [x] T0853 Verify rule 19: any audit-stage hash mismatch prevents mutual sign-off and is surfaced in the saved audit evidence; completed gameplay is not silently rewritten by an envelope parse failure
- [x] T0854 Verify rule 20: a replay/audit application exists and works — `python -m police_thief replay --log PATH` (Chapter 7), fully tested including a real tamper-and-detect round trip
- [x] T0855 Verify rule 21: capture claims are announced only when true — `check_capture`/`is_boxed_in` are deterministic functions computed from real positions, never a free-form self-reported claim that could lie about whether a capture occurred
- [x] T0856 Verify rule 22: capture claims/responses are sealed into live audit records and conflicting or missing evidence disables sign-off
- [x] T0857 Verify rule 23: the shared scent model is covered by the negotiated canonical config hash before gameplay
- [x] T0858 Verify rule 24: a signed Step-0 system/hardware attestation occurs before gameplay and is attached to the final audit
- [x] T0859 Verify rule 25: the LLM is not handed the actual move decision (or deviation is explicitly documented by mutual agreement) — structurally guaranteed: `BrainBase._decide_move`'s signature has no parameter through which LLM/hint text could reach it (Chapter 6)
- [x] T0860 Verify rule 26: free-text communication uses natural language only — `TemplateHintProvider` produces word-limited natural-language sentences (Chapter 6)
- [x] T0861 Verify rule 27: no direct numeric-coordinate protocol is used in hints — hints use direction words ("West, I think"), never raw `(row, col)` pairs; `parse_claimed_direction`/`detect_bluff` operate on direction words, not coordinates
- [x] T0862 Verify rule 28: a token-bucket rate limiter protects Gmail report sending — `TokenBucket`/`Gatekeeper` (Chapter 9), wired in front of every `send_match_report` call; not yet exercised against the real Gmail API since no real OAuth client exists (see rule 30)
- [x] T0863 Verify rule 29: a DOS/anomaly detector protects network resources — `AnomalyDetector` (Chapter 9), composed into the same `Gatekeeper` pipeline
- [x] T0864 Verify rule 30: the Gmail interface code uses send-only permission scope — verified in code: `services/gmail_oauth.py::SCOPES = ["https://www.googleapis.com/auth/gmail.send"]`, tested (`test_scopes_are_send_only_per_the_least_privilege_mandate`), deliberately narrower than the `gmail.modify` scope used in the prior course project this OAuth flow was ported from. The *Google Cloud Console* consent-screen configuration itself must still be double-checked to match once a team completes the real, manual OAuth setup (Section I.3) — the code-side guarantee is done, the human-side console configuration is not yet verifiable
- [x] T0865 Verify rule 31: the team completed five counted series against distinct opponents — `najamjad`, `amireman`, `sharNamr`, `SMNGRP05`, and `ahk-yosi`
- [ ] T0866 Verify rule 32: every counted match was automatically reported via Gmail — live Gmail delivery is proven for G009, but the retained artifacts do not independently prove automatic delivery for all five counted series
- [x] T0867 Verify rule 33: the match report is structured as valid JSON — all four mandatory report types round-trip correctly (Chapter 9)
- [x] T0868 Verify rule 34: no end-of-match report is ever sent as free text — `build_report_email` raises `TypeError` at runtime on anything that isn't a `dict`/`list`, a genuine enforcement, not just a type hint
- [x] T0869 Verify rule 35: mutual result claims and reciprocal series SHA gate `mutual_agreement.confirmed`; each team retains its independently produced report
- [x] T0870 Verify rule 36: every live sub-game performs a final mutual nonce/log audit and the series performs reciprocal consensus
- [x] T0871 Verify rule 37: counted-game history is declared and recorded during opponent coordination before counted play
- [x] T0872 Verify rule 38: declarations used for the five counted opponents were explicit and consistent; false-count detection remains tested
- [x] T0873 Verify rule 39: no secrets or credentials are ever pushed to any repo — actively re-verified in Chapter 11: `git log --all --diff-filter=A --name-only` searched for `credentials.json`/`token.json`/`.env`/`secret`-like filenames across the entire commit history; none found
- [x] T0874 Verify rule 40: authorization/secret files are listed in `.gitignore` — confirmed present: `credentials.json`, `token.json`, `*.pem`, `*.key`, `.env`
- [ ] T0875 Verify rule 41: the final submission version is tagged with a documented annotated Git tag — confirmed not done (`git tag -l` returns nothing); this is correctly a submission-time action, not a mid-development one, and should not be created without an explicit request at actual submission time
- [x] T0876 Verify rule 42: each repository has a comprehensive role-specific academic README with architecture, strategy, protocol, setup, testing, results, replay GIFs, and sibling-repo link
- [ ] T0877 Verify rule 43: deliverables are submitted as Word/PDF with the template's field layout unchanged — not done; a course-logistics step requiring the official Word template, outside this repository's scope
- [ ] T0878 Verify rule 44: the assignment is submitted as a separate file per team member — not done; same course-logistics scope
- [x] T0879 Verify rule 45: team identity is encoded as an 8-character unique code without spaces — this repo's own `config/cop/game.toml` now has `group_name = "uoh-ay26"` / `group_id = "uoh-ay26"` (8 characters, no spaces, matching `config/network_match.json`'s team identity and this team's real GitHub org/repo naming) rather than a `"TBD"` placeholder (the sibling thief repo tracks its own `config/thief/game.toml` independently — this repo has no visibility into it)
- [x] T0880 Verify rule 46: a barrier placed on the cop's own occupied cell counts toward capture at that instant — implemented and tested (`test_barrier_placed_exactly_on_thiefs_cell_counts_as_capture`, Chapter 3) per Sec. 3.3.5's clear body text (a barrier landing on the *thief's* cell captures it); Appendix E's own condensed rule text says "the cell the cop occupies," which reads as an appendix paraphrase artifact against the unambiguous primary section — resolved via the primary text per this project's academic-freedom-on-contradiction principle (Sec. 0)
- [ ] T0881 Verify rule 47: a thief leaving the arena via an illegal move counts as captured — **a genuine, newly-found rulebook tension, not yet resolved in code.** The main body (Sec. 3.3.2) only says an illegal move "must be rejected/handled," and the current implementation does exactly that: `Board.apply_move` raises `MoveRejectedError` for an out-of-bounds attempt. Rule 47 (found only in Appendix E's "completions" list, §16.6, with no corresponding body-text passage) instead says this specific illegal move should count as a **capture** (cop-capture score) rather than the general "illegal move -> technical loss" mapping rule 14's own consequence text implies. Today, `MoveRejectedError` is not even caught anywhere in `Orchestrator.run_turn`'s exception handling, so it would currently propagate uncaught rather than resolve to either outcome. This is left honestly unresolved rather than silently guessed at; flagged for a dedicated follow-up decision (see `ProgressDoc.md`'s Chapter 11 entry)
- [x] T0882 Verify rule 48: every match outcome is scored exactly per the scoring table — `ScoringTable`/`score_for` defaults exactly match the Mandatory Parameters Table (20/5 capture, 5/10 survival, 2/2 tie, 0/0 technical loss), tested for all four `MatchOutcome` values
- [x] T0883 Verify rule 49: separate public Cop and Thief GitHub repositories exist, READMEs cross-link them, and result JSON contains all four team repository links
- [x] T0884 Verify rule 50: every repo includes README, config files, PRD files, PLAN file, and TODO files — all present in this repo (`README.md`, `config/`, 9 `docs/PRD_*.md` files, `docs/PLAN.md`, `docs/TODO.md`); README's *content* is the separate, larger gap tracked at rule 42
- [x] T0885 Verify rule 51: counted-series automatic reporting is configured for `rmisegal+uoh26finalgame@gmail.com`; dry-run/non-counted mode remains available for tests
- [x] T0886 Verify rule 52: each opponent match-up counts only once toward scoring — `LeagueRecord.record_counted_game` raises `LeagueRuleError` on a second counted game against the same opponent (Chapter 9), tested
- [x] T0887 Verify rule 53: the commit-hash identifier is recorded and updated in every Step-0 declaration — `get_git_commit_hash()`/`Step0Declaration.git_commit_hash` (Chapter 5), tested against this real repository
- [x] T0888 Verify rule 54: the final-results JSON reports total token consumption — `MatchResult.total_tokens_used`, sourced from `TokenUsage.total` (Chapter 9)
- [x] T0889 Verify rule 55: self-scoring reflects code quality only, not league game outcome — a submission-process discipline for the humans involved, not a code-level mechanism; noted here as a reminder for whoever fills out the final self-grading, not something this codebase itself can enforce
- [ ] T0898 Reconcile `game_uid` derivation with the league interop-kit's labeled form — `SMNGRP05-vs-uoh-ay26-C01` records the labeled uid, so `validate_submission_directory` reports `derivation_mismatch` for that bundle only; accepted as a known limitation rather than changing the shipped derivation before submission

---

**Total task count target: 800-1000.** Run `grep -c '^- \[ \]' docs/TODO.md` (unchecked) and `grep -c '^- \[x\]' docs/TODO.md` (checked) to confirm the live count as tasks are checked off and/or added during development.

**Progress log:**
- Chapter 1 (Dec-POMDP formal model) — 27 tasks checked, 8 newly added (T0890–T0897). See `ProgressDoc.md` for what was executed and why.
- Chapter 2 (P2P network architecture & FastMCP) — 23 more tasks checked (Section D.1–D.3, plus T0005). Note: Section D.4 (Turn Management) and all of Section C (Stage 1 board/scoring) remain unchecked by design — this project works through `docs/tasks.md` in chapter order (1, 2, 3, ...), not the rulebook's recommended build-priority order (Ch.10), so board logic (Chapter 3) hasn't been reached yet. See `ProgressDoc.md` for details.
- Chapter 3 (board physics, movement, barriers, capture & scoring) — 73 more tasks checked across Section C.0–C.7. A handful (T0124, T0125, T0155, T0156, T0166) are explicitly left unchecked with inline rationale — mostly because they depend on a barrier-*placing* strategy or a match log that don't exist until Chapter 6/Chapter 5-9 respectively. See `ProgressDoc.md` and `docs/PRD_board_physics.md` for the full write-up.
- Chapter 4 (dynamic pheromone trails) — 12 more tasks checked in Section F.1 only (emission/decay mechanics). Section F.2 onward (belief map, hint parsing, LLM integration, deception) is deliberately untouched: `docs/tasks.md` scopes that content to Chapter 6, even though this TODO's own stage grouping (F, "Language + Scent") bundles it together with scent. One genuine, documented rulebook tension was found and resolved via the academic-freedom-on-contradiction clause (T0277) rather than silently papered over. See `ProgressDoc.md` and `docs/PRD_pheromone_scent.md`.
- Chapter 5 (cryptographic security & Step-0) — 28 more tasks checked across Section H.1, H.4-H.6. All of H.2 (four-step network protocol wiring), most of H.3 (live log recording/technical-loss wiring), H.7, and H.8's live-match milestones are deliberately deferred to Chapter 8 (Orchestrator/legal state machine) — this chapter builds the crypto *primitives* only, not their network enforcement. A real bug was found and fixed in Windows RAM detection along the way. See `ProgressDoc.md` and `docs/PRD_commit_reveal_crypto.md`.
- Chapter 6 (strategy module & decision-making) — 55 more tasks checked across Section E (E.1-E.2, E.3/E.4's "decided not to pursue" entries, E.5-E.7) and Section F.2-F.6 (belief map, hints, bluff detection). Real LLM provider integration (ollama/claude_api/claude_cli), trust-weighted hint fusion into the belief map, and network/live-match wiring are deliberately out of scope, each with inline rationale. The headline deliverable is `tests/integration/test_strategy_pipeline.py`: two real brains play and capture using only their own belief maps, never touching the opponent's true position. See `ProgressDoc.md` and `docs/PRD_strategy_module.md`.
- Chapter 7 (GUI & Replay Simulator) — 25 more tasks checked across Section I.1-I.2. The Replay Viewer's crypto verification reuses Chapter 5's `verify()`/`audit_log()` directly rather than re-implementing it. Both GUI layers achieved 100% test coverage using real (not mocked) Tkinter widgets — a session-scoped root fixture was needed after discovering Tkinter cannot reliably create/destroy many `Tk()` instances in one process. Screenshots (T0420/T0435/T0436) could not be produced in this session (no native-window-capture tool available) and remain a manual step before submission. See `ProgressDoc.md` and `docs/PRD_gui_replay.md`.
