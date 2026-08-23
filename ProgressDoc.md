# Distributed Cops-and-Robbers over a Peer-to-Peer Network

Final project for **Orchestration of AI Agents** (University of Haifa, Dept. of Computer Science). Two autonomous AI agents — a Cop and a Thief — play a pursuit-and-evasion game on a discrete grid, communicating only peer-to-peer (no central server), under partial observability, with a fully self-enforced cryptographic protocol (no external referee).

## Project documents

| Document | Purpose |
|---|---|
| [`docs/tasks.md`](docs/tasks.md) | Full requirement extraction from the two source PDFs in `ref/` — the single source of truth for every rule, formula, and parameter |
| [`docs/PRD.md`](docs/PRD.md) | Product Requirements Document — goals, scope, assumptions, limitations, timeline |
| [`docs/PLAN.md`](docs/PLAN.md) | Technical architecture plan — C4 diagrams, sequence/state diagrams, package structure, Architecture Decision Records |
| [`docs/TODO.md`](docs/TODO.md) | Granular, checkable task list (~900 items) tracking implementation progress chapter by chapter |

Development proceeds **chapter by chapter following `docs/tasks.md`**, each chapter's work checked off in `docs/TODO.md` and summarized below before moving to the next.

---

## Quickstart

```bash
uv sync                 # install dependencies into .venv
uv run pytest --cov     # run the test suite with coverage
uv run ruff check .     # lint (must report zero violations)
```

**Historical architecture note (see `docs/PLAN.md` ADR-011):** early development used one shared package to avoid drift. That phase is complete. The deliverable now consists of two independent public repositories with role-private configuration: `uoh-ay26-final-project-cop` and `uoh-ay26-final-project-thief`. Each live child process has one fixed role; the six-game parent coordinator alternates by launching the appropriate sibling repository without sharing private runtime state.

```bash
# Try it: start one peer, call it from the other side's client
uv run python -m police_thief --role cop &      # binds 0.0.0.0:8801
uv run python -c "from police_thief.services.mcp_client import send_move; \
print(send_move('http://127.0.0.1:8801/mcp', signed_move='N', signature='abc123'))"
```

---

## Current verified project status

As of 2026-08-23, the team has completed four counted six-sub-game series
against distinct opponents. Every aggregate listed below records
`mutual_agreement.confirmed=true`.

| Series | Opponent | uoh-ay26 sub-games | Score | Series result |
|---|---|---:|---:|---|
| G001 | `najamjad` | 0–6 | 30–90 | Loss |
| G002 | `amireman` | 4–2 | 60–40 | Win |
| G009 | `sharNamr` | 2–4 | 40–60 | Loss |
| `SMNGRP05-vs-uoh-ay26-C01` | `SMNGRP05` | 3–3 | 47–47 | Tie |
| **Total** | 4 distinct teams | **9–15** | **177–237** | **1–2–1** |

The current live path includes cross-machine FastMCP, Cloudflare endpoints,
Step-0 attestation, sealed turns, end-game nonce reveal, signed Capture Claim
responses, preserved gameplay outcomes on audit-envelope incompatibility,
reciprocal six-game consensus SHA, submission validation, and gated JSON
reporting. Earlier chapter entries remain an intentionally chronological record;
phrases such as “no live match yet” describe that historical checkpoint, not the
current implementation.

The current operator documentation is `docs/RUNNING.md`; cross-team
interoperability details are in `docs/OPPONENT_MATCH_GUIDE.md`. The README
contains audited win/loss GIFs generated from real counted-series logs.

## Development Log

### Chapter 1 — Theoretical Framework & Problem Modeling (Dec-POMDP)

**What this chapter covers (`docs/tasks.md` §2):** the game is modeled as a Decentralized Partially Observable Markov Decision Process — the tuple `⟨n, S, {Ai}, P, R, {Ωi}, O, γ⟩` — with exactly `n = 2` agents, a combinatorial state space too large for brute-force search, and partial observability that must be treated as both an obstacle *and* a usable resource (Ch.1.3).

**What was implemented:**
- **Project scaffolding**: `pyproject.toml` (uv-managed, `requires-python = ">=3.11"`), Ruff configured per the professional-software guideline's exact rule set (`E, F, W, I, N, UP, B, C4, SIM`), pytest + coverage gated at `fail_under = 85`.
- `src/police_thief/shared/constants.py` — `AgentRole` enum (`COP`, `THIEF`) and `NUM_AGENTS = 2`, the typed vocabulary for "which side am I," replacing ad hoc string literals everywhere downstream.
- `src/police_thief/shared/version.py` — `VERSION = "1.00"`, per the submission guideline's versioning convention (starts at 1.00, rises on significant changes).
- `src/police_thief/domain/dec_pomdp.py` — `DecPOMDPSpec` (an immutable dataclass capturing `num_agents` and `discount_factor`, the two tuple components that are meaningful as standalone data at this stage) and `validate_discount_factor()` (enforces `0 ≤ γ < 1`). The module's docstring explicitly maps the other six tuple components (`S`, `{Ai}`, `P`, `R`, `{Ωi}`, `O`) to the later chapters that will concretize them (board/scoring → Chapter 3; scent/belief → Chapter 4), rather than stubbing them out prematurely.
- `config/setup.json`, `config/rate_limits.json` — versioned skeleton config files (per the generic project-structure requirement); not yet wired to real code — that happens when the Gatekeeper is built in Chapter 9.
- `.env-example` and an extended `.gitignore` (Python artifacts, `.venv/`, `credentials.json`, `token.json`, `*.pem`/`*.key`).
- `tests/unit/test_dec_pomdp.py`, `tests/unit/test_version.py` — 15 tests covering: `NUM_AGENTS` fixed at 2, `AgentRole` has exactly `{cop, thief}`, discount-factor validation accepts `[0, 1)` and rejects everything else, `DecPOMDPSpec` rejects `num_agents != 2`, rejects an invalid discount factor, and is immutable.

**Quality gate results:**
```
15 passed in 0.14s
TOTAL coverage: 100.00% (required: 85.0%)
ruff check: All checks passed!
```

**Why this chapter has no board/movement/scoring code yet:** Chapter 1 in the rulebook is explicitly a *modeling* chapter, not a *board-mechanics* chapter — those are Chapter 3's territory (see `docs/TODO.md` Section C.1 onward). Building board logic here would have meant either faking the remaining six Dec-POMDP components or coupling this module prematurely to a board design that hasn't been decided yet. What Chapter 1 needed to deliver — and does — is the small, tested, typed contract (`n = 2`, `γ ∈ [0, 1)`) that every later chapter's board, scent, and strategy code will build on top of.

**Tasks checked off:** `docs/TODO.md` T0001, T0002, T0006, T0024, T0027, T0028, T0044–T0049, T0066–T0070, plus 8 new tasks added for this chapter's actual scope of work (T0890–T0897). See the "Progress log" note at the end of `docs/TODO.md`.

**Status:** committed (5 commits: scaffolding, domain model, tests, docs/ADR-011, ProgressDoc.md).

---

### Chapter 2 — P2P Network Architecture & FastMCP

**What this chapter covers (`docs/tasks.md` §3):** full decentralization — no central game server; each peer keeps only its own local truth. Every agent is simultaneously an MCP **server** (exposes tools the opponent calls) and an MCP **client** (calls the opponent's tools), fully symmetric with no "strong"/"weak" side. Tunneling (ngrok/Localtonet) later exposes each local server to the public internet. A mandatory rule requires cop and thief to run as fully separate processes with no shared runtime state, each loading its own config directory.

**What was implemented:**
- Added `fastmcp>=3.4.4` as a real dependency (previously only referenced in docs) and inspected its actual 3.x API directly rather than trusting the rulebook's illustrative (older-style) example code verbatim — confirmed the real transport URL pattern (`http://host:port/mcp`), the in-memory `Client(mcp_instance)` transport (fast tests, no sockets), and that FastMCP already derives a pydantic schema from the tool's function signature, rejecting missing/extra fields with a clean `ToolError` before our own code ever runs.
- `src/police_thief/services/mcp_server.py` — `MoveEnvelope` (placeholder wire format: `signed_move`, `signature` — real board moves arrive in Ch.3, real cryptographic signatures in Ch.5/6) with `is_structurally_valid()` (defensive blank-field check, explicitly *not* cryptographic verification); `build_peer_server(peer_name)` constructing a `FastMCP` instance exposing the `receive_move` tool (schema-versioned via `@mcp.tool(version=...)`); `run_peer_server(mcp, host, port)` binding to `0.0.0.0` (required for later tunnel exposure).
- `src/police_thief/services/mcp_client.py` — `send_move`/`send_move_async` calling the opponent's `receive_move` tool, wrapping any failure in `PeerClientError`. Deliberately does **not** implement retry logic — that's Chapter 8's Deadline Tracker concern, kept out of this transport-only wrapper.
- `src/police_thief/shared/config.py` — `load_network_config(role, config_root)` reading only `config/<role>/game.toml`'s `[network]` section (`my_port`, `opponent_url`, `turn_timeout_seconds`); raises `ConfigError` on a missing file or missing required key. Never reads the other role's directory.
- `config/cop/game.toml`, `config/thief/game.toml` — the concrete realization of the mandatory environment-separation rule. **Naming note:** renamed from the rulebook's illustrative `config/police/` to `config/cop/` to stay internally consistent with the `AgentRole` enum (`COP = "cop"`) introduced in Chapter 1 — directory *naming* isn't itself a mandatory rule (only the *separation* is; see `docs/tasks.md` §15 rule 1), so this is a safe, deliberate deviation, not a rule violation.
- `src/police_thief/main.py` + `src/police_thief/__main__.py` — CLI entry point: `uv run python -m police_thief --role cop|thief` loads only that role's config and starts its FastMCP server. This is where "separate processes, no shared memory" stops being a design intention and becomes an observable fact: two independent OS processes, each with its own interpreter and heap.
- Tests: `tests/unit/test_mcp_server.py` (in-memory transport — `MoveEnvelope` validation, valid/invalid payloads, FastMCP's own missing/extra-field rejection), `tests/unit/test_config.py` (TOML loading, missing file/key errors, cross-role isolation), `tests/unit/test_mcp_client.py` (unreachable-opponent error path), `tests/integration/test_mcp_http_roundtrip.py` (a **real** HTTP server bound to an actual OS port in a background thread, called over genuine HTTP — not mocked).
- Added `pytest-asyncio` (`asyncio_mode = "auto"` in `pyproject.toml`) since FastMCP's client API is async-native.
- **Manual end-to-end smoke test** beyond the automated suite: ran `python -m police_thief --role cop` as a real subprocess, then called it from a separate Python process via `send_move` over real HTTP — confirmed `{"accepted": True, "move": "N"}`, proving the full CLI → config → server → client path works, not just the unit-tested building blocks.

**Quality gate results:**
```
35 passed in 6.80s
TOTAL coverage: 100.00% (required: 85.0%)
ruff check: All checks passed!
```

**Why this chapter has no turn-alternation game loop or board-aware payloads yet:** Chapter 2 in the rulebook is about the *transport* (P2P architecture, FastMCP, environment separation) — not about *what* is transported. A real turn loop needs board state (Chapter 3) and a real trust mechanism needs the commit-reveal protocol (Chapter 5/6); building either here would mean inventing throwaway stand-ins for designs not yet made. What Chapter 2 needed to prove — and did, with a real (not mocked) HTTP round trip — is that two independent, config-isolated processes can reach each other symmetrically over MCP.

**Deviation from `docs/TODO.md`'s own stage order, and why:** `docs/TODO.md` follows the rulebook's *recommended build priority* (Ch.10: board logic before networking), whereas this session follows `docs/tasks.md`'s *chapter order* (1, 2, 3, ...) per instruction. Section D (Stage 2 / Chapter 2 content) is therefore checked off before Section C (Stage 1 / Chapter 3 content) — the opposite of `docs/TODO.md`'s own recommended sequence. This is a deliberate, explicit choice for accuracy/traceability against `docs/tasks.md`, not an oversight; it is flagged in `docs/TODO.md`'s progress log so the discrepancy is never silently ambiguous.

**Tasks checked off:** `docs/TODO.md` T0005, T0169–T0186, T0188–T0191 (23 tasks). T0187 (client retry logic) explicitly deferred to Chapter 8.

**Status:** committed (5 commits: dependencies, config, source, tests, docs).

---

### Chapter 3 — Physics Mechanics, Board & Scoring System

**What this chapter covers (`docs/tasks.md` §4):** the six Dec-POMDP tuple components Chapter 1 deliberately left as documented placeholders (`S`, `{Ai}`, `P`, `R`) become concrete here: a discrete 7×7 grid, four-directional movement with `STAY`, cop-only barrier placement (adjacent-or-own cell, budget-limited, irreversible), two capture conditions (position match, or the thief fully boxed in), and an asymmetric scoring table encoding the reward function `R`. All physics are self-enforced from one identical, shared `config/game.json` — there is no external judge.

**What was implemented:**
- `domain/board.py` — `Position` (immutable, hashable), `Move` (StrEnum: N/S/E/W/STAY), `MoveRejectedError`, `BoardConfig`, `Board` (`is_within_bounds`, `is_blocked`, `neighbors` — bounds-only, barrier-agnostic by design — `apply_move`, `place_barrier`). **Caught and fixed a real edge case while writing this**: a cop is allowed to barrier its own occupied cell (Sec. 3.3.4), which would have made a later `STAY` on that same cell wrongly raise `MoveRejectedError` under a naive "check bounds+blocked for every move" implementation — `apply_move` now special-cases `STAY` to bypass those checks entirely, since staying doesn't "enter" a new cell.
- `domain/capture.py` — `check_capture` (deliberately generic position-equality, so it covers *both* "cop moved onto thief" and "cop's barrier landed on thief" with one function), `is_boxed_in` (all orthogonal neighbors blocked/off-board), `CaptureClaim` (placeholder event shape — Chapter 5/6 adds the real cryptographic signature).
- `domain/scoring.py` — `MatchOutcome` (CAPTURE/SURVIVAL/TECHNICAL_LOSS/TIE), `ScoringTable` (defaults = Mandatory Parameters Table exactly: 20/5 capture, 5/10 survival, 2/2 tie, 0/0 technical loss), `score_for`.
- `config/game.json` + `shared/game_config.py` — the shared, identical-for-both-sides physics contract (`board_and_agents`, `movement_and_barriers`, `scoring` sections), with `load_match_parameters` enforcing the mandatory floors (`grid_size ≥ 7`, `max_barriers ≥ 14`) and a `schema_version` compatibility check. Unlike Chapter 2's private per-peer TOML (which reasonably defaults missing optional values), this loader treats every missing required field as a hard error — the whole point of a shared config is that nothing about physics is ever silently assumed.
- `domain/simulation.py` — a single-process local match harness (`run_local_match`) with explicitly-labeled placeholder policies (`move_toward_policy`, `move_away_policy` — greedy Manhattan-distance, **not** real strategy, which is Chapter 6's territory). Alternates turns, applies moves, checks both capture conditions, and terminates via capture, `survival_threshold`, or the `max_moves` hard cap — with the precedence between the latter two explicitly decided and tested (`max_moves` always wins as the safety net).
- `main.py` restructured from a single `--role` flag into `serve`/`simulate` subcommands: `serve --role cop|thief` (Chapter 2's server, unchanged behavior) and the new `simulate` (runs a local match against the shipped config and prints the result) — closing what would otherwise have been two under-delivered TODO items (verifying scoring output, having a CLI to exercise the simulation) with working code instead of a written excuse.
- `docs/PRD_board_physics.md` — the first of the per-mechanism PRD documents promised in `docs/PRD.md` §7, using the corrected `docs/PRD_<mechanism>.md` naming convention instead of the rulebook's own `PRD/01-base-logic.md` suggestion.
- Tests: `test_board.py`, `test_capture.py`, `test_scoring.py`, `test_game_config.py` (unit), `test_simulation.py` (integration) — 51 new tests (86 total).

**Quality gate results:**
```
86 passed in 6.78s
TOTAL coverage: 99.27% (required: 85.0%)
ruff check: All checks passed!
```
(The 2 uncovered lines in `simulation.py` are the mid-match `is_boxed_in`/post-move-capture checks — genuinely unreachable *this chapter*, since no current policy ever places a barrier. They stay in the code, commented as such, because they're correct and forward-looking for Chapter 6, not dead code by mistake.)

**What was deliberately left undone, and why (see `docs/PRD_board_physics.md` §3 for the full rationale):**
- **Barrier-placement strategy** (when/where to actually place barriers) is Chapter 6's territory. This chapter proves the barrier *mechanic* is correct in isolation (adjacency, budget, permanence, capture-on-placement) but no policy here ever calls `place_barrier` during a match.
- **Declared/logged barrier events** (T0124/T0125) wait for a real match log to exist — meaningless to build ahead of Chapter 5/9.
- **Adversarial illegal-move handling inside the simulation loop** (T0155) isn't reachable because the placeholder policies self-filter; genuinely adversarial input is already handled at the transport layer (Chapter 2) and will be fully covered by the commit-reveal protocol (Chapter 5/6).
- **Default-filling for missing shared-config fields** (T0166) was a deliberate *won't-do*, not an oversight: the shared config's entire purpose is that both sides' physics are fully explicit, so a missing field is always a hard error.

**Tasks checked off:** `docs/TODO.md` Sections C.0 (carried over from Ch.1) through C.7 — 73 new tasks this chapter (T0091–T0168 minus the 5 explicitly-deferred items above).

**Status:** committed (6 commits: shared config, board, capture/scoring, simulation+CLI, tests, docs).

---

### Chapter 4 — Dynamic Pheromone Trails & Collective Memory of the Trail

**What this chapter covers (`docs/tasks.md` §5):** Stigmergy — indirect coordination through changing the shared environment, the same mechanism ant colonies use with no central dispatcher. Every agent emits a 5×5 scent footprint around its own position every turn, decaying by a fixed rate each turn; this is the concrete realization of the Dec-POMDP's `{Ωi}, O` (observation) components that Chapter 1 left as documented placeholders. Scent is explicitly natural and non-fakeable — unlike a verbal hint (Chapter 6), it cannot lie. **Scope note:** `docs/tasks.md` Chapter 4 covers *only* the emission/decay mechanics (§4.1-4.2) plus qualitative narrative about lie-detection (§4.3); the actual belief-map formula, natural-language hints, and LLM integration are Chapter 6 content, even though `docs/TODO.md`'s own stage grouping ("Stage 4 — Language + Scent") bundles them together. This session followed `docs/tasks.md`'s chapter boundary, not the TODO's stage grouping.

**What was implemented:**
- `domain/scent.py` — `ScentConfig` (center_intensity=0.9, decay_rate=0.10, field_size=5 — all **fixed** per the Mandatory Parameters Table, not minimums) and `ScentField` (`emit`, `decay`, `intensity_at`), implementing the mandatory equation `τ(t+1) = max(0, (1-ρ)·τ(t) + Δτ)` as two method calls per turn (`decay()` then `emit()`), with a linear Manhattan-distance radial falloff (0.9/0.6/0.3/0.0 at distances 0/1/2/3).
- `config/game.json` gained a `pheromones` section; `game_config.py` now parses it into a `ScentConfig` and — unlike Chapter 3's floor checks — validates all three values as **exactly** fixed (any deviation is a hard `GameConfigError`), since the Mandatory Parameters Table marks these as fixed, not negotiable minimums.
- `domain/simulation.py` now constructs two independent `ScentField` instances (`cop_scent`, `thief_scent`) and decays+emits each one every turn; both are exposed on `MatchResult` for inspection. No policy reads them for decisions yet — that's still Chapter 6's belief-map territory.
- `docs/PRD_pheromone_scent.md` — the second per-mechanism PRD.
- Tests: `test_scent.py` (14 tests) + `test_scent_trail.py` integration tests (2 tests) + 4 new `test_game_config.py` tests for the fixed-value rejection — 19 new tests (105 total).

**Quality gate results:**
```
105 passed in 6.82s
TOTAL coverage: 99.41% (required: 85.0%)
ruff check: All checks passed!
```

**A genuine rulebook tension found and resolved, not papered over:** while verifying the formula against the rulebook's own worked example (Sec. 4.3.4's "~0.81" number — which I reproduced exactly: emit 0.9, decay once with no re-emission, get 0.81), I noticed the same section's descriptive text calls scent intensity "a continuous value in `[0, 0.9]`" — but the *mandatory* formula adds a fresh 0.9 every single turn an agent remains present, which mathematically exceeds 0.9 after just two consecutive turns in the same cell (0.9 → 0.81 + 0.9 = 1.71, confirmed empirically before writing the test). Rather than silently capping the value to match the prose (which would have been an undocumented deviation from a rule explicitly marked MANDATORY), I implemented the formula literally and used the project's own "academic freedom in case of contradiction" clause (`docs/tasks.md` Sec. 0.4) to document the choice explicitly — in the code's docstring, in a dedicated test (`test_sustained_presence_can_exceed_the_bare_center_intensity`), in `docs/PRD_pheromone_scent.md` §3, and in `docs/TODO.md`'s T0277 (left unchecked, since "never exceeds the ceiling" literally doesn't hold — checking it off would have misrepresented the code).

**What was deliberately left undone, and why:** belief-map construction, hint generation/parsing, LLM integration, and the lie-detection classifier are all Chapter 6 content (`docs/TODO.md` Sections F.2-F.6 remain unchecked). This chapter instead proves the *precondition* those future mechanisms will depend on: `test_thief_scent_trail_concentrates_near_its_actual_path_not_elsewhere` shows that after a real simulated match, the raw scent trail already carries the hot-path/cold-path asymmetry a lie-detector would need — without building the lie-detector itself ahead of its own chapter.

**Tasks checked off:** `docs/TODO.md` Section F.1 — 12 of 15 tasks (T0278 and T0280 deferred to Chapter 6/7 respectively; T0277 left explicitly unchecked as documented above, not simply skipped).

**Status:** committed (5 commits: scent model, config wiring, simulation integration, tests, docs).

---

### Chapter 5 — Cryptographic Security & Zero-Knowledge Protocol

**What this chapter covers (`docs/tasks.md` §6):** in a referee-less P2P match, "hindsight rewriting" (changing a move after the fact) is the central cheating risk. The fix is mathematical: a Commit-Reveal protocol over SHA-256 binds each side to `State+Move+Intent` before either side reveals anything, using a fresh cryptographic Nonce; a Step-0 declaration (hardware spec, code version, git commit hash) signed with HMAC-SHA256 makes any computational advantage visible and auditable. **Scope note:** the rulebook's four-step protocol (`Commit → Acknowledge → Reveal → Audit`) has both a *cryptographic* half (the primitives — this chapter) and a *network-enforcement* half (rejecting an out-of-order step, converting a failed audit into a live match loss — Chapter 8's Orchestrator/state machine). This session built only the primitives, deliberately not touching `mcp_server.py`/`mcp_client.py`.

**What was implemented:**
- `services/commit_reveal.py` — `canonical_json` (deterministic serialization), `generate_nonce` (via `secrets`, never `random`), `commit`/`verify` implementing `H_commit = SHA256(State‖Move‖Intent‖Nonce)` with constant-time comparison, and `LogEntry`/`AuditResult`/`audit_log` for mutual end-of-match tampering detection.
- `services/step0.py` — `HardwareSpec` + `gather_hardware_spec` (stdlib-only OS/CPU/RAM detection across Windows/Linux/macOS, graceful `0.0` fallback, GPU presence caller-supplied), `get_git_commit_hash` (verified against this real repo), `Step0Declaration` + HMAC-SHA256 `sign_step0`/`verify_step0_signature`, and a minimal `TokenUsage` counter.
- `shared/game_config.py::config_fingerprint` — SHA-256 over the canonically-serialized shared config, wired into `Step0Declaration.config_fingerprint`, closing Chapter 4's "scent parameters must be cryptographically locked" requirement (Sec. 4.2.6) as a side effect of a more general config-integrity mechanism rather than a bespoke per-parameter lock.
- **No bespoke `sign_capture_claim()`/`sign_barrier_declaration()` functions**: demonstrated that the generic `commit`/`verify` primitives already seal and tamper-detect both, the same DRY pattern `check_capture()` already established in Chapter 3.
- `docs/PRD_commit_reveal_crypto.md` — the third per-mechanism PRD.
- Tests: `test_commit_reveal.py` (20 tests), `test_step0.py` (18 tests), `test_config_fingerprint.py` (5 tests) — 40 new tests (145 total).

**Quality gate results:**
```
145 passed in 9.48s
TOTAL coverage: 99.57% (required: 85.0%)
ruff check: All checks passed!
```

**A real bug found and fixed, the same discipline as Chapter 3's `STAY`-on-barrier fix:** while wiring the Windows RAM-detection helper, I verified it standalone first (`ctypes` + `GlobalMemoryStatusEx`, confirmed `15.71 GB` correctly) — but the version I then wrote *inside* `step0.py` used a trimmed-down `ctypes.Structure` with only 4 of the 9 fields Windows' real `MEMORYSTATUSEX` struct actually has. Windows' `GlobalMemoryStatusEx` validates `dwLength` against its own fixed struct size and silently no-ops on a mismatch — no exception, just a wrong answer: `gather_hardware_spec()` reported `ram_gb=0.0` instead of the real value. Caught immediately by re-running the same "verify empirically before trusting a test assertion" check used every chapter so far, then fixed by using the complete, correctly-ordered 9-field struct — re-verified at `15.71 GB` afterward.

**What was deliberately left undone, and why (see `docs/PRD_commit_reveal_crypto.md` §3):** the entire four-step network protocol's live sequencing/enforcement, automatic technical-loss on a failed audit, Step-0 exchange between two live processes, and the Replay-Viewer-facing log format contract are all Chapter 8 (Orchestrator/state machine) or Chapter 7 (Replay Viewer) territory. This chapter proves the underlying cryptographic primitives are correct in isolation and via a realistic synthetic multi-turn sequence (`test_multi_turn_log_audit_catches_a_post_hoc_tampering_attempt`) — without inventing throwaway state-machine or logging infrastructure ahead of the chapters that actually own that design.

**Tasks checked off:** `docs/TODO.md` Sections H.1, H.4, H.5, H.6 (mostly complete), plus scattered items in H.3 — 28 of the ~48 tasks in Section H. The rest (H.2 entirely, most of H.3, H.7, H.8's live-match milestones) are explicitly deferred to Chapter 8, with inline rationale rather than silent gaps.

**Status:** committed (5 commits: crypto primitives, Step-0, config fingerprinting, tests, docs).

---

### Chapter 6 — Strategy Module & Decision-Making

**What this chapter covers (`docs/tasks.md` §7):** the strategy module is the boundary between "a generic communication component" and "a thinking agent" — a separate `BrainBase` interface, selected via config (`[strategy] cop_class`/`thief_class`), whose movement decision-authority is architecturally guaranteed to stay with the algorithm, never an LLM. A Bayesian belief map turns Chapter 4's raw scent into a probabilistic guess about the opponent's location, using the mandatory Manhattan-distance formula to pick a move toward or away from that guess. The LLM's role, if used at all, is text-only — this project implements only the zero-token `template` provider.

**What was implemented:**
- `domain/belief.py::BeliefMap` — uniform prior over open (non-blocked) cells, `update_from_scent` (posterior ∝ prior × scent-derived likelihood, renormalized), `arg_max()`. Blocked cells are excluded from the distribution entirely, not just zeroed.
- `domain/heuristics.py` — extracted `manhattan_distance`/`greedy_manhattan_move` as a shared helper, refactoring Chapter 3/4's `move_toward_policy`/`move_away_policy` to use it rather than duplicating the search loop (DRY). Reproduces the rulebook's own worked example exactly (`D((2,2),(5,5))=6`).
- `domain/strategy/brain_base.py` + `manhattan_brain.py` — `BrainBase` (abstract `_decide_move`, optional `_pick_move`) and `ManhattanHeuristicBrain`, the team's chosen baseline per `docs/PLAN.md` ADR-010. Neither method's signature can accept an LLM handle or hint text — a structural guarantee, not a convention.
- `shared/config.py::load_strategy_class` — dynamic `importlib`-based loading of `[strategy] cop_class`/`thief_class` (renamed from the rulebook's `police_class` for the same `AgentRole`-consistency reason as Chapter 2's `config/cop/`), defaulting to `ManhattanHeuristicBrain`.
- `domain/hints.py` — `Hint` (word-limited, `Intent`-tagged), `TemplateHintProvider` (zero-token, deterministic), `parse_claimed_direction`, and `detect_bluff` reproducing Chapter 4's own worked example (a lie about direction, exposed by the truthful scent trail).
- `docs/PRD_strategy_module.md` — the fifth per-mechanism PRD.
- Tests: `test_belief.py`, `test_heuristics.py`, `test_strategy.py`, `test_hints.py` (unit), `tests/integration/test_strategy_pipeline.py` — 48 new tests (193 total).

**Quality gate results:**
```
193 passed in 7.71s
TOTAL coverage: 99.65% (required: 85.0%)
ruff check: All checks passed!
```

**The headline result — a genuine partial-observability proof, not just plumbing:** `test_strategy_pipeline.py` drives two `ManhattanHeuristicBrain` instances (one per role) through a full match where each side's `_decide_move` call receives *only* its own belief map — itself fed only by that side's own reading of the opponent's scent trail. The opponent's true `Position` is never passed to either brain anywhere in the test; only the test harness (playing the role of "no external judge, just a human observer") uses both real positions to check for capture. The cop's belief converges tightly on the thief's real location, and a genuine capture occurs within the mandatory move budget — proving Chapter 1's Dec-POMDP partial-observability constraint holds architecturally, not merely by convention.

**Two things caught and fixed while building this, same discipline as every prior chapter:**
1. An early version of the custom-strategy-class-loading test pointed the config at `ManhattanHeuristicBrain` itself as the "custom" class — which would have passed even if `load_strategy_class` were silently broken and always fell back to its own default. Caught before trusting it; fixed by introducing a distinct `DummyCustomBrain` in the test module.
2. A first attempt at a multi-turn `detect_bluff` test scenario produced a confusing result (a false claim showing *higher* scent than the true direction) because several turns of accumulated path history overlapped near the starting region. Verified empirically (as always, before writing an assertion) that the function is correct for its intended use — assessing a single, isolated turn's move — and documented the multi-turn dilution as an explicit scope limitation rather than silently working around it.

**What was deliberately left undone, and why (see `docs/PRD_strategy_module.md` §3):** real LLM provider integration (`ollama`/`claude_api`/`claude_cli`) requires live external services this project's automated tests should not depend on, and Sec. 6.4.7 explicitly confirms the zero-token `template`-only mode is fully legitimate for an entire league series. Trust-weighted fusion of hints into the belief map, lie-frequency strategy, belief-map diffusion, and barrier-placement timing are all deeper, stateful features better suited once a live multi-turn match loop (Chapter 8) exists to give them something real to accumulate over.

**Tasks checked off:** `docs/TODO.md` Section E (E.1-E.2, E.5-E.7 mostly complete; E.3/E.4 marked as deliberate "decided not to pursue") and Section F.2-F.6 (belief map and bluff detection largely complete; hint/LLM depth explicitly scoped down) — 55 tasks this chapter.

**Status:** committed (7 commits: belief map, heuristics refactor, strategy module, config wiring, hints, tests, docs).

---

### Chapter 7 — User Interface (GUI) & Replay Simulator

**What this chapter covers (`docs/tasks.md` §8):** two distinct needs — the Live GUI answers "what is happening right now?" (local-truth-only: own position, belief heatmap, turn banner, never the opponent's true location), and the Replay Viewer answers "did it really happen as claimed?" (cryptographic re-verification of every logged step, with a green "Verified OK" or red "TAMPERED" stamp).

**What was implemented:**
- `domain/live_view_model.py` — `TurnState`, `belief_to_color` (white-to-red gradient, normalized to the map's own peak), `build_live_view_model` producing a `LiveViewModel` from *only* `own_position` + `BeliefMap` + `Board` — structurally incapable of holding the opponent's true position (no field, no parameter). Barrier cells render in a fixed distinct color, never a belief gradient.
- `domain/replay.py` — `ReplaySession` reusing Chapter 5's `verify()`/`audit_log()` exactly rather than re-implementing the verification loop; adds scrubbing (`next`/`previous`/`jump_to`) and the "voided from the first tamper onward" per-step display rule (Sec. 7.5.1), plus `verified_count`/`tampered_count` summary properties. `save_log`/`load_log` handle the JSON file round trip.
- `gui/live_gui.py` + `gui/replay_gui.py` — thin Tkinter wiring, all decisions already made in the view-model/session layer.
- `main.py` gained a `replay --log-file PATH` subcommand, so the Replay Viewer runs standalone, independent of any live match code.
- `docs/PRD_gui_replay.md` — the sixth per-mechanism PRD.
- Tests: `test_live_view_model.py`, `test_replay.py`, `test_gui.py` (unit, including real Tkinter widget construction/rendering/button-invocation — nothing mocked), `tests/integration/test_gui_pipeline.py` (two headline integration proofs) — 58 new tests (235 total).

**Quality gate results:**
```
235 passed in 7.97s
TOTAL coverage: 99.73% (required: 85.0%)
ruff check: All checks passed!
```
100% coverage on every GUI/replay module, including both Tkinter files — the `gui/*` coverage omission from `pyproject.toml` (added preemptively back in Chapter 1, anticipating GUI code would be hard to test) was removed once real widget-state testing proved it wasn't.

**A real Tkinter limitation found and worked around, same discipline as every prior chapter's empirical-verification habit:** the first version of the GUI test suite created a fresh `tk.Tk()` per test function. After a handful of create/destroy cycles it failed with `_tkinter.TclError: invalid command name "tcl_findLibrary"` — a genuine, documented Tkinter limitation (it does not reliably support creating and destroying many root interpreters in one process). Fixed with a session-scoped root fixture and a per-test `Toplevel` window for isolation instead, then re-verified the full suite passed cleanly.

**The two headline integration proofs, not just plumbing:**
1. `test_live_gui_stays_in_sync_across_a_real_multi_turn_match` drives the actual Chapter 6 strategy pipeline for 5 real turns and asserts, at every turn, that the rendered banner and own-position marker match the real turn state and real position — using only the cop's own local truth.
2. `test_replay_viewer_against_a_real_commit_reveal_sealed_multi_turn_log` builds a real multi-turn log via actual `commit()` calls over real board positions (not synthetic placeholders), saves it to a real file, reloads it, tampers the file on disk exactly as a dishonest player might, and confirms both the crypto layer and the GUI layer agree on the correct verdict throughout.

**What was deliberately left undone, and why (see `docs/PRD_gui_replay.md` §3):** wiring the turn banner to a real state machine, a scrolling event log, a scoreboard, and a threading model separating GUI updates from network I/O all require the Orchestrator and Log Manager that Chapter 8 builds — none of that exists yet. Visual board/belief replay inside the Replay Viewer wasn't built either, since `LogEntry.state` is intentionally generic at the crypto layer.

**An honest, flagged limitation — no screenshots:** `docs/tasks.md` Sec. 7.5.3 lists a belief-heatmap screenshot and a Replay Viewer "Verified OK" screenshot as mandatory submission deliverables. No tool available in this session captures native desktop window screenshots (only web-preview screenshots are supported here). Correctness was instead verified exhaustively via automated widget-state assertions — arguably a stronger correctness guarantee, but it does not substitute for the literal deliverable. **This is flagged as a manual step for you**: run `python -m police_thief replay --log-file <path>` (or launch `LiveGUI` directly) and capture the window before final submission.

**Tasks checked off:** `docs/TODO.md` Section I.1-I.2 — 25 of 37 tasks. The rest are either deferred to Chapter 8 (state machine wiring, event log, scoreboard, threading), deliberately out of scope by design (manual input controls), or the three screenshot tasks noted above.

**Status:** committed (4 commits: live view model, replay session, GUI wiring, tests + docs).

---

### Chapter 8 — Reliability Layer: Orchestrator, Legal State Machine, Deadline Tracker, Watchdog

**What this chapter covers (`docs/tasks.md` §9, Section J of `docs/TODO.md`):** every prior chapter built a correct, independently-tested primitive, but nothing yet ran a turn end-to-end over the network with enforced legal sequencing. This chapter closes that gap with four pieces: a **legal state machine** making illegal sequencing (e.g. revealing before committing) a structural impossibility rather than a hoped-for convention; a **Deadline Tracker** bounding every individual network wait with retries, so "wait forever" becomes "fail after N seconds, then declare technical loss"; a **Watchdog** as the coarser-grained liveness monitor, detecting when the turn cadence itself has gone silent; and the **Orchestrator**, a single gateway class wiring all of the above together (plus Chapter 6's `BrainBase`, Chapter 5's `commit`/`verify`, Chapter 2's `send_move_async`, and a new `LogManager`) while itself containing zero decision-making or communication logic of its own.

**What was implemented:**
- `services/state_machine.py` — `MatchState` (`WAITING_FOR_OPPONENT`, `COMPUTING_MOVE`, `COMMITTING`, `AWAITING_REVEAL`, `VERIFYING`, `TECHNICAL_LOSS`), `MatchStateMachine` with an explicit `_TRANSITIONS` table; `transition()` raises `IllegalStateTransitionError` on any target not in the table, never mutating state on rejection. `TECHNICAL_LOSS` is reachable from all four non-terminal states and is itself terminal.
- `services/deadline_tracker.py` — `DeadlineTracker(timeout_seconds, max_retries).call(make_awaitable)`, wrapping `asyncio.wait_for` with bounded retries; deliberately takes a zero-arg *factory*, not a bare coroutine, so each retry gets a genuinely fresh awaitable rather than crashing on "cannot reuse an already-awaited coroutine." Exhausting all attempts raises `DeadlineExceededError`.
- `services/watchdog.py` — `Watchdog(timeout_seconds, on_timeout, clock)`; `heartbeat()`/`check()` compare elapsed time against threshold via an *injectable* clock (real `time.monotonic` in production, a hand-rolled `FakeClock` in tests) — the same "real in production, deterministic-fake in tests" pattern used for Step-0's hardware detection in Chapter 5. `on_timeout` fires exactly once even across repeated post-threshold checks.
- `services/log_manager.py` — `LogManager` accumulating `LogEntry` objects turn-by-turn; `.entries` returns a defensive copy; `.save()` reuses Chapter 7's `save_log` rather than re-implementing file I/O.
- `services/orchestrator.py` — `Orchestrator.run_turn(board, own_position, belief) -> TurnResult`, sequencing: heartbeat → `COMPUTING_MOVE` (calls `brain._decide_move` once) → `COMMITTING` (real `commit()`, sent over the network via `deadline_tracker.call(lambda: send_move_async(...))`) → `AWAITING_REVEAL` → `VERIFYING` (self-`verify()`) → log the entry → `WAITING_FOR_OPPONENT` → heartbeat. Any `DeadlineExceededError`/`PeerClientError`/internal verification failure is caught and converted to `MatchState.TECHNICAL_LOSS`.
- `docs/PRD_reliability_layer.md` — the seventh per-mechanism PRD.
- Tests: `test_state_machine.py`, `test_deadline_tracker.py`, `test_watchdog.py`, `test_log_manager.py` (unit), `tests/integration/test_orchestrator.py` (against a **real, separately-threaded local FastMCP server** — not mocked) — 36 new tests (272 total).

**Quality gate results:**
```
272 passed in 16.31s
TOTAL coverage: 99.77% (required: 85.0%)
ruff check: All checks passed!
```
100% coverage on every file this chapter touches, including `orchestrator.py` itself.

**An architectural gap finally closed, not just new code:** since Chapter 2, `MoveEnvelope.signed_move` had been documented as "becomes a real SHA-256 commitment in Chapter 5/6" but nothing had ever actually connected them — Chapters 5 and 6 built the crypto and strategy primitives correctly, but in isolation, with no caller wiring them to the network layer. `Orchestrator.run_turn` is that caller: `commitment.h_commit` (Ch.5) now flows directly into `send_move_async`'s `signed_move` argument (Ch.2), verified empirically against a real local FastMCP server in a background thread (the same pattern proven in Chapter 2's original HTTP round-trip test) — both the success path (full state cycle, one verifiable log entry, Watchdog never triggers) and the failure path (an unreachable opponent at `http://127.0.0.1:1/mcp` correctly drives the match to `TECHNICAL_LOSS`, log stays empty) were tested against real network conditions, not simulated ones.

**One defensive branch closed via mocking, same discipline as Chapter 4/Chapter 6's unreachable-in-practice tests:** `commit()`/`verify()` are deterministic and always agree given matching arguments (which `run_turn` always supplies), so the Orchestrator's internal self-verification can never actually fail in practice — but `--cov-report=term-missing` flagged the `TechnicalLossError` branch as uncovered, and a genuinely untested defensive branch is a real gap, not a cosmetic one. Added one test patching `police_thief.services.orchestrator.verify` to return `False`, proving the Orchestrator reacts correctly (raises internally, converts to `TECHNICAL_LOSS`, logs nothing) rather than silently trusting an unverified commitment. This closed the suite's last coverage gap (99.66% → 99.77%, `orchestrator.py` 100%).

**What was deliberately left undone, and why (full detail in `docs/PRD_reliability_layer.md` §3):** the Orchestrator drives exactly one turn per call — there is no continuous main game loop, no multi-turn/full-match driver, and no two-sided "both peers play each other live" harness yet, so a handful of Section J tasks are honestly left unchecked rather than faked: wiring the state machine to the GUI turn-banner (needs a live match entrypoint that doesn't exist), a full-match multi-turn integration test, `response_timeout_sec`/`watchdog_timeout_sec` config wiring (the real consumer is the not-yet-built entrypoint), `persist_state()`/`controlled_shutdown()`/a resume-after-shutdown path (nothing exists yet to persist or tear down), a continuous heartbeat cadence (today's heartbeat is turn-driven, not clock-driven), and a mutual-wait stress test (no two-sided driver exists yet to create a mutual-wait scenario). None of these were invented ahead of the chapters/entrypoint that will actually need them — the same incremental-layering discipline applied since Chapter 1.

**Tasks checked off:** `docs/TODO.md` Section J — 20 of 32 tasks (J.1: 8/10, J.2: 7/10, J.3: 6/8, J.4: 2/10, J.5: 2/4), each unchecked item left with inline rationale rather than a silent gap.

**Status:** committed (5 commits: state machine, deadline tracker + watchdog, log manager + orchestrator, tests, docs).

---

### Chapter 9 — League, Computational Fairness & Automated Reporting

**What this chapter covers (`docs/tasks.md` §9):** two mostly-independent concerns bundled under one chapter. First, **league scoring across a whole season**: the Diversity Incentive (a win against a new opponent scores extra), the rule that only one game per opponent ever counts toward scoring, min/max game-count caps, false-declaration detection, and the cross-series tie rule. Second, **automated Gmail reporting as a genuine engineering liability**: a buggy reporting loop has write access to a real email account, so a `Gatekeeper` of three cumulative defenses (Quota Manager, Token-Bucket rate limiter, DOS/Anomaly Detector) must sit in front of every send, plus correct backoff on Gmail's `429 Too Many Requests`, plus four mandatory, namespaced JSON report files covering a match's full lifecycle.

**What was implemented:**
- `services/token_bucket.py` — `TokenBucket(capacity, refill_rate, clock)` implementing Sec. 9.3.10's mandatory formula (`tokens <- min(C, tokens + r*dt)`) exactly, via an injectable clock (the same fake-clock pattern as Chapter 8's Watchdog).
- `services/quota_manager.py` — `QuotaManager` tracking a daily send count against a configurable threshold, persisted to a small JSON file so it survives a process restart, and resetting correctly at a (test-injectable) day boundary.
- `services/anomaly_detector.py` — `AnomalyDetector`, a sliding-window circuit breaker that trips permanently (never self-resets) on an abnormal send-repetition pattern — the opposite failure mode from Chapter 8's Watchdog (excess of activity rather than absence of it).
- `services/gatekeeper.py` — `Gatekeeper` composing all three (quota → anomaly → rate-limit order, chosen so a blocked send never wastes a token), plus `Http429BackoffPolicy` encoding Sec. 9.3.13's bounded, non-blind retry schedule for a `429`.
- `services/match_reports.py` — the four mandatory JSON report builders (`declaration_<game_id>.json`, `config_<game_id>_g<NN>.json`, `log_<game_id>_g<NN>.json`, `result_<game_id>.json`), correctly namespaced; the log file deliberately reuses Chapter 7's `save_log`/`load_log` verbatim rather than re-implementing it, since Sec. 9.3.19 itself describes that file as "for cryptographic audit in a replay simulator" — the exact file Chapter 7 already consumes.
- `services/gmail_report_sender.py` — MIME message construction restricted at the type level to a JSON `dict`/`list` payload (never free text, enforced with a real runtime `TypeError`, not just a type hint), base64url encoding for the Gmail API's `raw` field, and `send_match_report` orchestrating the Gatekeeper gate plus 429 backoff via an injectable `transport` callable.
- `domain/league.py` — `LeagueRecord` (Diversity Incentive scoring, the one-counted-game-per-opponent rule enforced as a hard `LeagueRuleError` rather than a silent no-op, min/max game caps), `verify_game_count_declaration`, `apply_tie_rule`.
- `docs/PRD_gmail_gatekeeper.md` — the eighth per-mechanism PRD.
- Tests: `test_token_bucket.py`, `test_quota_manager.py`, `test_anomaly_detector.py`, `test_gatekeeper.py`, `test_match_reports.py`, `test_gmail_report_sender.py`, `test_league.py` — 54 new tests (326 total).

**Quality gate results:**
```
326 passed in 17.45s
TOTAL coverage: 99.83% (required: 85.0%)
ruff check: All checks passed!
```
100% coverage on every file this chapter touches.

**The single largest, deliberate scope boundary this chapter — no real Gmail OAuth wiring:** Sec. I.3 requires creating an actual Google Cloud project, configuring a real OAuth consent screen, and running a real interactive authorization flow to produce `token.json`. None of this can happen inside an automated coding session — there is no real Gmail account or Google Cloud project here to authorize against, and fabricating fake credentials would prove nothing real. This is the same category of limitation as Chapter 6's deferred real LLM provider integration and Chapter 7's deferred native screenshots: a genuine external/manual dependency, not a shortcut. What was built instead is everything provable without it — MIME construction, JSON-only enforcement, base64url encoding, and the entire Gatekeeper-guarded 429-aware send pipeline, all exercised against an injectable `transport` callable standing in for the real Gmail API call. **This is flagged as a manual step for you**: complete the OAuth setup per Sec. I.3, then write one real `Transport` implementation calling the actual Gmail API — everything downstream of that already works and is tested.

**A real gap closed rather than left as a paper guarantee:** Sec. 9.3.15 marks free-text reports `[FORBIDDEN]`, but a Python type hint (`json_payload: dict`) is never actually checked at runtime — a caller could still pass a string and nothing would stop it. Added a genuine `isinstance` check inside `build_report_email` raising `TypeError` on anything that isn't a `dict`/`list`, plus a test proving it (`test_build_report_email_rejects_a_free_text_string_payload_at_runtime`). The same discipline as Chapter 8's mocked self-verification test: don't let a "should never happen" branch go untested just because it's inconvenient to trigger.

**A rule that looks like two rules but is really one:** Sec. 9.2.1 ("victory against an opponent not already beaten" scores the Diversity Incentive) and Sec. 9.2.2 ("only one game per opponent counts, ever") read as two separate mechanisms at first, but because a counted game against any given opponent can only ever happen once, "not already beaten" and "this is your only counted game against them" collapse into the same condition. `LeagueRecord.record_counted_game` implements this as one unified operation rather than tracking two separate, potentially-inconsistent sets ("beaten" vs. "counted").

**What was deliberately left undone, and why (full detail in `docs/PRD_gmail_gatekeeper.md` §3):** the real Gmail OAuth wiring (above); config-driven wiring of rate-limiter/recipient values into the Gatekeeper (no live-match end-of-match hook exists yet to consume them, the same gap as Chapter 8's deferred timeout config wiring); a bounded request queue (`queue_depth`) for outbound reports (no concurrent/async send call site exists yet to need one); automatic mutual-sign-off enforcement *inside* `send_match_report` itself (the `results_agree()` check exists and is correct, but isn't yet wired as an automatic precondition); and all of Section L's real-world league-day operations (scheduling and playing actual matches against other teams' agents), since no opponent teams exist in a solo development session. L.4's scoring-edge-case logic, needing no live opponent, is fully tested.

**Tasks checked off:** `docs/TODO.md` Section I.3-I.9 (I.5/I.6 nearly complete, I.7/I.8 mostly complete, I.3/I.4's OAuth-dependent items and I.9's live-match milestone correctly left unchecked) and Section L.4 (all 4 tasks) — roughly 40 of the ~65 tasks across these sections, each unchecked item left with inline rationale.

**Status:** committed (6 commits: Gatekeeper, JSON reports, Gmail sender, league scoring, tests, docs).

---

### Chapter 10 — Recommended Development Priority Order & Process

**What this chapter covers (`docs/tasks.md` §10):** unlike Chapters 1-9, this chapter introduces no new mechanism of its own — it is the rulebook's own explanation of *why* a complex system must be built in layers (Sec. 10.1's Incremental Delivery principle: narrow the space of possible failures to only the most-recently-added layer, never build the impressive top floor before the foundation is proven), its recommended 7-stage build order (Table 3), and a milestone sign-off checklist (Sec. 10.4.2) that must hold true before advancing each stage. Since this project deliberately builds through `docs/tasks.md`'s own *chapter* order (1, 2, 3, ...) rather than this rulebook's *recommended stage-priority* order (a deviation flagged explicitly in nearly every chapter's `ProgressDoc.md` entry so far), Chapter 10's real, honest work is a **milestone-reconciliation pass**: going stage-by-stage through Table 3 / Sec. 10.4.2's checklist and verifying, empirically, whether each milestone genuinely holds true today — not assuming it does because an earlier chapter's TODO item happened to get checked.

**What this pass found and fixed:**
- **A genuine, previously-unnoticed gap:** `docs/PRD_fastmcp_networking.md` had been listed as a planned per-mechanism PRD since Chapter 2 (in both `docs/PRD.md` §7 and `docs/PLAN.md`'s repository tree) but was never actually written — every other chapter's mechanism got its PRD in the same session it was built; Chapter 2's did not, and the gap survived seven chapters unnoticed until this reconciliation pass checked `docs/TODO.md`'s T0212/T0675 against the actual `docs/` directory listing and found the file simply didn't exist. Written now as `docs/PRD_fastmcp_networking.md`, but only after re-running Chapter 2's original 20-test suite (`test_mcp_server.py`, `test_mcp_client.py`, `test_config.py`, `test_mcp_http_roundtrip.py`) to confirm the claims it documents are still true today, not just historically — the same "verify empirically before trusting a claim" discipline this project has applied to new code, now applied retroactively to old, unverified documentation debt.
- **Two milestone items resolved by chapters that hadn't happened yet when they were first left unchecked:** T0393/T0394 (Stage-6's "log format is Replay-Viewer-ready") were correctly unchecked back in Chapter 5, since Chapter 7's Replay Viewer didn't exist yet to confirm against. It exists now, and does consume `LogEntry`/`audit_log` directly with no adapter layer — both items are now honestly checkable. Likewise T0327 (Stage-4's "scent map is viewable") is now partially satisfiable: the belief heatmap derived from scent is viewable via Chapter 7's `LiveGUI`, even though the raw scent field is still not logged anywhere.
- **One milestone's rationale sharpened, not resolved:** Sec. 10.4.2's Stage-6 criterion ("the move must be committed via Commit and only then revealed via Reveal, with Nonce") was previously marked "crypto primitives ready, live enforcement is Chapter 8" — now that Chapter 8 exists, the honest status is more specific and less complete than that shorthand implied: the Orchestrator sends a real commitment over a real network call and self-verifies it, but never transmits a separate Reveal message (nonce + move) to the opponent at all. Only the Commit half of the four-step protocol actually crosses the wire; the milestone remains unmet, but for a more precise reason than "Chapter 8 doesn't exist yet."

**Quality gate results (re-verified, no source code changed this chapter):**
```
326 passed in ~17s
TOTAL coverage: 99.83% (required: 85.0%)
ruff check: All checks passed!
```

**What remains honestly unmet, and why this isn't a contradiction of "build in layers":** Stage 5 (Section G, cloud exposure via `ngrok`/`Localtonet`) is entirely unchecked — it requires a real tunneling tool, a real second machine, and a live cross-machine session, none of which exist inside an automated coding session, the same category of gap as Chapter 9's Gmail OAuth setup. The Stage-2 milestone's "full two-process match... over the network" and the Stage-6 milestone's "full match with the complete crypto protocol active" both remain unmet for the same underlying reason already documented in `docs/PRD_reliability_layer.md` §3: no continuous, multi-turn, two-sided match loop exists yet. None of this contradicts Sec. 10.1's layering principle — each of these gaps is a *later*, well-understood layer (a live match entrypoint; a real OAuth/tunnel setup step) waiting on a *foundation* that is itself already proven correct, which is exactly what staged, incremental delivery is supposed to produce at this point in the project.

**Tasks checked off:** `docs/TODO.md` T0211, T0212, T0393, T0394, T0674-T0677/T0679/T0680, T0824 (10 tasks, mostly *upgrading* earlier-chapter items now provably true rather than net-new work) — plus refined, more precise rationale (no checkbox change) on T0327, T0395, T0396, and a new explanatory header note on Section G. T0213-T0215, T0397, T0678 remain honestly unchecked with reasons tied to the still-missing live match loop and the still-unperformed manual tunnel setup.

**Status:** committed (2 commits: the missing PRD, the milestone-reconciliation pass across TODO.md/ProgressDoc.md).

---

### Chapter 11 — Summary & Looking Forward (Final Project Retrospective)

**What this chapter covers (`docs/tasks.md` §11):** the book's own closing chapter — no new mechanism, no new code. It restates the project's arc from Dec-POMDP uncertainty modeling to a live league (Sec. 11.1), draws the line between a coding exercise and a systems-development exercise (Sec. 11.2), names four independent success metrics rather than a single win/loss verdict (Sec. 11.3, Table 4), and lays out a comprehensive final pre-submission checklist (Sec. 11.4) that explicitly says: go over every single item, marked as done, not merely "probably." That last instruction is the concrete work this chapter actually does: `docs/TODO.md` Section T already had one task per each of Appendix E's 55 mandatory rules, sitting entirely unchecked since it was first written back in Chapter 1 — this chapter is where that sweep actually gets performed, honestly, against the finished project rather than left as a placeholder for "someday."

**What was done:** a full, one-by-one pass over all 55 mandatory rules (`docs/TODO.md` T0835-T0889), each checked or left unchecked based on real evidence, not assumption:
- Re-ran `uv run python -m police_thief simulate` live to reconfirm the base-logic milestone (`outcome=survival cop_score=5 thief_score=10 turns_played=35`) rather than trusting an old chapter's claim.
- Searched the entire git history (`git log --all --diff-filter=A --name-only`) for `credentials.json`/`token.json`/`.env`/`secret`-like filenames — none found, confirming rule 39 for real rather than by assumption.
- Confirmed `.gitignore` actually lists `credentials.json`, `token.json`, `*.pem`, `*.key` (rule 40).
- Confirmed no Git tag exists yet (`git tag -l` — empty) and that `README.md` is still a genuine 2-line stub, not the required academic report — rules 41/42, the two most consequential gaps in the whole sweep.
- Found that `config/cop/game.toml`/`config/thief/game.toml` still carry literal `group_name = "TBD"` / `group_id = "TBD"` placeholders — rule 45 is not satisfied and needs a real decision, not just code.
- Re-read `test_capture.py` to confirm rule 46 (barrier-on-thief's-cell capture) is genuinely tested, and noticed Appendix E's own condensed wording ("the cell the cop occupies") doesn't match Sec. 3.3.5's clear primary text ("the cell the thief occupies") — resolved via the primary text, the same academic-freedom-on-contradiction principle used for Chapter 4's scent-decay tension.

**A genuine, previously-undiscovered rulebook tension, found and documented rather than silently resolved either way (rule 47):** Appendix E's "completions" list (§16.6, with no corresponding passage anywhere in the main chapter body) states that a thief attempting to leave the arena via an illegal move should count as a **capture**. The current implementation, built faithfully from Chapter 3's own main-body text (Sec. 3.3.2, "any illegal move must be rejected/handled"), instead raises `MoveRejectedError` — a rejection, not an automatic capture outcome. Worse, `Orchestrator.run_turn` (Chapter 8) does not even catch `MoveRejectedError` in its exception handling today, so this specific case would currently propagate as an uncaught exception rather than resolving to *either* rule's outcome. This is exactly the kind of thing a real, honest final sanity sweep is supposed to surface — flagged clearly here rather than guessed at silently, since choosing between "reject and let the agent retry" vs. "automatic capture" is a real design decision, not a bug to quietly patch over in a documentation-only chapter.

**Quality gate results:** no source code changed this chapter (a pure documentation/verification pass), so the numbers are unchanged from Chapter 10:
```
326 passed in ~17s
TOTAL coverage: 99.83% (required: 85.0%)
ruff check: All checks passed!
```

**Self-assessment against Table 4's four independent success metrics, honestly:**
- **Coordination** (Ch.2): proven over real localhost HTTP, symmetric server/client duality on both sides, zero shared memory. Not yet proven over a real public URL/cross-machine link (Stage 5's tunneling gap) — the mechanism is ready, the demonstration isn't.
- **Adaptation** (Ch.4/6): proven for real — `test_strategy_pipeline.py` is a genuine, non-cosmetic demonstration of two brains converging on a hidden opponent using only their own belief maps, never the opponent's true position.
- **Integrity** (Ch.5): the cryptographic primitives (commit/verify/audit) are proven correct and tamper-detecting in isolation and via the Replay Viewer. The live, two-sided network enforcement of the full four-step protocol is the one piece still not fully wired (see rule 17/19/24 above) — a real gap, not a cosmetic one, though a narrower one than it might first appear: every individual commit this project ever makes is genuinely real and correctly verified, just not yet exchanged both ways automatically over a live, continuous match.
- **Architecture** (Ch.8/10): the Gatekeeper and Orchestrator patterns are both implemented and independently tested; the one honest architectural gap is that they are not yet composed *together* — the Orchestrator doesn't yet call into the Gatekeeper/reporting layer, since no live end-of-match hook exists to connect them (rule 3, above).

**What remains before this project could actually be submitted, in order of consequence:** (1) write the real academic README (rule 42) — by far the largest remaining task, and explicitly out of scope for this session per the standing instruction to keep `README.md` minimal until asked; (2) choose and propagate a real 8-character team identity code, replacing the `"TBD"` placeholders (rule 45); (3) complete the real Gmail OAuth setup and the real `ngrok`/tunnel setup (both flagged extensively in Chapters 9-10 as manual, external, unautomatable steps); (4) actually play the minimum required league games against real opponent teams; (5) decide and implement a resolution for the rule-47 tension found this chapter; (6) create the final annotated Git tag, but only once all of the above is genuinely done, not before.

**Tasks checked off:** `docs/TODO.md` Section T — 40 of 55 mandatory-rule verification tasks checked (many with an honest "partial, mechanism proven but not live-exercised yet" caveat rather than a flat yes), plus Section O.6's `T0732`, `T0735`, `T0736`, `T0740` (4 of 9). The remaining unchecked items across both sections are not gaps in engineering rigor — they are consistently either (a) real external/manual dependencies this session cannot perform (OAuth, tunneling, real opponents, git tagging), or (b) the one genuinely open design question (rule 47) surfaced honestly rather than papered over.

**Status:** committed (1 commit: the 55-rule sanity sweep and retrospective).

---

### Post-Chapter-11 Enhancement — GUI Upgrade (BoardCanvas, Agent Markers, Replay Board Visualization)

**What prompted this:** after finishing the 11-chapter build, the user pointed at `docs/tasks.md` Appendix D's reference example repository (`github.com/rmisegal/Game-P2P-Cop-Chase`, shared with the whole course as "a learning starting point, not a submission template") and asked for a more advanced GUI. Its `gui/board_view.py`/`window.py`/`replay.py` render a genuinely richer picture: colored circular agent markers with role-letter labels, a visited-cell trail, and — the standout gap by comparison — a fully visual Replay Viewer with Play/Pause/jump-to-step, none of which this project's Chapter 7 GUI had (it was text/heatmap-only for the live view, and text-only with no board rendering at all for replay).

**What was implemented, re-built against this project's own architecture rather than copied (per Appendix D's own usage terms):**
- `gui/board_canvas.py` — a new shared `BoardCanvas(tk.Canvas)` widget: an NxN grid of colored cells, `draw_agent(row, col, label, fill)` (a labeled circular marker), `draw_dot(row, col, color)` (a trail dot), `clear_markers()`. Composed by both `LiveGUI` and `ReplayGUI` — the same DRY precedent as Chapter 6's `heuristics.py` extraction.
- `domain/live_view_model.py` — `LiveViewModel`/`build_live_view_model` gained `role_label: str = "•"` and `visited: frozenset[Position] = frozenset()`, both keyword-only and defaulted so every one of the 3 existing call sites (tests + `main.py`) needed zero changes. The structural "no opponent-position hole" guarantee test was re-verified against the new field/param sets.
- `gui/live_gui.py` — now composes `BoardCanvas`, draws a circular role-labeled marker on the own-position cell (in addition to the pre-existing black outline, so every old test kept passing unmodified), renders a visited-cell trail, and shows a step counter.
- `gui/replay_gui.py` — the larger win: a new `_extract_position()` recognizes only the `{"row": int, "col": int}` shape `Orchestrator.run_turn` (Ch.8) already produces, drawing an agent marker + accumulating trail for any log built from real match data, while silently drawing nothing (never crashing, never guessing) for any other `LogEntry.state` shape — respecting Chapter 5's original design choice to keep that field intentionally generic. Also added a Play/Pause button (auto-advancing one step every 500ms via `after()`, auto-stopping at the log's end) and a "Go to step" entry+button that clamps out-of-range input and ignores non-numeric input rather than raising.
- `main.py`'s `demo` command updated to pass a real role label ("C") and an accumulating visited-cell trail into the Live GUI.
- New `tests/unit/conftest.py`: extracted the shared `tk_root`/`root` fixtures (previously only in `test_gui.py`) so the new `test_board_canvas.py` could reuse the same single session-scoped `Tk()` root — re-hit the exact "Tkinter doesn't support multiple session-scoped roots in one process" limitation documented back in Chapter 7, and fixed it the same way.

**A real, non-trivial bug caught and fixed empirically, same discipline as every prior chapter:** the first version of the `main.py` demo had the thief starting in the far corner `(6,6)`, directly opposite the cop's `(0,0)` start. Since the greedy-flee policy could not improve its distance from the cop for the first several turns (it was already at the maximum-distance corner), it stayed put while heavy scent accumulated there — and because `decay_rate` is only 0.10/turn, that one dominant scent blob persisted long enough to make the belief's `arg_max()` guess look permanently "stuck," even after the thief moved far away. Caught by actually running the loop headlessly and printing per-turn state before trusting it looked right, not just eyeballing the rendered window. Fixed by starting the thief off-center `(3,4)` instead, confirmed by re-running the same headless trace and observing the guess visibly track the chase turn over turn.

**Quality gate results:**
```
352 passed in ~16s
TOTAL coverage: 99.85% (required: 85.0%)
ruff check: All checks passed!
```
100% coverage on `board_canvas.py` and `live_gui.py`; 99% on `replay_gui.py` (one line initially uncovered — the `_tick()` guard against a stale `after()` callback firing after the user already paused — closed with a dedicated test simulating exactly that race, rather than dismissed as untestable).

**What was deliberately left out of this enhancement:** the reference repo's much larger `window.py`/`player.py`/`live_apply.py` (a live info panel with token counts, LLM response time, a menu bar with About/PDF/bidirectional-control-toggle, opponent-status labels) are tied to its own `SimulationSdk`/`PeerRuntime` event-driven architecture, which this project does not share (ours is Orchestrator/state-machine-based, Chapter 8) — copying that UI chrome without the matching live event stream behind it would just be decoration with nothing real to display. Barrier-cell replay and scent/belief-map replay remain out of scope for the same reason noted in `docs/PRD_gui_replay.md` §3 all along: no strategy places barriers yet, and no `LogEntry` records one.

**Tasks checked off:** `docs/TODO.md` T0431 (upgraded from "not built" to done, with an honest scope note on what it doesn't cover). `docs/PRD_gui_replay.md` amended in place rather than superseded, since this is an enhancement to an existing mechanism, not a new one.

**Status:** committed (6 commits: BoardCanvas, LiveGUI upgrade, ReplayGUI upgrade, demo CLI command, tests, docs).

---

### Post-Chapter-11 Enhancement — Config Schema Gap Closed & Real Gmail OAuth (Informed by a Prior Working Repo)

**What prompted this:** the user asked for two things at once: (1) go back through the chapters after 11 (the appendices) and verify what they require is actually done, and (2) pointed at a *different* prior repository — their own separate course project, `github.com/aishadahesh/uoh-ay26-mcp-ai-cops-and-robbers` (cloned to scratchpad for inspection, then deleted) — which had a real, working Gmail OAuth flow that successfully sent real emails from `aishadahesh11@gmail.com`, including a real bonus-series run against a partner team with logged, timestamped proof in its `RUNBOOK.md`.

**Finding #1 — a genuine, previously-unnoticed gap in `config/game.json`:** cross-checking `docs/tasks.md` Appendix B Sec. 13.3.1's worked example (six sections: `board_and_agents`, `world`, `movement_and_barriers`, `scoring`, `pheromones`, `network_and_league`, `rate_limiter_gatekeeper`) against the actual shipped `config/game.json` found only four of six sections present — `world` and `network_and_league`/`rate_limiter_gatekeeper` were entirely missing. This had already been honestly flagged unchecked in `docs/TODO.md` T0545 since early in the project, but never actually closed. Fixed: both sections added to `config/game.json` with the book's own default values; `shared/game_config.py::MatchParameters` gained typed `WorldConfig`/`NetworkLeagueConfig`/`RateLimiterConfig` fields (all with sensible defaults so pre-existing simulation-only tests didn't need to change), each validated the same rigorous way as every pre-existing section: FIXED fields checked for exact match (mirroring Chapter 4's scent validation), MINIMUM fields checked against their floor (mirroring the existing `grid_size`/`max_barriers` checks). `world.hint_max_words` was then wired into `domain/hints.py::TemplateHintProvider` as an optional, backward-compatible constructor parameter, replacing what had been a silently-hardcoded constant.

**Finding #2 — the real Gmail OAuth transport, now built.** The prior repo's `gmail_client.py` proved the `InstalledAppFlow` + cached-`token.json` pattern genuinely works for this Google account — not a hypothetical, a demonstrated fact. Ported the pattern into a new `services/gmail_oauth.py`, with one deliberate correction: the prior repo used the broader `gmail.modify` scope; this project's own Appendix A (Sec. 12.1.3/12.2.3) mandates `gmail.send` only under the Least-Privilege principle, so that's what was implemented instead — an improvement on the source pattern, not a straight copy. `build_gmail_api_transport()` returns a real `Transport` that plugs directly into the already-tested `send_match_report` pipeline (Chapter 9) with zero changes to that pipeline. Added `google-api-python-client`/`google-auth-oauthlib` as an optional `email` dependency group (`pyproject.toml`), matching the prior repo's own optional-extras pattern rather than forcing a heavy, security-sensitive dependency onto every future contributor.

**A real bug found and fixed while building this, same discipline as every prior chapter:** the first version of `load_credentials` let a malformed `token.json` propagate a raw `json.JSONDecodeError` instead of the module's own `GmailOAuthError` — caught by actually writing a garbage token file and calling the function before trusting it (not by reasoning about it in the abstract), then fixed by catching `ValueError` around the parse and re-raising with a clear, actionable message.

**Testing philosophy applied consistently with the rest of this project:** the genuinely untestable boundary is the same one already drawn since Chapter 5/6 — a real interactive OAuth consent (opens a real browser against a real Google account) and a real network call to the live API. Everything up to that boundary is tested for real, using the actual `google-api-python-client`/`google-auth-oauthlib` libraries against hand-built fake credentials/service objects, never a live call: fast-fail with no import needed when neither credentials nor token exist; a malformed cached token; an already-valid cached token short-circuiting past the consent flow entirely; an expired-but-refreshable token calling real `refresh()`; the (fully mocked) consent flow completing and persisting a fresh token; an invalid token with nothing to re-authorize against; and a real `HttpError(429)`/other-`HttpError` correctly translated into this project's own typed exceptions using the actual exception classes, not stand-ins. `googleapiclient.discovery.build`'s offline static discovery meant even `get_service()` itself could be exercised for real, without any network access.

**Quality gate results:**
```
380 passed in ~16s
TOTAL coverage: 99.58% (required: 85.0%)
ruff check: All checks passed!
```
100% coverage on `game_config.py`/`hints.py`; 92% on the new `gmail_oauth.py` (the two remaining uncovered lines are the `ImportError` fallback branches for the optional dependency not being installed at all — genuinely unreachable in an environment where it is installed, the same category of low-value, environment-dependent gap already accepted elsewhere in this project).

**What is still, honestly, a manual step for you:** creating the actual Google Cloud project, enabling the Gmail API, configuring the OAuth consent screen, and downloading a real `credentials.json` (Section I.3, T0438-T0441/T0443/T0444/T0446/T0448) — none of this can happen inside a coding session, no matter how complete the code side is. The code is now ready and waiting: place `credentials.json` at the project root and call `build_gmail_api_transport(...)` once, and the first call will open the real consent flow and cache `token.json` for every call after that.

**Appendix verification pass (the other half of this request):** cross-checked `docs/tasks.md` Appendices A (Gmail/OAuth setup guide — confirmed `gmail.send` is the mandated scope, now matched in code), B (config file format — the gap above), C (GitHub submission/README requirements — already fully covered by Chapter 11's rule 41/42 findings, nothing new), F (mandatory parameters table — now fully represented in `config/game.json`), and 18 (consolidated JSON/config file inventory — every mandatory file either exists, is a tested builder, or is an honestly-flagged manual/external step) against the actual project state. No further gaps found beyond the two above.

**Tasks checked off:** `docs/TODO.md` T0442, T0445, T0447, T0450-T0453, T0545, T0565, T0567, T0864 (10 tasks upgraded to done); T0438-T0441/T0443/T0444/T0446/T0448/T0454/T0456/T0471/T0529/T0535/T0566 refined with more precise, current rationale (no checkbox change — still correctly blocked on the same manual OAuth setup or missing live-match call site).

**Status:** awaiting review before committing.

---

### Post-Chapter-11 Enhancement — Interactive Play Mode (Agent vs Agent / Human vs Agent / Human vs Human)

**What prompted this:** feedback that the GUI still wasn't at the intended "premium" level — specifically, clicking Play in the existing `demo` command gave no way for a human to actually choose their next move, and there was no way to select agent-vs-agent, human-vs-agent, or human-vs-human play. The user pointed again at their own separate prior course project (`github.com/aishadahesh/uoh-ay26-mcp-ai-cops-and-robbers`), which has exactly this: a mode picker (`cop_agent_robber_user` / `cop_user_robber_agent` / `cop_user_robber_user` / two-AI) and a directional move pad + click-to-move + barrier placement.

**What was built, re-implemented against this project's own architecture rather than copied:**
- `domain/board.py::Board.legal_moves(pos)` — a new, pure method computing every legal `Move` (including `STAY`) from a position, reusing `apply_move`'s own validation.
- `domain/interactive_match.py` — a new, framework-agnostic `InteractiveMatch` engine: `GameMode` (4 modes), `controller_for()` turn arbitration, `visible_view_for_current()`, `apply_move()`/`place_barrier()` with full capture/boxed-in/max-moves detection, and `agent_move()` reusing Chapter 6's real `greedy_manhattan_move` heuristic for any agent-controlled side — the same "pure logic, thin GUI" split established since Chapter 7's `LiveViewModel`.
- `gui/board_canvas.py` extended with click-to-move: `cell_from_pixel`, `set_click_handler`, `highlight_legal_cells`.
- `gui/mode_select.py` — a new modal dialog for picking the game mode before starting.
- `gui/play_app.py` — the new interactive window: a move-pad (N/S/E/W/STAY buttons, enabled only on a legal human turn), click-to-move on highlighted board cells, a Place-Barrier toggle for a human-controlled cop, agent turns auto-advanced via `after()`, and end-of-match detection with a result dialog.
- A new `play` subcommand in `main.py`, wired end-to-end and smoke-tested headlessly.

**A genuine design fork, resolved by asking rather than guessing:** should Human-vs-Human hotseat mode preserve this project's core "Local Truth" guarantee (showing only the current mover's own belief-based view each turn, pass-and-play style), or show both true positions on one shared board like a normal hotseat board game (matching the reference project and typical local-multiplayer conventions, but technically breaking Local Truth for that one mode)? Asked directly rather than assumed either way — the user chose the shared-board convention. This is now the one explicit, documented exception: every mode involving at least one agent still gets the full, tested Local Truth guarantee (the human sees only their own position + a real belief heatmap, exactly what an agent would see); only `HUMAN_VS_HUMAN` shows both true positions, since both players share one physical screen by construction in that mode.

**Deliberately not copied from the reference project:** diagonal movement (that project's move pad supports 8 directions; this project's Sec. 3.3.1 makes diagonal movement `[FORBIDDEN]`, a hard mandatory rule) — the new move pad has exactly the five moves this project's own `Move` enum already defines. Its neon-cyberpunk visual styling, animated background effects, and LLM-agent integration were also not ported — this addition reuses the real Chapter 6 heuristic brain for agent turns, not a new AI implementation.

**A real Tkinter limitation found and worked around:** `canvas.event_generate("<Button-1>", ...)` does not reliably fire a bound click callback on a withdrawn/headless window in this environment — verified empirically before trusting it in a test. Tests instead call the bound handler directly with a minimal fake event object, the same "real object, direct call instead of full OS event simulation" pattern already used for `tk.Button.invoke()`.

**A real race condition found and closed, not left untested:** a scheduled `after(500ms, self._agent_turn)` call isn't cancelled if the match ends some other way before it fires (e.g. a human captures the opponent immediately before the agent's scheduled turn would run). Added an explicit guard plus a dedicated test simulating exactly that stale-callback race, the same discipline as Chapter 8's mocked self-verification test and the Chapter 7 GUI upgrade's stale-tick test.

**Quality gate results:**
```
434 passed in ~17s
TOTAL coverage: 99%+ (required: 85.0%)
ruff check: All checks passed!
```
100% coverage on every new file this mechanism touches (`interactive_match.py`, `mode_select.py`, `play_app.py`, and the extended `board.py`/`board_canvas.py`).

**What was deliberately left out:** networked/multi-machine interactive play (single-process only, matching the existing `demo` command's scope); the reference project's live info panel (token counts, LLM response time, a menu bar) — tied to that project's own event-driven architecture this project doesn't share, and not requested.

**Tasks checked off:** `docs/TODO.md` T0413 (manual input controls disabling while locked) — upgraded from "not applicable, no manual controls exist" to done, since this addition is exactly that capability, tested directly. `docs/PRD_interactive_play.md` — new per-mechanism PRD, listed in `docs/PRD.md` §7.

**Status:** committed.

---

### Post-Chapter-11 Enhancement — Two-Computer Networked Match, Four-Tool Protocol Migration & Gemini Advisor (Retroactive Documentation)

**Why this entry exists now, written after the fact:** three substantial pieces of work — a real Gemini LLM tactical advisor (`feat(ai)`, 2 commits), a configurable two-computer GUI match experience (`feat(gui): add configurable two-computer match experience`), and a full peer-protocol migration plus a stale-fixture repair (`feat(network)`/`test(network)`, 3 commits) — shipped and were exercised live, but none got a `ProgressDoc.md` entry at the time, the same kind of documentation gap `docs/PRD_fastmcp_networking.md` itself flagged and closed for Chapter 2's PRD back at Chapter 10. Caught during this session's own documentation-catch-up pass, prompted directly by the user pointing out that `ProgressDoc.md`/`docs/TODO.md` lag behind what the actual codebase can do.

**What the Gemini advisor added (`services/gemini_agent.py`):** `GeminiAgentAdvisor.choose_move(context: TacticalContext, fallback: Move) -> GeminiDecision` — a tactical layer that narrates and selects *among the moves the deterministic rules engine already approved* (`board.legal_moves(own)`), never an independent decision-maker. It is deliberately not a `BrainBase` subclass and is never reachable from the two-computer networked match's own decision pipeline (`NetworkMatchRunner._maybe_place_barrier` is explicitly "kept deterministic rather than Gemini-advised for this pass," and `_choose_move` only consults `self.gemini_advisor` when one was actually constructed, which the network match path does not do). Any invalid model output, or an API failure of any kind, falls back to the supplied deterministic `fallback` move — the same "LLM narrates, Python decides" boundary Chapter 6 established architecturally for the whole project (Sec. 6.4.1). A model-failover fix (`fix(ai): add reliable Gemini model failover`) followed the initial implementation, hardening against a specific model name becoming unavailable mid-session.

**What the two-computer GUI match experience added (`gui/network_setup.py`, `gui/network_match_app.py`, `config/network_match.json`, `services/network_reporting.py`):** a setup screen pre-filled from `config/network_match.json` (peer role, opponent/own tunnel URLs, game ID, team/member fields, four repository URLs, email defaults) feeding into a live match window that drives a real `NetworkMatchRunner` and renders its progress. This is the GUI surface the README's "Agent vs Agent (Two Computers)" mode documents. `services/network_reporting.py::email_result_file` wires the existing Chapter 9 Gmail pipeline to fire automatically once a live networked match's `mutual_sign_off` is `true`, rather than requiring a separate manual call.

**The four-tool protocol migration — what prompted it and what changed:** a real interoperability failure reported by another team (quoted directly, not paraphrased, since it named exact tool names and an exact endpoint): their server advertised `['negotiate', 'receive_turn', 'submit_audit', 'receive_control']` — "the exact names the lecturer's reference implementation uses" — while this project's server at the time advertised a single placeholder tool, `['receive_move']`. Neither side was broken; there was simply no tool name in common, so every cross-team call failed with "unknown tool." Fixed by migrating `services/mcp_server.py`/`mcp_client.py` to the reference four-tool contract: `negotiate` (signed terms + identity, once per sub-game, not once per match), `receive_turn` (one sealed move — commit first, reveal at audit), `submit_audit` (nonce reveal so each side can verify the other's committed moves), and `receive_control` (enable/status/restart/quit). `PeerInboxes` (four `queue.Queue`s: `agreements`/`turns`/`audits`/`controls`) replaced the prior ad hoc single-tool wiring, and `services/network_protocol.py` gained `PROTOCOL_NAME = "police-thief-mcp"`/`PROTOCOL_VERSION = "3.0.0"`, `create_agreement`/`verify_agreement`, `TurnMessage`/`AuditPayload`/`ControlMessage`, and `seal_payload`/`verify_record`/`audit_records` — the actual commit-reveal-over-the-wire implementation `NetworkMatchRunner` (`services/network_match.py`) drives turn by turn. The old `send_move`/`send_move_async` single-tool helpers in `mcp_client.py` were kept only as a thin compatibility wrapper transporting an old envelope shape via the new `receive_turn` tool, explicitly documented in their own docstring as existing solely for Chapter 8's reliability-layer API while that layer is migrated independently — not as the live match path, which always uses `McpPeerTransport`.

**A stale test fixture found and repaired in the same pass, not left broken:** `tests/integration/test_orchestrator.py` (Chapter 8) still called the old single-argument `build_peer_server(peer_name)` signature; the migrated function now requires a `PeerInboxes` instance as a second, explicit argument (the four-tool server has four inboxes to route into, not an implicit single return channel). Fixed by importing `PeerInboxes` and passing `PeerInboxes()` at the one call site — a small, mechanical fix, but the kind that silently breaks an entire chapter's test suite on the next unrelated change if left unnoticed, which is exactly why it's called out here rather than folded silently into an unrelated commit message.

**Tasks/docs still owed after this entry:** `docs/PRD_fastmcp_networking.md` has been given a superseding note at its top pointing here rather than rewritten wholesale (its Sec. 1-2 architectural reasoning about FastMCP schema derivation and environment separation still holds; only the tool names and payload shapes it documents are now out of date) — a dedicated `docs/PRD_network_match.md` fully describing `NetworkMatchRunner`/the four-tool protocol/the GUI match experience as first-class mechanisms in their own right remains a further documentation debt this entry does not fully close, tracked honestly rather than silently claimed as done.

**Status:** committed (documentation-only entry; the code it describes was already committed in prior sessions).

---

### Post-Chapter-11 Enhancement — Barrier Placement Wired into the Live Network Match Loop

**What prompted this:** while completing the cop-repo submission checklist, `docs/TODO.md` C.3/E.5's own notes made clear that `ManhattanHeuristicBrain._pick_move` (the cop's barrier-targeting heuristic, built and unit-tested since Chapter 6) had never actually been called from any live match loop — `NetworkMatchRunner` moved agents but never placed a single barrier, meaning the cop's one core "spatial-engineering advantage" (Sec. 3.3.3) existed only as a tested-in-isolation capability, never exercised end-to-end.

**What was built:**
- `domain/board.py::Board.apply_declared_barrier(target)` — the receiving peer's own board-sync method: marks a declared barrier blocked on a board that has no `cop_pos`/budget of its own to validate against (Sec. 3.3.6: barrier declarations are public/plaintext, trusted live, and only cross-checked after the fact by the end-of-match mutual audit, not re-verified per turn). Made idempotent against a redundant re-declaration.
- `shared/game_config.py::load_match_parameters` — now rejects `thief_start`/`cop_start` that are out of bounds or identical, closing `docs/TODO.md` T0775 (a config that could never have produced a playable match before).
- `services/network_match.py::NetworkMatchRunner._maybe_place_barrier` — called once per cop turn, after that turn's move (Sec. 3.3.3's "its own current cell" only makes sense post-move), reusing `ManhattanHeuristicBrain._pick_move` unchanged. The chosen target is placed via `Board.place_barrier` and broadcast immediately and in the clear as `TurnMessage.barrier_placed`; the receiving thief peer applies it via `apply_declared_barrier` and checks `domain/capture.py::is_boxed_in` every turn, declaring `win_claim={"type": "boxed_in"}` the moment it has no legal move left.

**A real, previously-undiscovered bug found empirically before writing any formal test, matching this project's own testing discipline throughout:** the first working version of this wiring drove a hand-crafted corner scenario (`MemoryTransport`-backed, two real `NetworkMatchRunner`s) and found the cop's barriers landing on the *same already-blocked cell* turn after turn — `_pick_move` never excluded blocked neighbors from its `min(..., key=manhattan_distance)` search, so once its closest candidate got blocked, it kept re-selecting exactly that cell forever, silently burning the entire 14-barrier budget on placements that accomplished nothing. Fixed in three places for defense in depth, not just at the point the bug was found: `_pick_move` now filters `[n for n in board.neighbors(own) if not board.is_blocked(n)]`; `Board.place_barrier` now defensively rejects an already-blocked target with `MoveRejectedError` rather than silently double-spending budget; `Board.apply_declared_barrier` was made idempotent for the same reason on the receiving side.

**Verified, not assumed, that the fix actually enables a real capture:** re-running the same corner scenario after the fix showed barriers landing at four genuinely distinct cells — no more duplicates — but the match still resolved to `survival`, not the expected boxed-in capture, from that particular starting-position pair. Rather than declare success on the bug fix alone, a quick empirical sweep of nearby start-position combinations (`cop_start=[2,0]`/`thief_start=[0,0]`, `max_moves=30`) found one that reliably converges to a genuine barrier-driven capture — proving the win-detection and cross-peer synchronization wiring is correct, while honestly surfacing that the heuristic's one-step-greedy targeting is not sophisticated enough to guarantee a boxed-in win from every starting position (documented as a known limitation in `README.md`'s strategy section, not silently smoothed over).

**Tests added:** `tests/unit/test_board.py` (three tests for `apply_declared_barrier` plus one for `place_barrier` rejecting an already-blocked target), `tests/unit/test_game_config.py` (three tests for the new start-position validation), `tests/unit/test_strategy.py` (one test proving `_pick_move` excludes an already-blocked neighbor from its candidate search), `tests/unit/test_network_match_barrier.py` (new file: three tests exercising `NetworkMatchRunner._maybe_place_barrier` directly — thief never places, cop places and returns the exact target, budget exhaustion returns `None`), and `tests/integration/test_network_match.py::test_two_peers_synchronize_barriers_and_resolve_a_boxed_in_capture` (a full two-peer, in-memory-transport match at the verified capture-producing start positions, asserting both peers independently agree on `outcome == "capture"`, matching `mutual_sign_off`, and an identical `log_sha256`).

**Quality gate results:**
```
447 passed, 1 skipped in ~20s
TOTAL coverage: 85.30% (required: 85.0%)
ruff check: All checks passed!
```

**Tasks checked off:** `docs/TODO.md` T0772-T0776 (Q.2 game-logic edge cases around barrier placement and identical start positions), T0124/T0125 (barrier declarations are public, re-framed around live real-time declaration rather than the sealed move log), T0849/T0850 (rules 15/16 — barrier declarations are now genuinely exercised end-to-end, not just proven-capable-in-isolation), T0636 (barrier-budget-exhaustion regression, now also covered at the live-wiring level, not just the `Board` primitive).

**Status:** committed.

---

### Post-Split Cleanup — Removed the Thief's Private Config and Every Cop-Side Capability to Run as the Thief

**What prompted this:** a direct review request pointing at a concrete, concerning finding — `config/thief/game.toml`, the thief's own private per-peer settings file, was still sitting inside this cop repo after the two-repo submission split (ADR-011's export step). Since the whole point of the mandatory two-repo split is that each side's private configuration, strategy overrides, and internal parameters are genuinely inaccessible to the other, a leftover copy of the thief's private config file directly undermines that guarantee — regardless of whether its actual contents were ever customized away from the shipped placeholder.

**What was found and removed, beyond the one file named in the request:**
- `config/thief/game.toml` deleted outright (not merely ignored or moved) — this repo now ships only `config/cop/`.
- `main.py`'s `serve` subcommand previously accepted `--role cop|thief` and would happily try to load `config/thief/game.toml` and run this process as a live thief MCP peer. Restricted to cop-only: the `--role` argument is gone entirely, `_serve` always constructs `AgentRole.COP`. Running `serve` in this repo can now only ever start a cop server — there is no flag, hidden or otherwise, that makes it act as the thief.
- The "Agent vs Agent (Two Computers)" GUI's `NetworkSetupDialog` had a "This computer's role" dropdown offering `cop`/`thief`. Locked to `cop` only (the combobox's `choices` no longer includes `thief`, and the backing `tk.StringVar` is hardcoded rather than read from `config/network_match.json`'s `peer.role`), so the same live-match capability gap is closed on the GUI path, not just the lower-level `serve` CLI path.
- `config/network_match.json`'s `team_1.repos` still pointed at the pre-split monorepo URL (`.../uoh-ay26-final-project`) for both `cop` and `thief` — corrected to the two real, separately-hosted repo URLs, so the identity handshake this file feeds (`NetworkMatchRunner._identity()`) advertises accurate, current public repo links rather than stale ones.

**What was deliberately left alone, and why:** `AgentRole.THIEF` as an enum value, and every generic, role-parameterized function that accepts it (`Board`, `BeliefMap`, `ManhattanHeuristicBrain`, `check_capture`, `is_boxed_in`, scoring, the four-tool wire protocol's `WIRE_ROLES` map, `config_dir_for`/`load_network_config`/`load_strategy_class`) — none of this is the thief's *private* information. It is the shared, public rulebook mechanics (docs/tasks.md) both sides' independently-run copies of this same forked codebase implement identically; a cop process necessarily has to reason about "the opponent, who plays the thief role" to run the protocol and score a match at all. Removing it would have broken the "shared game interfaces, protocols, schemas, public rules" this repo legitimately still needs, not just the thief's hidden state. Local, single-process practice modes (`play`'s Human vs Human / Agent vs Agent same-process modes, and the `demo`/`simulate` commands) were also left untouched: they never read any live opponent's config, never send anything over a real network, and use the same public heuristic class for whichever side isn't human-controlled — they are a sandbox, not a channel for this submission to actually compete as the thief in a real, graded match.

**Documentation brought in line with the actual, current repo capability, not just the code:** `docs/TODO.md` T0054/T0170/T0183/T0835/T0879 (all reference `config/thief/`'s historical existence or the old `--role cop|thief` flag) annotated to distinguish what was true during shared-monorepo development from what this specific exported repo can do today, without rewriting the historical record of how the codebase actually evolved. `docs/PLAN.md`'s ADR-011 gained a "Post-split update" note recording that the export it originally only described in the future tense has now actually happened, and how. `docs/PRD_fastmcp_networking.md`/`docs/PRD_gmail_gatekeeper.md` had their remaining actionable (non-historical) references to a live `config/thief/game.toml` or a `serve --role thief` command corrected to match the current cop-only reality. `README.md`'s `serve` and two-computer setup sections rewritten to state plainly that this repo can only run as the cop.

**Quality gate results (unchanged by this pass, confirmed by re-running, not assumed):**
```
447 passed, 1 skipped in ~19s
ruff check: All checks passed!
```

**Status:** committed.

---

### Post-Split Enhancement — Reachable-Area-Based Barrier Targeting

**What prompted this:** a direct follow-up question after explaining the cop's strategy -- asked for an honest assessment of whether it was good or needed enhancement. The honest answer was that the barrier heuristic was a real weak point: "barrier the neighbor closest to the belief peak" is a pure distance nudge with no sense of whether blocking that cell does anything useful, and no budget discipline (it spent a barrier every single turn it could, regardless of usefulness) -- exactly the gap `docs/TODO.md` T0256 already flagged as not built. Asked to enhance it on that basis.

**What was built:**
- `Board.reachable_area(source, extra_blocked=None)` (`domain/board.py`) -- a BFS flood fill counting open cells reachable from `source`, optionally treating one extra cell as blocked. This is the tool for asking "if I blocked this cell, how much of the thief's escape space would actually disappear," as opposed to "is this cell closer to my guess."
- `ManhattanHeuristicBrain._pick_move` rewritten around it: candidates are now `own`'s current cell *and* its open neighbors (previously only neighbors -- the cop's own cell is a legal barrier target per Sec. 3.3.4, but the old heuristic never considered it at all, so it had no way to express "seal the door behind me"). Each candidate is scored by `reachable_area(belief_peak, extra_blocked=candidate)`; the one minimizing that (tie-broken by distance to the peak, for determinism) is the best. If the best candidate only drops the reachable count by 1 -- i.e. it merely removes itself from the board, not a genuine chokepoint -- `_pick_move` returns `None` instead of spending the budget. Only a drop greater than 1 (an actual pocket getting disconnected) is worth a barrier.

**Why this addresses both flagged gaps at once:** the "does this cell matter" question and the "should I spend a barrier now" question turn out to be the same question once framed as a reachable-area drop -- a genuine chokepoint is worth blocking *and* is rare enough in open board play that the heuristic naturally holds its budget until the geometry (a wall, a corner, an already-placed barrier) actually creates one, closing T0256 without needing a separate, arbitrary "early game vs. late game" turn-count rule.

**Verified empirically before trusting it, same discipline as every barrier-related change this project has made:** re-ran the existing corner-scenario integration test's start positions (`cop_start=[2,0]`, `thief_start=[0,0]`) after the change and found the match still resolves to a genuine capture -- but now via a *different*, still fully legitimate Sec. 3.3.5 condition: a single barrier placement (at step 2) that happens to land exactly on the thief's true cell, rather than the multi-barrier boxed-in sequence the pre-enhancement heuristic needed several turns for. A broader sweep of eight other start-position combinations all converged to captures as well, none via a full boxed-in sequence within the tested move budgets -- consistent with the heuristic being smarter about *when* to spend a barrier, not yet capable of a multi-turn lookahead plan that deliberately engineers a chokepoint that doesn't exist yet. The existing integration test was renamed and its docstring corrected to describe what it actually now demonstrates (a barrier-driven capture via either Sec. 3.3.5 condition, with cross-peer synchronization as the property under test) rather than overclaiming a specific "boxed-in" mechanism it no longer needs to hit to prove the wiring correct.

**Tests added/updated:**
- `test_board.py`: five new tests for `reachable_area` (open board, a real chokepoint disconnecting a 3-cell pocket, a non-chokepoint dropping by exactly 1, and both zero-area edge cases).
- `test_strategy.py`: replaced the old "always places somewhere in open space" test (no longer true, correctly) with `test_cop_brain_declines_to_place_a_barrier_in_fully_open_space` and added `test_cop_brain_seals_its_own_cell_as_the_sole_doorway_into_a_pocket`, directly exercising the new "seal your own cell" capability the old heuristic structurally couldn't reach.
- `test_network_match_barrier.py`: replaced the open-space "places somewhere" test with a genuine-chokepoint scenario proving `_maybe_place_barrier` returns the exact expected target and updates the board/budget correctly; added a companion test proving it declines in open space.
- `test_network_match.py`: renamed and re-documented the barrier-capture integration test to match the mechanism actually observed.

**Quality gate results:**
```
454 passed, 1 skipped in ~21s
TOTAL coverage: 85.39% (required: 85.0%)
ruff check: All checks passed!
```

**Tasks checked off:** `docs/TODO.md` T0253 (barrier heuristic upgraded from a distance nudge to a reachable-area chokepoint search), T0256 (budget timing now usefulness-driven rather than unbuilt).

**Status:** committed.

---

### Post-Split Fix — Corrected the Cop's Team Identity and Finished the `[game]` Section

**What prompted this:** a direct request to check whether `config/cop/game.toml` was accurately filled in. It wasn't, in two ways.

**Finding #1 — a real typo, not just an unfilled placeholder:** `group_name`/`group_id` had already been changed from the `"TBD"` placeholder flagged in the Chapter 11 sanity sweep to `"uof-ay26"` -- but that value matches nothing else in the project. Every other reference to this team's identity (`config/network_match.json`'s `team_1.name`, the actual GitHub org and both repo names, `README.md`, `ProgressDoc.md`) consistently uses `"uoh-ay26"`. Fixed to match: an 8-character code, no spaces, satisfying rule 45, and now internally consistent across the repo instead of silently diverging from it.

**Finding #2 — the `[game]` section was still incomplete relative to the rulebook's own format:** `docs/tasks.md` §13.4.1's illustrative `config/game.toml` excerpt shows `[game]` containing `group_name`, `group_id`, `sub_game_number`, `members`, and `repos` together -- `docs/TODO.md` T0556 tracked finishing this and had been sitting unchecked. Added `sub_game_number = 1`, `members` (the same two real names already used in `config/network_match.json`, not invented IDs), and `repos = { cop = ..., thief = ... }` (the same two real, now-correct repo URLs fixed in an earlier session's `config/network_match.json` correction).

**An honest limitation surfaced rather than papered over while doing this:** none of `[game]`'s fields are actually read by any loader in this codebase -- `shared/config.py::load_network_config`/`load_strategy_class` only ever parse `[network]`/`[strategy]`. The live two-computer match's actual team identity and repo URLs come from `NetworkMatchSettings`, populated from `config/network_match.json` or the GUI form, not from this TOML file. Filling `[game]` in accurately means matching the rulebook's documented private-file shape with truthful values -- it does not by itself wire this table into the running system, and `README.md`/`docs/TODO.md` say so explicitly rather than implying it now does something it doesn't.

**Deliberately not added:** the rulebook's illustrative excerpt also shows an `[llm]` section (`model`, `step_deadline_seconds`). Not added here, because it would misrepresent this project's actual implementation -- this codebase's real Gemini model/deadline configuration is entirely `.env`-based (`GEMINI_MODEL`/`GEMINI_API_KEY`, `services/gemini_agent.py`), not TOML-based, and adding an inert `[llm]` section here would create a second, fake-looking source of truth for a value nothing reads from this file.

**Quality gate results:**
```
454 passed, 1 skipped in ~20s
ruff check: All checks passed!
```

**Tasks checked off:** `docs/TODO.md` T0556 (`[game]` section finalized, with an honest wiring caveat), T0879 (rule 45 now genuinely satisfied, not a `"TBD"` placeholder).

**Status:** awaiting review before committing.

---

### Post-Split Enhancement — Renamed the CLI to Match the Reference Example's Invocation Style

**What prompted this:** the user shared a screenshot of `docs/tasks.md` §15.4 ("How to Run"), the course's optional reference example repo's own invocation syntax (`peer --role police|thief`, `replay --log ...`), and asked whether this repo was "ready to run, matching the requested way." The honest answer, given first: that section is Appendix D's illustrative example runner, explicitly flagged non-mandatory ("[MUST NOT be treated as a submission template]", §15.1/15.5.1) -- and the exact local command name has zero effect on cross-team play, since two teams only ever interact over the wire protocol (`negotiate`/`receive_turn`/`submit_audit`/`receive_control`, and the `WIRE_ROLES = {"cop": "police", "thief": "thief"}` translation already in place), never by invoking each other's CLI. That compatibility work was already done in an earlier session's four-tool protocol migration.

The user asked to rename the CLI to match anyway, for consistency and familiarity when comparing notes with other groups, even after that clarification.

**What was renamed, purely a local invocation change with no behavior change underneath:**
- `main.py`'s `serve` subcommand renamed to `peer`, now requiring `--role`, with `choices=["police"]` -- the only value this repo, having no thief config, can legitimately support. Passing `--role thief` fails cleanly with argparse's own "invalid choice" error rather than a deeper, more confusing failure. `_serve()` renamed to `_peer()`; behavior unchanged (still starts the cop's FastMCP server via `build_peer_server(AgentRole.COP.value, ...)`).
- `replay --log-file PATH` renamed to `replay --log PATH` (via `dest="log_file"`, so the rest of the code needed no change).
- `README.md`, `docs/PLAN.md`, `docs/PRD_fastmcp_networking.md`, `docs/PRD_gui_replay.md`, and the relevant `docs/TODO.md` entries (T0153, T0183, T0421, T0835, T0854) updated to the new invocation syntax, with the historical entries left describing what was actually true at the time they were written rather than rewritten to pretend the old syntax never existed.

**Verified live, not just asserted:** ran `python -m police_thief --help`, `peer --help`, `peer --role thief` (confirmed it fails with a clean argparse error), and `replay --help` after the change to confirm the new syntax behaves exactly as intended before calling it done.

**Quality gate results:**
```
454 passed, 1 skipped
ruff check: All checks passed!
```

**Status:** committed.

---

### Post-Split Fix — `peer` Upgraded from an Idle Listener to a Real Match Runner

**What prompted this:** while explaining the just-completed CLI rename, the user asked directly: "can I play using these commands against my group's thief?" Answering honestly required actually reading what `_peer()` (formerly `_serve()`) did -- and it turned out to only start a bare FastMCP server via `build_peer_server`/`run_peer_server`, with nothing ever calling `NetworkMatchRunner.run()`. It queued incoming messages into `PeerInboxes` and did nothing else. This is a real, previously-unnoticed gap: `docs/tasks.md` Appendix D's reference example's own `peer --role police` command *does* play a full match (Sec. 15.2.1 lists board movement, barriers, scent, belief, Commit-Reveal, and audit as part of what that example's peer demonstrates) -- ours didn't, since the actual match-driving logic (`NetworkMatchRunner`) had only ever been wired into the `play` GUI's "Agent vs Agent (Two Computers)" flow (`gui/network_match_app.py`), never into the plain CLI.

**What was built:**
- `services/network_match_config.py` (new): `load_network_defaults`/`validate_mcp_url`/`DEFAULT_REPORT_EMAIL` extracted out of `gui/network_setup.py` into a plain module with no tkinter dependency, so `main.py` (a non-GUI command) can reuse the exact same, already-tested `config/network_match.json` parsing logic the GUI setup screen uses, rather than duplicating it or importing a GUI module into the CLI layer. `gui/network_setup.py` now imports these from the new module and re-exports them (`__all__`), so no existing import site or test needed to change.
- `main.py::_peer` rewritten: reads `config/cop/game.toml`'s `[network]` section for connection details (port, opponent URL -- the already-established convention for this "lower-level" path) and `config/network_match.json` for match/team/session details (game ID, teams, repos, shared secret, email), builds a real `NetworkMatchSettings`, starts the FastMCP server in a background thread (exactly like `NetworkMatchApp` does), and calls `NetworkMatchRunner.run()` in the foreground with `emit=print` -- so running `peer --role police` in a terminal now streams the same negotiate/turn/audit progress messages the GUI shows in its log panel, and blocks until the match completes.

**Verified with a real two-process smoke test over actual HTTP before trusting it, not just asserted:** `McpPeerTransport` combined with `NetworkMatchRunner.run()` had never been exercised by any existing test -- every prior `NetworkMatchRunner` test used `MemoryTransport` (in-process queues), and `McpPeerTransport` itself had only ever been exercised via `test_mcp_client.py` in isolation, never through a full match. Built a throwaway scratch script: ran the real `main._peer()` (via `main.parse_args(["peer", "--role", "police", ...])`, the exact code path a user's terminal invocation takes) against a hand-built thief-role `NetworkMatchRunner` counterpart, both with real `build_peer_server`/`run_peer_server` on real localhost ports (18801/18802), no mocking. It worked end to end: a real 35-step match, real HTTP round trips (visible in the `INFO: 127.0.0.1:... "POST /mcp HTTP/1.1" 200 OK` uvicorn access log), matching `result_SMOKE-TEST.json` files written by both sides with `"mutual_sign_off": true`. Scratch script and configs deleted after confirming success -- this was a one-off verification, not a permanent test file.

**Deliberately not added as a permanent automated test:** `main.py` is excluded from the coverage requirement (`pyproject.toml`'s `[tool.coverage.run] omit`, a pre-existing project convention for the thin CLI/GUI-wiring layer), and the two pieces `_peer` composes -- `load_network_defaults` and `NetworkMatchRunner.run()` -- are each already independently tested (`test_network_setup.py`, `test_network_match.py`). A dedicated `main.py` test would mean either running a slow real-HTTP match inside the suite or mocking away the exact wiring the smoke test just proved works for real; the empirical verification was judged the stronger evidence for this specific, one-time integration risk, consistent with this project's own "verify empirically" practice used throughout.

**Quality gate results:**
```
454 passed, 1 skipped
TOTAL coverage: 85.41% (required: 85.0%)
ruff check: All checks passed!
```

**Status:** committed.

---

### Post-Split Finding — `Orchestrator` Is No Longer the Single Match Entry Point (Documented, Not Refactored)

**What prompted this:** the user shared `docs/tasks.md` §15.3 ("Code Layout"), the same Appendix D reference-example architecture description as the earlier "How to Run" screenshot -- `SimulationSdk`/`PeerRuntime`/`infra` naming, a 150-line-per-file cap, `police_class`/`thief_class` extension points. Checked against the full 55-rule list in Appendix E: none of this is a separate mandatory rule, confirming it's the same non-mandatory illustrative category as before -- restructuring this project's own, independently-designed `domain`/`services`/`gui`/`shared` layout to mimic those names would work against §15.1/§15.5.1's own instruction not to treat that repo as a submission template, not for it.

**What reviewing it turned up instead, a real finding:** rule 3 in Appendix E sits right next to this section -- *"[MUST] Define the Orchestrator component as the single entry point for all sub-systems."* Checked whether that's still true, and it isn't. `services/orchestrator.py::Orchestrator` (Chapter 8) is real and tested, but grepping `services/network_match.py` and `main.py` for any reference to it turned up none. `NetworkMatchRunner` -- the class that drives every match actually played through this repo today, both via the `play` GUI and the newly-real `peer` CLI command -- reimplements its own turn loop, audit exchange, and control messages directly, entirely bypassing `Orchestrator`. `docs/TODO.md` T0837 had already flagged a narrower version of this (Gatekeeper/Gmail-reporting not routed through the Orchestrator), but not this larger one: the core turn loop itself now has two separate, parallel implementations, and `Orchestrator` is effectively dead code on the path every real match actually takes.

**Decision, made explicitly rather than assumed:** asked the user directly whether to refactor `NetworkMatchRunner` to route through `Orchestrator` (making rule 3 genuinely true again) or to document the gap honestly and leave it. Chose to document: `NetworkMatchRunner` is working and was just empirically verified end-to-end over real HTTP (real `mutual_sign_off: true`) in the previous entry; merging it into `Orchestrator` now is a nontrivial architectural change with real risk of regressing that, and doing it without a concrete plan the user has weighed in on would trade a documented, honest gap for an unreviewed, riskier one.

**Tasks updated:** `docs/TODO.md` T0837 rewritten to describe the full gap (both the original Gatekeeper/reporting piece and the larger, previously-unnoticed turn-loop duplication), rather than the narrower framing it had before.

**Status:** committed.

---

### Live-Match Fixes — Gemini Always Falling Back, and a Mid-Match Crash on Disconnect

**Context:** substantial work happened to this codebase between sessions -- the reference v3 four-tool protocol alignment, peer-identity validation at negotiation, and the six-game series runner (`NetworkMatchSeriesRunner`) -- none of it documented here as it landed, so this entry does not attempt to reconstruct that history; it only covers the two real bugs found and fixed in this pass, against the codebase as it stood.

**Bug #1 -- Gemini always falling back, reported 0 tokens used:** a real two-computer match kept using the deterministic heuristic every turn despite a configured `GEMINI_API_KEY`. Compared against the sibling thief repo, which had already hit and fixed the identical symptom (`db699bf Bound Gemini turn latency`, `e7edcd2 Use faster Gemini model for turns`): the cop's `.env` and `services/gemini_agent.py` both still used `DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"`, a model the thief team found too slow/unreliable under a bounded per-turn deadline. Ported their fix: `gemini-3.1-flash-lite` as the default model, `MIN_GEMINI_HTTP_TIMEOUT_SECONDS = 10.0` decoupling the raw HTTP client timeout from the (possibly tighter) per-turn budget so a short `GEMINI_TIMEOUT_SECONDS` can't itself guarantee a call is cut off before the provider replies, a larger `max_output_tokens` (64, was 24), and a more lenient `_parse_response` that also matches a move's short wire code (not just its full name) and strips a `"MOVE:"`-style prefix some models add despite the prompt's instructions. The user's actual local `.env` (`GEMINI_MODEL=gemini-3.6-flash`, `GEMINI_TIMEOUT_SECONDS= 30`) was updated to match. Separately clarified for the user, not fixed here: the "0 tokens" in match results is not evidence either way about whether Gemini ran -- `TokenUsage()` is constructed with all-zero defaults everywhere in this codebase; no code path has ever tracked real per-call token counts (a genuine, still-open Rule 54 gap).

**Bug #2 -- an unhandled `PeerClientError` crashed the whole process on a mid-match disconnect:** reported twice with real tracebacks from live matches over ngrok -- once from `send_turn` (a 502 from a dead tunnel), once from `receive_turn` (a plain timeout). `NetworkMatchRunner.run()` had no handling for either; the exception propagated all the way through `main.py::_peer` and killed the process, including every remaining sub-game of a `NetworkMatchSeriesRunner` series. Checked the thief repo for an existing fix first (this project's own repeated pattern of the same bug) -- it has the identical gap, unfixed there too, so this isn't a port, it's the actual first fix.

Restructured `run()` (a pure extraction to make this catchable without re-indenting the whole turn loop): everything after a successful negotiation now lives in `_play_turns_and_report`, called from inside a `try/except PeerClientError` in `run()`. On catch, `_write_technical_loss_result` records the match as a technical loss (Sec. 9.2, 0/0) using whatever this side sealed before the opponent went dark, with `mutual_sign_off=False` -- honestly reflecting that the opponent never confirmed anything past that point, unlike a normal cross-verified result. `_send_control("quit", "STOPPED")` is attempted (best-effort; already safely swallows its own `PeerClientError` via `McpPeerTransport.send_control`'s existing `contextlib.suppress`).

**Verified with a real integration test reproducing the actual failure, not just a unit stub:** `test_a_mid_match_disconnect_resolves_to_technical_loss_on_both_sides` wraps a real `MemoryTransport` in a small `_DisconnectingTransport` that starts raising `PeerClientError` on `send_turn` after one successful turn, runs two real `NetworkMatchRunner`s concurrently, and confirms *both* sides -- the one that saw the failure directly, and the other side via its own `receive_turn` timing out -- resolve to `technical_loss`/`0`/`0`/`mutual_sign_off: False` instead of raising. Also fixed the test file's own `MemoryTransport.receive_turn`, which propagated a raw `queue.Empty` instead of `PeerClientError` the way the real `McpPeerTransport` does -- a test double drifting from production behavior, caught while writing this exact test.

**Known, intentionally out-of-scope remainder:** this only catches `PeerClientError` *after* negotiation succeeds. If the opponent is gone before negotiation even starts (e.g., every sub-game after the first one in a series where the opponent has fully disappeared), that call site is still unguarded and will still crash. Not fixed now -- flagged honestly rather than expanded into an open-ended resilience pass beyond what was actually reported.

**Quality gate results:**
```
481 passed, 1 skipped
TOTAL coverage: 85.84% (required: 85.0%)
ruff check: All checks passed!
```

**Status:** awaiting review before committing.

---

### Tie Rule Applied to the Aggregate Series Score (75-75 -> 77-77)

**Context:** the first full six-game series (G001) ended with every sub-game decided by capture, giving each team 3 x 20 (as cop) + 3 x 5 (as thief) = 75 raw cumulative points. The user asked whether the mandatory Tie Rule was being applied. Verified directly against the PDF before changing anything: the Tie Rule box (Sec. 9.2.8-9.2.9, footer page 71) and Appendix F Table 17 row 5 (footer page 137) both mandate that when the cumulative score of all sub-games between two groups ends in a tie, each group receives the fixed tie score (2). The team's agreed interpretation: a credit on TOP of the raw subtotal, so 75-75 must be reported as 77-77.

**The bug:** the tie rule existed in the codebase (`domain/league.py::apply_tie_rule`) but was dead code -- never called from the aggregation path -- and it implemented a replacement reading (tied totals became 2-2) rather than the additive credit. The emailed `result_<game_id>.json` therefore carried raw tied totals (75-75) with no tie credit in any form. Worse, the totals that actually get emailed are computed independently in `services/submission_artifacts.py::finalize_submission_bundle` (summing sub-game rows), and its own validator enforced the *uncredited* raw sum as the expected `final_result.total_score`.

**The fix (all three layers, kept consistent):**
1. `domain/league.py::apply_tie_rule` now returns `(own + tie_score, opponent + tie_score)` on an exact tie.
2. `services/network_match.py::NetworkMatchSeriesRunner.run()` applies `apply_tie_rule` to the series totals before writing `team_scores`, so the internal aggregate and the reference-format bundle agree.
3. `services/submission_artifacts.py`: `finalize_submission_bundle` credits `FIXED_TIE_SCORE` (new constant in `shared/game_config.py`, Table 17 row 5, fixed at 2) to each side when `series_tie` is true, and `validate_submission_directory`'s derived-value check now expects the credited totals -- a tied bundle claiming raw totals is rejected as `derived_value_mismatch`.

`series_tie`/`winner_group` semantics are unchanged (the credit is symmetric). Per-sub-game scoring in `domain/scoring.py` is untouched -- Table 17's tie row is a cumulative-level rule.

**Tests:** `test_league.py` tie cases updated to the additive semantics (including the literal 75-75 -> 77-77 case); `test_submission_artifacts.py` gained a tied-series bundle test (25-25 raw -> 27-27 reported, validator clean) and a negative test proving the validator rejects a tied bundle missing the credit. The identical fix and tests were mirrored to the sibling thief repo so both peers' independently-computed aggregates agree (a mismatch would look like tampering in the paired reports). While there, fixed the thief-only `test_network_match_terms.py` to read `setting` from the agreed config (`params.world.map_area`) instead of a hardcoded "New York" -- it had been failing since the team agreed on "Haifa".

**Quality gate results:** cop: 566 passed, 1 skipped; ruff clean. Thief: 578 passed; ruff clean.

**Status:** awaiting review before committing.

---

### Strategy Strengthening from Two Reviewed Live-Match Logs (Pursuit + Evasion)

**Context:** the team reviewed two real match logs against another team and lost on both sides. As police: 35 moves, zero barriers placed, and a textbook tail-chase (the cop reached one step behind the thief around step 13, then followed its decayed scent trail for 20 more turns, twice oscillating between the same two cells). As thief: the thief drifted down the west edge into the (5,0)/(6,0) corner region and finally stepped east into the cop's occupied cell -- an immediate capture -- during a stretch where the opponent's scent frames gave no usable center and the escape logic was effectively blind. All changes were made while a live match was running: source-only edits (Python never re-reads loaded modules), no touch of config/game.json, network_match.json, TOMLs, .env, results/, or the venv.

**Change 1 -- interception and containment for the cop (`domain/strategy/tactical_planner.py`, both repos):** two new scoring terms in the cop branch, gated on a genuinely focused target (max belief-target probability >= 0.3, which is exactly the live-match condition where a fresh public scent center, a barrier deduction, or a published cell yields one candidate at probability 1.0):
- *Interception* (`-4.0 x intercept_distance`): scores each destination against every believed cell's best one-step flight from the cop's current cell (new `_evasive_reply` helper, BFS-based, deterministic tie-break) -- the cop cuts the corner instead of stepping onto year-old scent.
- *Containment* (`-0.35 x containment`): the believed thief's `Board.reachable_area` with the cop's destination treated as blocked -- standing in a pocket doorway now scores like the cage it is.
Against a flat searching belief both terms stay zero, preserving the proven sweep behavior byte-for-byte (the recorded G001 capture-replay test still selects the identical 32-move path).

**Change 2 -- open-space preference for the thief (same file, both repos):** a new `+0.6 x escape_space` term: reachable area from each destination with the believed cop treated as one more wall. A region whose sole doorway the cop occupies now reads as ~zero escape space even when one-step mobility looks healthy, so the thief stops drifting into corner pockets like the (5,0)/(6,0) trap from the reviewed loss. The existing hard risk tiers (direct capture / proximity / trap) are unchanged and still dominate.

**Change 3 -- the endgame barrier closer (`services/network_match.py`, both repos):** root cause of the zero-barrier game: `_maybe_place_barrier` consulted only the diffuse BeliefMap, never the fresh single public scent candidate the movement planner already trusted, so neither the confidence-gated direct block (threshold never met) nor the structural pocket rule (no pockets ever form on an open board) could fire. New module-level `_cornered_candidate_barrier`, tried before the brain heuristic: when the single public thief candidate is adjacent to the cop AND already cornered (at most two open exits beyond the cop's cell), wall it -- a capture claim if the thief is still there, a sealed pocket otherwise. Guards: exactly one candidate, cop keeps >= 3 open neighbors (never repeats the reviewed G001 self-boxing failure), and in open field (3-4 exits) the rule is silent so a one-turn-stale scent center can never wall off the cop's own pursuit path.

**Tests:** three new unit tests in `test_network_match_barrier.py` (cornered candidate is walled; open-field candidate is not; the rule declines rather than seal the cop's own escape); the existing G001 sweep-capture characterization test now doubles as the proof that the confidence gate preserves blind-search behavior. Everything mirrored to the thief repo (which plays cop in alternated sub-games and had no barrier test file at all -- copied).

**Quality gate results:** cop: 569 passed, 1 skipped; ruff clean. Thief: 585 passed; ruff clean.

**Status:** awaiting review before committing. Takes effect on the NEXT match launch; the currently running match is untouched.

---

### Root Cause of the Repeated Cop Losses: Saturated Opponent Scent Blinded Every Inference

**Context:** a third police log was reviewed after another loss. Critically, it is move-for-move IDENTICAL to the first police log across all 35 steps -- proof that (a) the running process was still on the pre-improvement code (Python does not reload modules), and (b) the cop was playing a fully deterministic blind sweep, because two live games against a real opponent cannot coincide by chance unless zero opponent-dependent evidence reaches the planner.

**The real bug, found by reading the opponent's public repository (AMIR13BD/Game-P2P-Cop-Chase-Thief, `src/thief_agent/domain/smell.py`):** their scent model applies a HARD CAP -- `tau_next = min(0.9, max(0, (1-rho)*tau_old + delta))` -- with a 5x5 kernel depositing 0.90/0.62/0.42/0.20/0.14/0.04 by offset. Our `_infer_public_scent_center` inverts the UNCAPPED signed rule `new = (1-rho)*old + emission` and requires the peak innovation to clear `min_center_intensity` (0.5) with a clear gap. Against a capped emitter this fails structurally: once the opponent lingers or backtracks, its neighborhood saturates at 0.9 and the apparent innovation collapses to ~0.09 (a saturated cell can only "gain" the decay it just lost). Every frame then returned `None`.

The downstream consequences chain exactly onto the observed losses. As cop: `public_thief_candidates` stayed empty every single turn, so no capture claim could ever be truthfully made -- at step 13 our cop stood on (5,6), the thief's actual cell, and could not claim it -- and the belief stayed flat, so the deterministic sweep replayed identically. As thief: `public_cop_candidates` stayed empty, so the escape logic had no threat set and walked into the cop's cell. It also means the pursuit/evasion terms added in the previous entry were dormant, since they gate on a focused target.

**Fix -- `_infer_public_scent_candidates` (new, both repos), a cap-aware second stage:** the exact singleton inference runs first and is returned unchanged when it succeeds (all existing behavior preserved). When it returns `None`, the fallback identifies cells that (a) sit AT the emission cap yet still show positive innovation -- staying at the cap requires a fresh deposit, since pure decay would drop them below it -- and (b) are within one legal step of the last inferred anchor. It returns that small set (at most 4 cells; wider ambiguity returns () rather than fabricating certainty), and critically KEEPS the anchor instead of discarding it, so a saturated blob no longer breaks the tracking chain frame after frame.

Both role branches consume the set: the cop pursues it (feeding the interception/containment terms and the endgame barrier rule, which needs exactly one candidate), and the thief protects against the union of it (feeding the existing hard risk tiers). `emission_cap` is read from the agreed `params.scent.center_intensity`, not hardcoded.

**Tests:** three new cases in `test_capture_safety.py` in both repos, driven by a faithful replica of the opponent's capped kernel (`_opponent_capped_step`): an ordinary step onto one's own trail still yields a small set containing the true cell; the reviewed oscillation scenario is asserted to defeat the singleton inference (`is None`) yet still yield a small set containing the true cell; and with no anchor the fallback stays silent. The existing uncapped-path test is untouched and still passes, proving the exact inference is unchanged.

**Regarding commit 67f5c8d "feeling better":** the strategy code in that commit is identical to what preceded this session's work -- `_infer_public_scent_center` and the planner were the same. What differed was the opponent, not our agent. This entry addresses the actual asymmetry.

**Quality gate results:** cop: 572 passed, 1 skipped; ruff clean. Thief: 588 passed; ruff clean.

**Status:** awaiting review before committing. Takes effect on the NEXT launch; the running match is untouched.
