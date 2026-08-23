# PRD: Commit-Reveal Cryptographic Protocol & Step-0 Fairness Declaration

**Mechanism owner:** `src/police_thief/services/commit_reveal.py`, `src/police_thief/services/step0.py`; `config_fingerprint` in `shared/game_config.py`
**Parent document:** `docs/PRD.md` (see §7, "Per-Mechanism PRD Documents")
**Corresponds to:** `docs/tasks.md` Chapter 5 ("Cryptographic Security & Zero-Knowledge Protocol") — specifically §5.1-5.4 (commit-reveal, audit) and §5.5 (Step-0). The actual **network wiring** of the four-step protocol (Commit → Acknowledge → Reveal → Audit, enforced in strict order over FastMCP) is **Chapter 8's** Orchestrator/legal-state-machine territory and explicitly out of scope here — see "Constraints & Limitations" below.

---

> **Current implementation update (2026-08-14):** the limitations below are a
> historical Chapter-5 snapshot. The live `NetworkMatchRunner` now seals every
> turn, exchanges complete nonce reveals after terminal gameplay, attaches the
> signed `step: 0` / `type: "system_spec"` attestation, verifies peer records,
> and gates mutual sign-off on matching result evidence. This path has completed
> five mutually verified counted six-game series.

## 1. Description & Theoretical Background

In a referee-less P2P match, the central cheating risk is "hindsight rewriting": changing a move, or denying a prior declaration, after the fact. The fix here is mathematical, not contractual — a **commitment** (Blum 1983's "coin-flipping over the telephone") cryptographically binds a side to `State + Move + Intent` *before* either side reveals anything, closing off the ability to change one's mind retroactively without breaking a previously-transmitted hash. The four-step protocol embodies a **Zero-Knowledge** flavor (Goldwasser–Micali–Rackoff 1989): at commit time, the opponent gets certainty a decision exists, with zero knowledge of its content — commitment is separated from disclosure.

Step-0 addresses a different but related trust gap: is it fair for a modest laptop to compete against a team running a heavy LLM on a powerful cloud machine? Step-0 doesn't equalize hardware — it makes any advantage **visible and auditable** via a signed declaration, feeding the league's computational-fairness scoring incentive (Chapter 9).

## 2. Specific Requirements, Input/Output, Performance Metrics

| Requirement | Implementation | Expected input → output |
|---|---|---|
| `H_commit = SHA256(State‖Move‖Intent‖Nonce)` | `commit(state, move, intent, nonce=None) -> Commitment` | any JSON-serializable `state`/`move`/`intent` → a 64-hex-char digest |
| Canonical serialization (sorted keys, fixed separators) | `canonical_json(data) -> bytes` | `{"z":1,"a":2}` and `{"a":2,"z":1}` → identical bytes |
| Cryptographically-secure Nonce, never `random` | `generate_nonce()` via `secrets.token_hex(32)` | 64 hex chars, unique per call |
| `verify(state, move, intent, nonce, h_commit) -> bool`, constant-time | `secrets.compare_digest` internally | correct reveal → `True`; any single-field tamper → `False` |
| `Commitment` never carries raw content | Dataclass fields limited to `{h_commit, nonce}` | structurally verified via `dataclasses.fields` |
| Mutual audit over a whole log | `audit_log(list[LogEntry]) -> AuditResult` | one tampered entry among N → `AuditResult(verified=False, tampered_index=<i>)` |
| Step-0 hardware spec (OS, CPU, RAM, GPU, LLM model) | `gather_hardware_spec()` | on this dev machine: `HardwareSpec(os_name='Windows', cpu_count=16, ram_gb=15.71, ...)` |
| Git commit hash per declaration | `get_git_commit_hash()` | real repo → 40-char SHA-1; non-repo directory → `GitCommitHashError` |
| HMAC-SHA256 signed declaration | `sign_step0`/`verify_step0_signature` | correct key → verifies; wrong key or any post-signing edit (including nested `HardwareSpec` fields) → fails |
| Config "locking" via fingerprint | `config_fingerprint(path) -> str` (SHA-256 over canonical JSON) | any change to `config/game.json` — including the otherwise-*fixed* scent parameters — changes the fingerprint |
| Performance | All operations are single SHA-256/HMAC calls over small JSON payloads; negligible cost | full 145-test suite runs in ~9.5s |

## 3. Constraints, Limitations, Alternatives Considered & Rationale

- **Scope boundary — crypto primitives vs. network protocol:** this chapter builds `commit`/`verify`/`audit_log`/Step-0 signing as pure, standalone functions. It deliberately does **not** wire them into `mcp_server.py`/`mcp_client.py`, nor build the four-step handshake's live sequencing/enforcement (rejecting an out-of-order Reveal, converting a failed audit into a live `MatchOutcome.TECHNICAL_LOSS`, exchanging Step-0 declarations before match start). All of that requires the Orchestrator and legal state machine that Chapter 8 builds — attempting it here would mean inventing throwaway state-machine logic ahead of its own chapter, the same incremental-layering discipline applied since Chapter 1.
- **Design choice — generic primitives over bespoke wrappers:** `commit()`/`verify()` accept any JSON-serializable `state`/`move`/`intent`. Rather than building a dedicated `sign_capture_claim()` or `sign_barrier_declaration()` function, this mechanism demonstrates that the *same* generic primitive already covers both (`test_capture_claim_can_be_sealed_and_verified_via_the_generic_commit_primitive`, `test_barrier_declaration_can_be_sealed_and_tamper_detected`) — mirroring how `check_capture()` was deliberately kept generic across move-based and barrier-based captures in Chapter 3. Avoids duplicate, near-identical code (DRY).
- **Design choice — HMAC-SHA256, not a bare hash, for Step-0 signing:** "signed with a pre-shared key" requires a *keyed* MAC to authenticate origin; a plain `SHA256(data ‖ secret)` construction is naive and vulnerable to length-extension attacks. `hmac.new(key, payload, sha256)` is the textbook-correct primitive.
- **Design choice — config fingerprint over a bespoke per-parameter lock:** rather than inventing a separate "locking" mechanism specifically for the three scent parameters (Sec. 4.2.6), `config_fingerprint()` hashes the *entire* canonical shared config. This closes the scent-locking requirement as a side effect of a more general mechanism (any physics parameter drift, not just scent, becomes detectable), reusing the same `canonical_json` helper `commit_reveal.py` already provides — one more DRY win.
- **A real bug found and fixed during implementation:** the Windows RAM-detection helper (`_detect_ram_gb`) initially used a `ctypes.Structure` with only 4 of the 9 fields Windows' real `MEMORYSTATUSEX` struct requires. `GlobalMemoryStatusEx` validates `dwLength` against its own fixed struct size and silently no-ops on a mismatch — the code ran with no exception, but always reported `0.0 GB`. Caught by checking the actual return value against a manually-verified standalone script before trusting it in a test (the same "verify empirically before writing an assertion" discipline used throughout this project), then fixed by using the complete, correctly-ordered 9-field struct.
- **Limitation — RAM/GPU detection is best-effort:** RAM detection covers Windows/Linux/macOS via stdlib-only means (`ctypes`, `/proc/meminfo`, `sysctl`) and falls back to `0.0` on any failure or unsupported platform, never raising. GPU presence is caller-supplied rather than auto-detected, since GPU detection is genuinely vendor/platform-specific and out of scope for a lightweight, dependency-free fairness declaration.
- **Resolved — live match logs now exist and audit clean.** This section previously recorded "no live match log yet": `LogEntry`/`audit_log` were tested only in isolation and against a synthetic multi-turn sequence, because `run_local_match` had no crypto layer wired in. That wiring landed in Chapter 8, and five counted six-sub-game series have since been played, each sub-game recording a real turn-by-turn log. Re-running `audit_log` over the retained logs returns `AuditResult(verified=True, tampered_index=None)`, and flipping a recorded move or nonce in a copy is still caught at the exact index — so the primitive is now evidenced against real matches, not only synthetic ones. The original synthetic test (`test_multi_turn_log_audit_catches_a_post_hoc_tampering_attempt`) is retained as a regression guard.
- **Limitation — token usage tracking is a bare counter:** `TokenUsage` (Sec. 5.5.4) exists as a minimal accumulator; it has nothing to count yet since no LLM integration exists (Chapter 6).
- **Alternative considered — wiring Step-0 exchange into the FastMCP layer now:** rejected for this chapter; Step-0 exchange requires a match-start gate that only the Orchestrator (Chapter 8) can meaningfully own.

## 4. Success Criteria & Test Scenarios

All satisfied, per `tests/unit/test_commit_reveal.py`, `test_step0.py`, and `test_config_fingerprint.py` (40 new tests directly on this mechanism; 145 tests total project-wide, 99.57% coverage, zero lint violations):

1. `commit`/`verify` round-trip correctly; any single tampered field (state, move, intent, nonce, or the commit hash itself) is caught.
2. Nonce generation is cryptographically random (never `random`), 64 hex characters, unique per call — never reused unless explicitly supplied for a `verify()` recomputation.
3. `Commitment` is structurally incapable of carrying raw move/intent content — only `{h_commit, nonce}` exist as fields.
4. `audit_log` passes on a clean log, pinpoints the exact index of a single tampered entry, is deterministic across repeated runs, and correctly handles the empty-log edge case.
5. The same generic `commit`/`verify` primitives correctly seal and tamper-detect both a `CaptureClaim` and a barrier-placement declaration, with no bespoke per-claim-type code.
6. Step-0: hardware spec gathering succeeds with a real, verified-positive RAM figure on this Windows dev machine (with mocked-but-faithful tests for the Linux/macOS code paths this machine can't natively exercise); git commit hash retrieval works against this real repository and fails cleanly outside one; HMAC signing/verification correctly rejects a wrong key, a post-signing edit to any top-level field, and a post-signing edit to a *nested* field (`HardwareSpec`).
7. `config_fingerprint` is stable for identical content regardless of key ordering, and changes if *any* shared-config value changes — including the otherwise-fixed scent parameters, directly demonstrating Sec. 4.2.6's "cryptographic locking" requirement.
