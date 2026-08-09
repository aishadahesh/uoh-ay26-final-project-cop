"""Independent local-truth peer runtime over the four-tool MCP protocol."""

from __future__ import annotations

import json
import math
import platform
import re
import secrets
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from threading import Event

from police_thief.domain.belief import BeliefMap
from police_thief.domain.board import Board, Move, Position
from police_thief.domain.capture import cop_capture_cells, is_boxed_in
from police_thief.domain.hints import TemplateHintProvider
from police_thief.domain.league import apply_tie_rule
from police_thief.domain.replay import save_log
from police_thief.domain.scent import ScentField
from police_thief.domain.scoring import MatchOutcome, score_for
from police_thief.domain.strategy.manhattan_brain import ManhattanHeuristicBrain
from police_thief.services.commit_reveal import LogEntry
from police_thief.services.gemini_agent import GeminiAgentAdvisor, TacticalContext
from police_thief.services.match_reports import (
    RepoCrossLinks,
    ResultTeamIdentity,
    TeamInfo,
    build_config_snapshot,
    build_declaration,
    build_match_result,
    save_config_snapshot,
    save_declaration,
    save_match_result,
    save_series_result,
)
from police_thief.services.mcp_client import McpPeerTransport, PeerClientError
from police_thief.services.mcp_server import PeerInboxes
from police_thief.services.network_protocol import (
    WIRE_ROLES,
    AuditPayload,
    ControlMessage,
    NetworkProtocolError,
    TurnMessage,
    audit_records,
    create_agreement,
    now_iso,
    seal_payload,
    validate_claim_response,
    verify_agreement,
)
from police_thief.services.step0 import (
    Step0Declaration,
    TokenUsage,
    gather_hardware_spec,
    get_git_commit_hash,
    sign_step0,
)
from police_thief.services.submission_artifacts import (
    SubmissionBundleError,
    finalize_submission_bundle,
    public_participant,
    save_submission_validation_report,
    validate_submission_directory,
)
from police_thief.shared.constants import AgentRole
from police_thief.shared.game_config import config_fingerprint, load_match_parameters

EventSink = Callable[[str], None]


@dataclass(frozen=True)
class NetworkMatchSettings:
    role: AgentRole
    local_port: int
    opponent_url: str
    public_url: str
    game_id: str
    sub_game_number: int
    shared_config: Path
    output_dir: Path
    team_name: str = "TBD"
    members: tuple[str, ...] = ()
    opponent_team_name: str = "TBD"
    opponent_members: tuple[str, ...] = ()
    own_cop_repo: str = "TBD"
    own_thief_repo: str = "TBD"
    opponent_cop_repo: str = "TBD"
    opponent_thief_repo: str = "TBD"
    shared_key: bytes = b"course-match"
    email_mode: str = "dry_run"
    email_recipient: str = "rmisegal+uoh26finalgame@gmail.com"
    credentials_path: Path = Path("credentials.json")
    token_path: Path = Path("token.json")
    llm_model: str = "deterministic-heuristic"
    # Local orchestration metadata. It is intentionally excluded from the
    # signed public game terms and pre-game conformance manifest.
    series_id: str = ""
    game_index: int = 0
    counted: bool = True
    smoke_test: bool = False


class _WireScent:
    def __init__(self, values: dict[str, float]) -> None:
        self.values = values

    def intensity_at(self, position: Position) -> float:
        return float(self.values.get(f"{position.row},{position.col}", 0.0))


def _confirmed_cop_position(
    belief: BeliefMap,
    capture_claim: list[int] | None,
    *,
    occupied_blocked_position: Position | None = None,
) -> Position | None:
    """Return only a currently published cop cell, never stale certainty."""
    if capture_claim is None:
        return None
    position = Position(*capture_claim)
    # The cop may legally place a barrier on its own occupied cell.  The board
    # must remain blocked for movement, while the separately tracked exact
    # position still identifies the cop there; BeliefMap intentionally cannot
    # assign probability to a blocked cell.
    if position != occupied_blocked_position:
        belief.set_certain_position(position)
    return position


def _public_barrier_cop_candidates(
    board: Board, barrier_target: Position,
) -> tuple[Position, ...]:
    """Return every cop cell consistent with a public barrier declaration.

    A legal barrier is placed on the cop's own cell or an orthogonally
    adjacent cell.  The target may therefore itself be occupied even after it
    becomes blocked, so it is intentionally retained in this candidate set.
    """
    return tuple(dict.fromkeys((barrier_target, *board.neighbors(barrier_target))))


def _infer_public_scent_center(
    board: Board,
    previous_grid: dict[str, float],
    current_grid: dict[str, float],
    *,
    decay_rate: float,
    min_center_intensity: float,
    previous_position: Position | None = None,
) -> Position | None:
    """Infer a fresh emission center from two truthful public scent grids.

    The signed rule is ``new = (1-rho)*old + emission``.  Subtracting the
    retained trail prevents old high-intensity cells from being mistaken for
    the cop's current region.  The result remains an inference: malformed,
    capped, ambiguous, or physically impossible grids return ``None`` and the
    normal probabilistic belief path remains in control.
    """
    retained = 1.0 - decay_rate
    innovations: list[tuple[Position, float]] = []
    for row in range(board.config.grid_size):
        for col in range(board.config.grid_size):
            position = Position(row, col)
            key = f"{row},{col}"
            try:
                current = float(current_grid.get(key, 0.0))
                previous = float(previous_grid.get(key, 0.0))
            except (TypeError, ValueError):
                return None
            if not math.isfinite(current) or not math.isfinite(previous):
                return None
            innovations.append((position, current - retained * previous))

    ranked = sorted(innovations, key=lambda item: item[1], reverse=True)
    if not ranked:
        return None
    center, peak = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else float("-inf")
    rounding_tolerance = 2e-5
    minimum_gap = max(0.05, min_center_intensity * 0.10)
    if peak < min_center_intensity - rounding_tolerance:
        return None
    if peak - runner_up < minimum_gap:
        return None
    if (
        previous_position is not None
        and center not in set(board.legal_moves(previous_position).values())
    ):
        return None
    return center


def _infer_public_scent_candidates(
    board: Board,
    previous_grid: dict[str, float],
    current_grid: dict[str, float],
    *,
    decay_rate: float,
    min_center_intensity: float,
    emission_cap: float,
    previous_position: Position | None = None,
    max_ambiguity: int = 4,
) -> tuple[Position, ...]:
    """Cap-aware generalization of `_infer_public_scent_center`.

    Some opponents implement the signed scent rule with a hard intensity cap
    (``new = min(cap, (1-rho)*old + emission)``).  Once their agent lingers
    or backtracks, its whole neighborhood saturates at the cap and the
    fresh-emission innovation collapses below ``min_center_intensity``,
    blinding the singleton inference exactly during the hiding phases where
    pursuit evidence matters most (both reviewed live-match losses).  When no
    unique fresh center exists, this fallback returns the SMALL set of cells
    that (a) sit at the cap yet cannot be explained by pure retained trail
    -- staying at the cap requires a fresh deposit -- and (b) remain one
    legal step from the last inferred position.  Ambiguity wider than
    ``max_ambiguity`` cells returns () -- never fabricated certainty."""
    center = _infer_public_scent_center(
        board,
        previous_grid,
        current_grid,
        decay_rate=decay_rate,
        min_center_intensity=min_center_intensity,
        previous_position=previous_position,
    )
    if center is not None:
        return (center,)
    if previous_position is None:
        return ()
    retained = 1.0 - decay_rate
    tolerance = 2e-5
    reachable = sorted(
        set(board.legal_moves(previous_position).values()),
        key=lambda cell: (cell.row, cell.col),
    )
    candidates: list[Position] = []
    for position in reachable:
        key = f"{position.row},{position.col}"
        try:
            current = float(current_grid.get(key, 0.0))
            previous = float(previous_grid.get(key, 0.0))
        except (TypeError, ValueError):
            return ()
        if not math.isfinite(current) or not math.isfinite(previous):
            return ()
        innovation = current - retained * previous
        if current >= emission_cap - tolerance and innovation > tolerance:
            candidates.append(position)
    if not candidates or len(candidates) > max_ambiguity:
        return ()
    return tuple(candidates)


def _cornered_candidate_barrier(
    board: Board,
    own_position: Position,
    public_thief_candidates: tuple[Position, ...],
) -> Position | None:
    """Endgame closer: when the single fresh public thief candidate is
    adjacent to the cop AND already cornered (at most two open exits beyond
    the cop's own cell), wall that cell.  Either the thief is still on it (a
    capture claim, Sec. 3.3.4) or its hiding pocket just lost the doorway
    and the next approach boxes it in.  In an open-field chase the candidate
    has three or four exits, so this rule stays silent and can never wall
    off the cop's own pursuit path with a one-turn-stale scent center."""
    candidates = tuple(dict.fromkeys(public_thief_candidates))
    if len(candidates) != 1:
        return None
    target = candidates[0]
    open_neighbors = [
        neighbor
        for neighbor in board.neighbors(own_position)
        if not board.is_blocked(neighbor)
    ]
    # Never seal the cop's own last escape route (the reviewed G001 failure
    # that forced ten consecutive STAY turns).
    if target == own_position or target not in open_neighbors or len(open_neighbors) < 3:
        return None
    target_exits = [
        neighbor
        for neighbor in board.neighbors(target)
        if not board.is_blocked(neighbor) and neighbor != own_position
    ]
    if len(target_exits) > 2:
        return None
    return target


def _truthful_capture_claim(
    role: AgentRole,
    own_position: Position,
    plausible_opponent_positions: tuple[Position, ...],
) -> list[int] | None:
    """Challenge capture when public evidence includes the cop's occupied cell.

    A saturated scent can legitimately leave several current thief candidates.
    Requiring a singleton in that situation lets the cop move onto the real
    thief without issuing the claim that asks the thief to acknowledge capture.
    The claim remains evidence-based: the occupied cell must be one of the
    publicly plausible candidates, and the thief's signed response is still
    authoritative when the candidate set is ambiguous.
    """
    candidates = tuple(dict.fromkeys(plausible_opponent_positions))
    if (
        role is AgentRole.COP
        and own_position in candidates
    ):
        return [own_position.row, own_position.col]
    return None


_REVEALED_SELF_POSITION = re.compile(
    r"self\s*=\s*\[\s*(-?\d+)\s*,\s*(-?\d+)\s*\]", re.IGNORECASE,
)


@dataclass(frozen=True)
class _RevealedTrajectoryAudit:
    capture_step: int | None = None
    capture_after_role: str | None = None
    trailing_moves: int = 0
    errors: tuple[str, ...] = ()


def _revealed_coordinate(value: object) -> Position | None:
    """Read only public/revealed coordinate shapes used by compatible peers."""
    if isinstance(value, dict):
        row, col = value.get("row"), value.get("col")
        if all(isinstance(item, int) and not isinstance(item, bool) for item in (row, col)):
            return Position(row, col)
    if (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and all(isinstance(item, int) and not isinstance(item, bool) for item in value)
    ):
        return Position(value[0], value[1])
    if isinstance(value, str):
        match = _REVEALED_SELF_POSITION.search(value)
        if match:
            return Position(int(match.group(1)), int(match.group(2)))
    return None


def _revealed_move(value: object) -> Move | None:
    raw = str(value).strip().upper()
    for prefix in ("MOVE:", "MOVE=", "MOVE ", "ACTION:", "ACTION=", "ACTION "):
        if raw.startswith(prefix):
            raw = raw[len(prefix):].strip()
            break
    aliases = {
        "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W",
        "WAIT": "STAY", "NONE": "STAY",
    }
    try:
        return Move(aliases.get(raw, raw))
    except ValueError:
        return None


def _revealed_post_position(
    payload: dict, previous: Position, grid_size: int,
) -> tuple[Position | None, str | None]:
    """Normalize a signed move without assuming whether ``state`` is pre/post.

    Our records publish pre-move ``state`` plus post-move ``position``.  The
    reviewed reference-compatible peer publishes its post-move cell inside
    ``grid=...;self=[row,col]`` and uses ``MOVE:*`` actions.  Continuity from
    the protected start position distinguishes both formats safely.
    """
    move = _revealed_move(payload.get("move"))
    if move is None:
        return None, f"unsupported move {payload.get('move')!r}"
    delta = {
        Move.NORTH: (-1, 0), Move.SOUTH: (1, 0),
        Move.EAST: (0, 1), Move.WEST: (0, -1), Move.STAY: (0, 0),
    }[move]
    expected = Position(previous.row + delta[0], previous.col + delta[1])
    if not (0 <= expected.row < grid_size and 0 <= expected.col < grid_size):
        return None, f"move {move.value} from {previous} leaves the board"

    explicit = _revealed_coordinate(payload.get("position"))
    state = _revealed_coordinate(payload.get("state"))
    if explicit is not None:
        if explicit != expected:
            return None, f"position {explicit} does not match {move.value} from {previous}"
        if state is not None and state not in (previous, explicit):
            return None, f"state {state} is inconsistent with {previous}->{explicit}"
        return explicit, None
    if state == expected:
        return state, None
    if state == previous:
        return expected, None
    return None, f"state {payload.get('state')!r} does not continue from {previous}"


def _audit_revealed_trajectory(
    own_records: list[dict],
    peer_records: list[dict],
    own_role: str,
    peer_role: str,
    cop_start: Position,
    thief_start: Position,
    grid_size: int,
) -> _RevealedTrajectoryAudit:
    """Replay signed public records and find the first physical collision."""
    decorated: list[tuple[str, dict]] = []
    for source_role, records in ((own_role, own_records), (peer_role, peer_records)):
        for record in records:
            payload = record.get("payload") if isinstance(record, dict) else None
            if not isinstance(payload, dict) or "move" not in payload:
                continue
            decorated.append((source_role, payload))
    def sort_key(item: tuple[str, dict]) -> tuple[int, int]:
        try:
            step = int(item[1].get("step", -1))
        except (TypeError, ValueError):
            step = -1
        return step, 0 if item[0] == "thief" else 1

    decorated.sort(key=sort_key)

    positions = {"police": cop_start, "thief": thief_start}
    seen: set[tuple[str, int]] = set()
    errors: list[str] = []
    capture_step: int | None = None
    capture_after_role: str | None = None
    trailing_moves = 0
    for source_role, payload in decorated:
        role = "police" if source_role == "cop" else source_role
        try:
            step = int(payload.get("step"))
        except (TypeError, ValueError):
            errors.append(f"{role} record has invalid step {payload.get('step')!r}")
            continue
        declared_role = "police" if payload.get("role") == "cop" else payload.get("role")
        if role not in positions or declared_role not in (None, role):
            errors.append(
                f"step {step} source role {role!r} conflicts with payload role {declared_role!r}"
            )
            continue
        key = (role, step)
        if key in seen:
            errors.append(f"duplicate {role} move at step {step}")
            continue
        seen.add(key)
        position, error = _revealed_post_position(payload, positions[role], grid_size)
        if error is not None or position is None:
            errors.append(f"step {step} {role}: {error}")
            continue
        positions[role] = position
        if capture_step is not None:
            trailing_moves += 1
            continue
        if positions["police"] == positions["thief"]:
            capture_step = step
            capture_after_role = role

    return _RevealedTrajectoryAudit(
        capture_step, capture_after_role, trailing_moves, tuple(errors),
    )


_OPPOSITE_MOVE = {
    Move.NORTH: Move.SOUTH,
    Move.SOUTH: Move.NORTH,
    Move.EAST: Move.WEST,
    Move.WEST: Move.EAST,
    Move.STAY: Move.STAY,
}


class NetworkMatchRunner:
    def __init__(
        self, settings: NetworkMatchSettings, inboxes: PeerInboxes,
        gemini_advisor: GeminiAgentAdvisor | None = None,
        transport: McpPeerTransport | None = None,
    ) -> None:
        self.settings = settings
        self.gemini_advisor = gemini_advisor
        self.transport = transport or McpPeerTransport(
            settings.opponent_url, inboxes, sender=settings.role.value,
        )
        self._usage_start = self._gemini_usage_snapshot()

    def run(self, stop: Event, emit: EventSink = lambda _message: None) -> Path:
        s = self.settings
        own_identity = self._identity()
        params = load_match_parameters(s.shared_config)
        timeout = params.network_league.response_timeout_sec
        terms = self._terms(params)
        emit("Negotiating peer session")
        peer_agreement = self.transport.exchange_agreement(
            create_agreement(terms, own_identity), timeout,
        )
        peer_identity = verify_agreement(peer_agreement, terms)
        emit(f"Peer session established with {peer_identity.get('group_name', 'opponent')}")
        self._write_pregame_files(params)
        self._send_control("enable", "READY")

        own_records: list[dict] = [self._sealed_system_spec()]
        try:
            return self._play_turns_and_report(params, timeout, peer_identity, own_records, stop, emit)
        except PeerClientError as exc:
            # The opponent stopped responding mid-match (crashed, tunnel
            # dropped, etc.) -- resolve as a technical loss (Sec. 9.2, 0/0)
            # with whatever this side can prove on its own, rather than
            # crashing the whole process (and, inside a multi-game series,
            # every remaining sub-game) with an unhandled traceback.
            emit(f"Opponent unreachable mid-match -- resolving as technical loss: {exc}")
            self._send_control("quit", "STOPPED")
            return self._write_technical_loss_result(params, own_records, peer_identity, emit)

    def _play_turns_and_report(
        self, params, timeout: float, peer_identity: dict, own_records: list[dict],
        stop: Event, emit: EventSink,
    ) -> Path:
        board = Board(params.board)
        own_position = (
            params.cop_start if self.settings.role is AgentRole.COP else params.thief_start
        )
        own_scent = ScentField(params.board.grid_size, params.scent)
        belief = BeliefMap(board)
        belief.set_certain_position(
            params.thief_start
            if self.settings.role is AgentRole.COP
            else params.cop_start
        )
        brain = ManhattanHeuristicBrain(
            self.settings.role, strategy_seed=self.settings.sub_game_number
        )
        hint_provider = TemplateHintProvider(params.world.hint_max_words)
        peer_commits: dict[int, str] = {}
        pending_claim_response: dict | None = None
        outstanding_capture_claims: list[list[int]] = []
        outstanding_scent_claim: list[int] | None = None
        scent_capture_evidence_reliable = True
        missing_claim_response = False
        known_cop_position = (
            params.cop_start if self.settings.role is AgentRole.THIEF else None
        )
        public_cop_candidates: tuple[Position, ...] = ()
        public_thief_candidates: tuple[Position, ...] = ()
        previous_peer_scent: dict[str, float] = {}
        last_inferred_opponent_position = (
            params.cop_start
            if self.settings.role is AgentRole.THIEF
            else params.thief_start
        )
        thief_boxed_in = False
        outcome = MatchOutcome.SURVIVAL
        wire_role = WIRE_ROLES[self.settings.role.value]
        emit(f"Peer ready as {wire_role.upper()} - game {self.settings.game_id}")

        # Reference v3 numbers each peer's own turns 1..max_steps.  The thief
        # moves first, so a full survival game has 2*max_steps-1 wire turns.
        for global_turn in range(1, params.max_moves * 2):
            if stop.is_set():
                self._send_control("quit", "STOPPED")
                raise RuntimeError("network match cancelled")
            active_role = AgentRole.THIEF if global_turn % 2 == 1 else AgentRole.COP
            step = (global_turn + 1) // 2
            if active_role is self.settings.role:
                if (
                    self.settings.role is AgentRole.THIEF
                    and pending_claim_response
                    and pending_claim_response.get("caught")
                ):
                    # A capture is immediate. Acknowledge it with a sealed
                    # terminal record, but do not compute or execute a ghost move.
                    payload = {
                        "step": step,
                        "role": wire_role,
                        "state": {"row": own_position.row, "col": own_position.col},
                        "position": [own_position.row, own_position.col],
                        "terminal_ack": "capture",
                        "claim_response": pending_claim_response,
                    }
                    record = seal_payload(payload)
                    own_records.append(record)
                    message = TurnMessage(
                        step=step,
                        sender=wire_role,
                        hint="Capture acknowledged.",
                        smell_grid=self._scent_snapshot(
                            own_scent, params.board.grid_size
                        ),
                        commit=record["commit"],
                        timestamp=now_iso(),
                        claim_response=pending_claim_response,
                    )
                    self.transport.send_turn(message.to_dict(), timeout)
                    emit(f"Step {step}: capture acknowledged; no thief move executed")
                    outcome = MatchOutcome.CAPTURE
                    break
                self._send_control("status", "THINKING")
                fallback = brain._decide_move(
                    board,
                    own_position,
                    belief,
                    known_opponent_position=known_cop_position,
                    plausible_opponent_positions=(
                        public_cop_candidates
                        if self.settings.role is AgentRole.THIEF
                        else public_thief_candidates
                    ),
                )
                move, _private_reason = self._choose_move(
                    board, belief, own_position, fallback, step, params.max_moves, emit,
                    plan=brain.last_plan,
                    known_opponent_position=known_cop_position,
                    plausible_opponent_positions=(
                        public_cop_candidates
                        if self.settings.role is AgentRole.THIEF
                        else public_thief_candidates
                    ),
                )
                # Gemini's rationale is private reasoning and may mention local
                # truth.  Only a bounded direction claim crosses the wire.
                state_before = own_position
                public_hint = self._generate_public_hint(
                    hint_provider, board, state_before, move, step,
                )
                hint = public_hint.text
                own_position = board.apply_move(own_position, move)
                brain.record_move(state_before, move, own_position)
                if self.settings.role is AgentRole.THIEF:
                    # Barrier evidence describes the cop before its next turn.
                    # Do not carry that exact candidate set across another cop
                    # move; the fresh scent/public declaration will replace it.
                    public_cop_candidates = ()
                if (
                    self.settings.role is AgentRole.THIEF
                    and known_cop_position is not None
                    and own_position == known_cop_position
                ):
                    pending_claim_response = {
                        "claim": [known_cop_position.row, known_cop_position.col],
                        "caught": True,
                        "reason": "thief_entered_cop_cell",
                    }
                    emit(
                        f"Step {step}: thief entered the cop cell {known_cop_position}; "
                        "capture confirmed before the cop may move"
                    )
                own_scent.decay()
                own_scent.emit(own_position)
                barrier_placed = self._maybe_place_barrier(
                    board, own_position, belief, brain, emit, step,
                    public_thief_candidates=public_thief_candidates,
                )
                capture_claim = _truthful_capture_claim(
                    self.settings.role,
                    own_position,
                    (
                        public_thief_candidates
                        if scent_capture_evidence_reliable
                        else ()
                    ),
                )
                if capture_claim is not None:
                    emit(
                        f"Step {step}: cop occupies a publicly plausible thief cell "
                        f"{own_position}; requesting signed capture acknowledgement"
                    )
                win_claim = (
                    {"type": "boxed_in"} if self.settings.role is AgentRole.THIEF and thief_boxed_in
                    else {"type": "survival"}
                    if self.settings.role is AgentRole.THIEF and step >= params.max_moves
                    else None
                )
                payload = {
                    "step": step,
                    "role": wire_role,
                    "state": {"row": state_before.row, "col": state_before.col},
                    "position": [own_position.row, own_position.col],
                    "move": move.value,
                    "intent": public_hint.intent_truthful,
                    "hint": hint,
                }
                payload.update({
                    field: value
                    for field, value in {
                        "barrier_placed": barrier_placed,
                        "capture_claim": capture_claim,
                        "claim_response": pending_claim_response,
                        "win_claim": win_claim,
                    }.items()
                    if value is not None
                })
                record = seal_payload(payload)
                own_records.append(record)
                message = TurnMessage(
                    step=step, sender=wire_role, hint=hint,
                    smell_grid=self._scent_snapshot(own_scent, params.board.grid_size),
                    commit=record["commit"], timestamp=now_iso(),
                    capture_claim=capture_claim,
                    barrier_placed=barrier_placed,
                    claim_response=pending_claim_response,
                    win_claim=win_claim,
                )
                self.transport.send_turn(message.to_dict(), timeout)
                if self.settings.role is AgentRole.COP:
                    outstanding_capture_claims = [
                        list(claim) for claim in (capture_claim, barrier_placed)
                        if claim is not None
                    ]
                    outstanding_scent_claim = (
                        list(capture_claim) if capture_claim is not None else None
                    )
                    public_thief_candidates = ()
                elif pending_claim_response and not pending_claim_response.get("caught"):
                    # A negative acknowledgement answers one public claim only;
                    # do not repeat it on unrelated later turns.
                    pending_claim_response = None
                emit(f"Step {step}: sealed turn delivered; nonce remains private")
                if pending_claim_response and pending_claim_response.get("caught"):
                    outcome = MatchOutcome.CAPTURE
                    break
                if win_claim:
                    outcome = MatchOutcome.CAPTURE if win_claim.get("type") == "boxed_in" else MatchOutcome.SURVIVAL
                    break
            else:
                self._send_control("status", "WAITING")
                message = TurnMessage.from_dict(self.transport.receive_turn(timeout))
                expected_sender = WIRE_ROLES[active_role.value]
                if message.step != step or message.sender != expected_sender:
                    raise NetworkProtocolError(
                        "received an out-of-order or wrong-role turn: "
                        f"expected sender={expected_sender!r}, step={step}; "
                        f"received sender={message.sender!r}, step={message.step}"
                    )
                peer_commits[step] = message.commit
                inferred_candidates = _infer_public_scent_candidates(
                    board,
                    previous_peer_scent,
                    message.smell_grid,
                    decay_rate=params.scent.decay_rate,
                    min_center_intensity=params.scent.min_center_intensity,
                    emission_cap=params.scent.center_intensity,
                    previous_position=last_inferred_opponent_position,
                )
                inferred_scent_center = (
                    inferred_candidates[0] if len(inferred_candidates) == 1 else None
                )
                previous_peer_scent = dict(message.smell_grid)
                belief.update_from_scent(_WireScent(message.smell_grid))
                emit(f"Step {step}: received sealed {message.sender} turn")
                barrier_cop_candidates: tuple[Position, ...] = ()
                barrier_target: Position | None = None
                if message.barrier_placed is not None:
                    barrier_target = Position(*message.barrier_placed)
                    barrier_cop_candidates = _public_barrier_cop_candidates(
                        board, barrier_target,
                    )
                    board.apply_declared_barrier(barrier_target)
                    emit(f"Step {step}: opponent publicly declared a barrier at {barrier_target}")
                if self.settings.role is AgentRole.THIEF:
                    previous_known_cop_position = known_cop_position
                    known_cop_position = _confirmed_cop_position(
                        belief,
                        message.capture_claim,
                        occupied_blocked_position=barrier_target,
                    )
                    if known_cop_position is not None:
                        public_cop_candidates = ()
                        last_inferred_opponent_position = known_cop_position
                    elif inferred_scent_center is not None:
                        public_cop_candidates = (inferred_scent_center,)
                        last_inferred_opponent_position = inferred_scent_center
                        if (
                            barrier_cop_candidates
                            and inferred_scent_center not in barrier_cop_candidates
                        ):
                            # Two public channels disagree.  Do not fabricate
                            # certainty; protect against the union instead.
                            public_cop_candidates = tuple(dict.fromkeys(
                                (inferred_scent_center, *barrier_cop_candidates)
                            ))
                            # Do not validate the next transition from one side
                            # of disputed evidence.  The next fresh scent frame
                            # will be assessed without a false singleton anchor.
                            last_inferred_opponent_position = None
                        emit(
                            f"Step {step}: fresh public scent implies cop center "
                            f"({inferred_scent_center.row},{inferred_scent_center.col}); "
                            "using it as high-confidence escape evidence"
                        )
                    elif inferred_candidates:
                        # Saturated-scent ambiguity: the cop is one of a few
                        # capped cells near the last anchor.  Protect against
                        # the whole set and KEEP the anchor -- the cop is
                        # still within one legal step of it.
                        public_cop_candidates = tuple(dict.fromkeys(
                            (*inferred_candidates, *barrier_cop_candidates)
                        ))
                    else:
                        public_cop_candidates = barrier_cop_candidates
                        last_inferred_opponent_position = None
                    if public_cop_candidates:
                        rendered = ", ".join(
                            f"({position.row},{position.col})"
                            for position in public_cop_candidates
                        )
                        emit(
                            f"Step {step}: public evidence constrains the cop to "
                            f"one of [{rendered}]; applying this to escape safety"
                        )
                    if (
                        previous_known_cop_position is not None
                        and known_cop_position is None
                    ):
                        emit(
                            f"Step {step}: cop position was not published; discarded stale "
                            "certainty and switched to the public scent belief"
                        )
                    claims = [
                        list(claim) for claim in (message.capture_claim, message.barrier_placed)
                        if claim is not None
                    ]
                    if claims:
                        own_cell = [own_position.row, own_position.col]
                        caught = own_cell in claims
                        reported_claim = own_cell if caught else claims[0]
                        pending_claim_response = {"claim": reported_claim, "caught": caught}
                    if is_boxed_in(board, own_position):
                        thief_boxed_in = True
                        emit(f"Step {step}: no legal move remains -- boxed in (Sec. 3.3.5)")
                elif self.settings.role is AgentRole.COP:
                    if inferred_scent_center is not None:
                        public_thief_candidates = (inferred_scent_center,)
                        last_inferred_opponent_position = inferred_scent_center
                        emit(
                            f"Step {step}: fresh public scent implies thief center "
                            f"({inferred_scent_center.row},{inferred_scent_center.col}); "
                            "using it for pursuit and truthful capture detection"
                        )
                    elif inferred_candidates:
                        # Saturated-scent ambiguity: the thief lingers inside
                        # a capped blob near the last anchor.  Pursue the
                        # small candidate set and KEEP the anchor -- the
                        # thief is still within one legal step of it.
                        public_thief_candidates = inferred_candidates
                        rendered = ", ".join(
                            f"({position.row},{position.col})"
                            for position in inferred_candidates
                        )
                        emit(
                            f"Step {step}: saturated public scent constrains the "
                            f"thief to one of [{rendered}]; pursuing the set"
                        )
                    else:
                        public_thief_candidates = ()
                        last_inferred_opponent_position = None
                if self.settings.role is AgentRole.COP and outstanding_capture_claims:
                    if message.claim_response is None:
                        missing_claim_response = True
                        scent_capture_evidence_reliable = False
                        emit(
                            f"Step {step}: opponent omitted the required response to "
                            f"capture claim(s) {outstanding_capture_claims}; disabling "
                            "scent-derived capture claims for this sub-game"
                        )
                    else:
                        validate_claim_response(
                            message.claim_response, outstanding_capture_claims,
                        )
                        if (
                            outstanding_scent_claim is not None
                            and message.claim_response.get("claim") == outstanding_scent_claim
                            and not message.claim_response.get("caught")
                        ):
                            scent_capture_evidence_reliable = False
                            emit(
                                f"Step {step}: opponent rejected scent-derived capture "
                                f"claim {outstanding_scent_claim}; treating scent as pursuit "
                                "evidence only for the rest of this sub-game"
                            )
                        if message.claim_response.get("caught"):
                            outcome = MatchOutcome.CAPTURE
                            break
                    outstanding_capture_claims = []
                    outstanding_scent_claim = None
                elif self.settings.role is AgentRole.COP and message.claim_response:
                    raise NetworkProtocolError(
                        "opponent sent an unsolicited capture response"
                    )
                if message.win_claim:
                    claim_type = message.win_claim.get("type")
                    outcome = MatchOutcome.CAPTURE if claim_type == "boxed_in" else MatchOutcome.SURVIVAL
                    break

        emit("Exchanging final audit records and nonce reveals")
        own_usage = self._token_usage()
        usage_payload = {
            "input_tokens": own_usage.input_tokens,
            "output_tokens": own_usage.output_tokens,
            "total": own_usage.total,
        }
        peer_audit = AuditPayload.from_dict(self.transport.exchange_audit(
            AuditPayload(wire_role, own_records, outcome.value, usage_payload).to_dict(), timeout,
        ))
        audit_ok, failed = audit_records(
            peer_audit.records,
            peer_commits,
            require_step0=True,
        )
        if not audit_ok:
            emit(
                f"Opponent audit rejected at steps {failed}; recording technical loss "
                "with mutual_sign_off=false"
            )
            self._send_control("status", "AUDIT_FAILED")
            return self._write_technical_loss_result(
                params, own_records, peer_identity, emit,
            )
        entries = self._combined_log(
            own_records, peer_audit.records, wire_role, peer_audit.sender,
        )
        trajectory = _audit_revealed_trajectory(
            own_records,
            peer_audit.records,
            wire_role,
            peer_audit.sender,
            params.cop_start,
            params.thief_start,
            params.board.grid_size,
        )
        semantic_audit_clean = not trajectory.errors
        if trajectory.errors:
            rendered = "; ".join(trajectory.errors[:5])
            emit(
                "Revealed trajectory contains semantic validation errors; "
                f"mutual sign-off disabled: {rendered}"
            )
        if trajectory.capture_step is not None:
            if outcome is not MatchOutcome.CAPTURE:
                emit(
                    f"Final audit corrected the outcome to capture: signed positions "
                    f"first coincide at step {trajectory.capture_step} after the "
                    f"{trajectory.capture_after_role} move"
                )
            outcome = MatchOutcome.CAPTURE
            if trajectory.trailing_moves:
                semantic_audit_clean = False
                emit(
                    f"Final audit found {trajectory.trailing_moves} move(s) after the "
                    f"terminal collision at step {trajectory.capture_step}; retaining "
                    "the signed log but disabling mutual sign-off"
                )

        peer_claim_matches = peer_audit.result_claim == outcome.value
        if not peer_claim_matches and trajectory.capture_step is None:
            emit(
                "Opponent result claim does not match local result; recording "
                "technical loss with mutual_sign_off=false"
            )
            self._send_control("status", "AUDIT_FAILED")
            return self._write_technical_loss_result(
                params, own_records, peer_identity, emit,
            )
        if not peer_claim_matches:
            emit(
                f"Opponent claimed {peer_audit.result_claim!r}, but the signed revealed "
                f"trajectory proves {outcome.value!r}; saving the evidence-derived "
                "result without mutual sign-off"
            )
        mutual_sign_off = bool(re.fullmatch(
            r"[0-9a-f]{40}", str(peer_identity.get("git_commit_hash", "")),
        )) and peer_claim_matches and semantic_audit_clean and not missing_claim_response
        if not mutual_sign_off:
            emit(
                "Audit was not fully mutually verifiable (identity, result claim, "
                "trajectory, or capture response); result retained with "
                "mutual_sign_off=false"
            )
        path = self._write_result(
            params, entries, outcome, peer_identity, peer_audit.token_usage, emit,
            mutual_sign_off=mutual_sign_off,
        )
        self._send_control("status", "COMPLETE")
        if self.settings.email_mode == "real":
            _try_email_result(path, params, self.settings, emit)
        elif self.settings.email_mode == "dry_run":
            emit("Email mode is dry_run; JSON created but not sent")
        return path

    def _choose_move(
        self, board, belief, own, fallback, step, max_steps, emit, plan=None,
        known_opponent_position=None,
        plausible_opponent_positions=(),
    ):
        legal_now = board.legal_moves(own)
        safe_now = dict(legal_now)
        threat_positions = (
            (known_opponent_position,)
            if known_opponent_position is not None
            else tuple(dict.fromkeys(plausible_opponent_positions))
        )
        if self.settings.role is AgentRole.THIEF and threat_positions:
            cop_reachable_next = {
                destination
                for position in threat_positions
                for destination in cop_capture_cells(board, position)
            }
            guaranteed_safe = {
                move: destination
                for move, destination in legal_now.items()
                if destination not in cop_reachable_next
            }
            if guaranteed_safe:
                safe_now = guaranteed_safe
                for move, destination in legal_now.items():
                    if move in safe_now:
                        continue
                    emit(
                        f"Step {step}: rejected {move.name} ({move.value}); destination "
                        f"{destination} is capturable on the cop's next turn "
                        "(move or barrier)"
                    )
            else:
                # If every option is threatened, still forbid walking onto a
                # currently plausible cop cell: that loses immediately before
                # the cop even takes its turn.
                for move, destination in tuple(safe_now.items()):
                    if destination in threat_positions and len(safe_now) > 1:
                        safe_now.pop(move)
                        evidence = (
                            "the cop's confirmed current cell"
                            if known_opponent_position is not None
                            else "a publicly plausible current cop cell"
                        )
                        emit(
                            f"Step {step}: rejected {move.name} ({move.value}); destination "
                            f"{destination} is {evidence}"
                        )
        if plan is not None:
            for item in plan.evaluations:
                emit(f"Step {step}: candidate {item.move.name} ({item.move.value}) - {item.summary()}")
            if plan.loop_detected:
                excluded = ", ".join(move.name for move in plan.excluded_moves) or "none"
                emit(
                    f"Step {step}: repeated loop detected ({plan.loop_reason}); "
                    f"forcing reconsideration; excluded={excluded}"
                )
            allowed = tuple(move for move in plan.allowed_moves if move in safe_now)
            if not allowed:
                allowed = tuple(
                    item.move for item in plan.evaluations if item.move in safe_now
                )
        else:
            allowed = tuple(safe_now)
        if not allowed:
            allowed = tuple(safe_now) or tuple(legal_now)
        if fallback not in allowed:
            ranked_allowed = (
                tuple(
                    item.move
                    for item in plan.evaluations
                    if item.move in allowed
                )
                if plan is not None
                else ()
            )
            fallback = ranked_allowed[0] if ranked_allowed else allowed[0]
        if self.gemini_advisor is None:
            emit(f"Step {step}: planner selected {fallback.name} ({fallback.value}); valid=True")
            return fallback, "Deterministic local-truth move"
        started_at = time.monotonic()
        size = board.config.grid_size
        blocked = tuple(
            Position(row, col)
            for row in range(size)
            for col in range(size)
            if board.is_blocked(Position(row, col))
        )
        evaluations = {item.move: item.summary() for item in plan.evaluations} if plan else {}
        decision = self.gemini_advisor.choose_move(
            TacticalContext(
                role=self.settings.role, own_position=own, belief_peak=belief.arg_max(),
                legal_moves=allowed,
                legal_destinations=tuple((move, legal_now[move]) for move in allowed),
                action_scores=tuple((move, evaluations.get(move, "not scored")) for move in allowed),
                board_size=size,
                blocked_cells=blocked,
                belief_candidates=(
                    tuple(
                        (position, 1.0 / len(threat_positions))
                        for position in threat_positions
                    )
                    if known_opponent_position is None and threat_positions
                    else belief.top_positions(5)
                ),
                recent_positions=plan.recent_positions if plan else (),
                recent_actions=plan.recent_actions if plan else (),
                repeated_state_warning=plan.loop_reason if plan and plan.loop_detected else "",
                known_opponent_position=known_opponent_position,
                sub_game_number=self.settings.sub_game_number,
                turn_number=step,
                max_turns=max_steps, remaining_barriers=board.remaining_barrier_budget,
            ),
            fallback,
        )
        elapsed = time.monotonic() - started_at
        legal_now = board.legal_moves(own)
        unsafe_destination = (
            self.settings.role is AgentRole.THIEF
            and known_opponent_position is not None
            and decision.move in legal_now
            and legal_now[decision.move] == known_opponent_position
        )
        if decision.move not in legal_now or decision.move not in allowed or unsafe_destination:
            reason = (
                "would enter the cop's confirmed current cell"
                if unsafe_destination
                else "not legal now"
                if decision.move not in legal_now
                else "excluded by tactical safety or loop prevention"
            )
            emit(f"Step {step}: rejected Gemini action {decision.move!r}: {reason}")
            emit(f"Step {step}: fallback activated; selected {fallback.name} ({fallback.value})")
            return fallback, reason
        for rejection in decision.rejected:
            emit(f"Step {step}: Gemini response rejected - {rejection}")
        if decision.used_fallback:
            emit(f"Step {step}: fallback activated after {decision.attempts} Gemini attempt(s)")
            emit(f"Step {step}: fallback selected {decision.move.name} ({decision.move.value})")
        else:
            emit(f"Step {step}: Gemini selected {decision.move.name} ({decision.move.value}); valid=True; attempts={decision.attempts}")
        source = "fallback" if decision.used_fallback else "Gemini"
        emit(f"Step {step}: {source} ({elapsed:.1f}s) - {decision.rationale}")
        return decision.move, decision.rationale

    def _generate_public_hint(
        self, provider, board, before, true_move, step,
    ):
        """Generate a legal verbal bluff for the thief, never a fake scent.

        Hints are the one rule-authorized deceptive channel.  Prefer claiming
        the opposite move when that claim is plausible from the public origin;
        otherwise rotate through other legal claims across games/turns.  The
        cop remains truthful because pursuit gains nothing from advertising a
        fabricated route here.
        """
        if self.settings.role is not AgentRole.THIEF:
            return provider.generate(true_move, tell_truth=True)
        # Mix truth into the policy so an opponent cannot simply invert every
        # audited hint in the next game.  Randomness affects language only,
        # never the deterministic movement or legal-action validation.
        if secrets.randbelow(4) == 0:
            return provider.generate(true_move, tell_truth=True)
        alternatives = tuple(
            move for move in board.legal_moves(before)
            if move is not true_move
        )
        if not alternatives:
            return provider.generate(true_move, tell_truth=True)
        preferred = tuple(
            move
            for move in alternatives
            if move is _OPPOSITE_MOVE[true_move] and move is not Move.STAY
        )
        # Include the opposite twice to make it a useful default without
        # becoming a deterministic, invertible signal.
        bluff_pool = preferred + alternatives
        false_move = bluff_pool[secrets.randbelow(len(bluff_pool))]
        return provider.generate(
            true_move, tell_truth=False, false_move=false_move,
        )

    def _gemini_usage_snapshot(self) -> tuple[int, int]:
        if self.gemini_advisor is None or not hasattr(
            self.gemini_advisor, "usage_snapshot"
        ):
            return 0, 0
        return self.gemini_advisor.usage_snapshot()

    def _token_usage(self) -> TokenUsage:
        current_input, current_output = self._gemini_usage_snapshot()
        start_input, start_output = self._usage_start
        return TokenUsage(
            input_tokens=max(0, current_input - start_input),
            output_tokens=max(0, current_output - start_output),
        )

    def _maybe_place_barrier(
        self, board, own_position, belief, brain, emit, step,
        public_thief_candidates: tuple[Position, ...] = (),
    ) -> list[int] | None:
        """Cop-only: the "core spatial-engineering advantage" (Sec. 3.3.3).

        Runs after the cop's move above, not instead of it -- Sec. 3.3.3
        lists "its own current cell" as a legal barrier target, which only
        makes sense as the cell the cop just moved to. Reuses
        `ManhattanHeuristicBrain._pick_move` (Chapter 6), the same barrier-
        selection heuristic already shipped and tested; deliberately kept
        deterministic rather than Gemini-advised for this pass (see
        docs/PRD_strategy_module.md for the rationale on scoping LLM
        involvement to the verbal layer only, Sec. 6.4.1).

        Declared in plaintext on the wire (Sec. 3.3.6: barrier placements
        are public in real time, never sealed inside the commit like a
        move), so the opponent's board stays in sync without waiting for
        the end-of-match reveal.
        """
        if self.settings.role is not AgentRole.COP or board.remaining_barrier_budget <= 0:
            return None
        target = _cornered_candidate_barrier(board, own_position, public_thief_candidates)
        if target is None:
            target = brain._pick_move(board, own_position, belief)
        if target is None or board.remaining_barrier_budget <= 0:
            return None
        board.place_barrier(own_position, target)
        emit(f"Step {step}: placed a barrier at {target} (publicly declared per Sec. 3.3.6)")
        return [target.row, target.col]


    def _send_control(self, kind: str, status: str) -> None:
        self.transport.send_control(ControlMessage(
            kind=kind, sender=WIRE_ROLES[self.settings.role.value],
            sub_game_number=self.settings.sub_game_number, status=status,
        ).to_dict())

    def _terms(self, params) -> dict:
        return {
            "board_size": params.board.grid_size,
            "smell_grid_size": params.scent.field_size,
            "decay_per_step": params.scent.decay_rate,
            "emit_intensity": params.scent.center_intensity,
            "min_center_intensity": params.scent.min_center_intensity,
            "max_steps": params.max_moves,
            "barriers_max": params.board.max_barriers,
            "setting": params.world.map_area,
            "hint_max_words": params.world.hint_max_words,
            "axis_origin_corner": params.board.axis_origin_corner,
            "axis_start_index": params.board.axis_start_index,
            "thief_start": [params.thief_start.row, params.thief_start.col],
            "cop_start": [params.cop_start.row, params.cop_start.col],
            "num_games": params.network_league.num_games,
        }

    def _identity(self) -> dict:
        s = self.settings
        hardware = gather_hardware_spec(s.llm_model)
        return {
            "group_id": s.team_name.lower().replace(" ", "-"),
            "group_name": s.team_name,
            "members": list(s.members),
            "repos": {"cop": s.own_cop_repo, "thief": s.own_thief_repo},
            "mcp_servers": {s.role.value: s.public_url},
            "llm_model": s.llm_model,
            # Exact public hardware keys consumed by the reference report
            # builder after a successful match.
            "spec": {
                "os": hardware.os_name,
                "cpu_type": platform.processor() or "unknown",
                "cpu_cores": hardware.cpu_count,
                "cpu_freq_mhz": "unknown",
                "ram_gb": hardware.ram_gb,
                "gpu_type": "present" if hardware.gpu_present else "unknown",
                "gpu_cores_or_cuda": "unknown",
                "vram_gb": "unknown",
            },
            "protocol": {"name": "police-thief-mcp", "version": "3.0.0"},
            "git_commit_hash": get_git_commit_hash(str(s.shared_config.parent.parent)),
        }

    def _validate_peer_identity(self, identity: dict) -> None:
        """Bind the negotiated peer to the opponent declared before play."""
        s = self.settings
        expected = {
            "group_name": s.opponent_team_name,
            "members": list(s.opponent_members),
            "repos": {"cop": s.opponent_cop_repo, "thief": s.opponent_thief_repo},
        }
        for field, value in expected.items():
            configured = value not in ("", "TBD", [], {"cop": "TBD", "thief": "TBD"})
            received = identity.get(field)
            matches = (
                isinstance(value, str)
                and isinstance(received, str)
                and value.casefold() == received.casefold()
                if field == "group_name"
                else received == value
            )
            if configured and not matches:
                raise NetworkProtocolError(
                    f"opponent identity mismatch for {field}: configured {value!r}, "
                    f"negotiated {received!r}"
                )

    def _sealed_system_spec(self) -> dict:
        """Build the lecturer-reference step-0 record revealed at final audit."""
        payload = {
            "step": 0,
            "type": "system_spec",
            "spec": asdict(gather_hardware_spec(self.settings.llm_model)),
            "model": self.settings.llm_model,
            "code_version": "3.0.0",
            "group_name": self.settings.team_name,
            "sub_game_number": self.settings.sub_game_number,
            "git_commit_hash": get_git_commit_hash(
                str(self.settings.shared_config.parent.parent)
            ),
        }
        return seal_payload(payload)

    @staticmethod
    def _scent_snapshot(scent: ScentField, size: int) -> dict[str, float]:
        return {
            f"{row},{col}": round(scent.intensity_at(Position(row, col)), 6)
            for row in range(size) for col in range(size)
            if scent.intensity_at(Position(row, col)) > 0
        }

    @staticmethod
    def _combined_log(
        own_records: list[dict], peer_records: list[dict], own_role: str, peer_role: str,
    ) -> list[LogEntry]:
        # Step numbers are local to each peer.  Decorate records with their
        # source role so both computers produce the same thief-then-police
        # ordering and therefore the same replay-log hash.
        decorated = [
            (own_role, record)
            for record in own_records
            if record["payload"]["step"] > 0 and "move" in record["payload"]
        ] + [
            (peer_role, record)
            for record in peer_records
            if record["payload"]["step"] > 0 and "move" in record["payload"]
        ]
        records = sorted(
            decorated,
            key=lambda item: (
                item[1]["payload"]["step"], 0 if item[0] == "thief" else 1,
            ),
        )
        return [
            LogEntry(
                state=record["payload"]["state"], move=record["payload"]["move"],
                intent=record["payload"]["intent"], nonce=record["nonce"],
                h_commit=record["commit"], payload=record["payload"],
            )
            for _role, record in records
        ]

    def _write_pregame_files(self, params) -> None:
        s = self.settings
        fingerprint = config_fingerprint(s.shared_config)
        step0 = Step0Declaration(
            hardware=gather_hardware_spec(s.llm_model), code_version="3.00",
            team_name=s.team_name, game_id=s.game_id, sub_game_number=s.sub_game_number,
            git_commit_hash=get_git_commit_hash(str(s.shared_config.parent.parent)),
            config_fingerprint=fingerprint,
        )
        team = TeamInfo(s.team_name, s.members, s.own_cop_repo, s.own_thief_repo)
        save_declaration(build_declaration(
            s.game_id, s.sub_game_number, team, sign_step0(step0, s.shared_key),
            params.network_league.token_budget_per_series,
        ), s.output_dir)
        raw_config = json.loads(s.shared_config.read_text(encoding="utf-8"))
        save_config_snapshot(build_config_snapshot(
            s.game_id, s.sub_game_number, raw_config, fingerprint,
        ), s.output_dir)

    def _write_result(
        self, params, entries, outcome, peer_identity: dict,
        peer_token_usage: dict | None, emit: EventSink,
        *, mutual_sign_off: bool = True,
    ) -> Path:
        s = self.settings
        save_log(entries, s.output_dir / f"log_{s.game_id}_g{s.sub_game_number:02d}.json")
        cop_score, thief_score = score_for(outcome, params.scoring)
        own_identity = self._identity()
        teams = sorted(
            (own_identity, peer_identity),
            key=lambda identity: str(
                identity.get("group_id") or identity.get("group_name") or ""
            ).casefold(),
        )
        team_a, team_b = teams
        repos_a = team_a.get("repos", {})
        repos_b = team_b.get("repos", {})
        own_usage = self._token_usage()
        participants = {
            str(identity["group_id"]): public_participant(identity)
            for identity in (own_identity, peer_identity)
        }
        token_usage_by_group = {
            str(own_identity["group_id"]): own_usage.total,
            str(peer_identity["group_id"]): int((peer_token_usage or {}).get("total", 0)),
        }
        result = build_match_result(
            s.game_id, s.sub_game_number, cop_score, thief_score, outcome.value,
            mutual_sign_off,
            entries, self._token_usage(), RepoCrossLinks(
                str(repos_a.get("cop", "")), str(repos_a.get("thief", "")),
                str(repos_b.get("cop", "")), str(repos_b.get("thief", "")),
            ),
            ResultTeamIdentity(
                str(team_a.get("group_name", "")), tuple(team_a.get("members", ())),
            ),
            ResultTeamIdentity(
                str(team_b.get("group_name", "")), tuple(team_b.get("members", ())),
            ),
            participants,
            token_usage_by_group,
        )
        path = save_match_result(
            result, s.output_dir,
            include_sub_game=params.network_league.num_games > 1,
        )
        status = "verified" if mutual_sign_off else "not mutually signed"
        emit(f"Audit {status}; result saved to {path}")
        return path

    def _write_technical_loss_result(
        self, params, own_records: list[dict], peer_identity: dict, emit: EventSink,
    ) -> Path:
        """Best-effort result when the opponent stops responding mid-match
        (Sec. 9.2's technical-loss score, 0/0): records what this side can
        prove on its own. `mutual_sign_off` is False -- the opponent never
        confirmed anything past whatever it acknowledged before going dark,
        so this is honestly not the same as a normal, cross-verified result.
        """
        s = self.settings
        entries = [
            LogEntry(
                state=record["payload"]["state"], move=record["payload"]["move"],
                intent=record["payload"]["intent"], nonce=record["nonce"],
                h_commit=record["commit"], payload=record["payload"],
            )
            for record in own_records
            if record["payload"].get("step", 0) > 0
            and "move" in record["payload"]
        ]
        save_log(entries, s.output_dir / f"log_{s.game_id}_g{s.sub_game_number:02d}.json")
        cop_score, thief_score = score_for(MatchOutcome.TECHNICAL_LOSS, params.scoring)
        own_identity = self._identity()
        teams = sorted(
            (own_identity, peer_identity),
            key=lambda identity: str(
                identity.get("group_id") or identity.get("group_name") or ""
            ).casefold(),
        )
        team_a, team_b = teams
        repos_a = team_a.get("repos", {})
        repos_b = team_b.get("repos", {})
        own_usage = self._token_usage()
        participants = {
            str(identity["group_id"]): public_participant(identity)
            for identity in (own_identity, peer_identity)
        }
        token_usage_by_group = {
            str(own_identity["group_id"]): own_usage.total,
            str(peer_identity["group_id"]): 0,
        }
        result = build_match_result(
            s.game_id, s.sub_game_number, cop_score, thief_score,
            MatchOutcome.TECHNICAL_LOSS.value, False,
            entries, self._token_usage(), RepoCrossLinks(
                str(repos_a.get("cop", "")), str(repos_a.get("thief", "")),
                str(repos_b.get("cop", "")), str(repos_b.get("thief", "")),
            ),
            ResultTeamIdentity(
                str(team_a.get("group_name", "")), tuple(team_a.get("members", ())),
            ),
            ResultTeamIdentity(
                str(team_b.get("group_name", "")), tuple(team_b.get("members", ())),
            ),
            participants,
            token_usage_by_group,
        )
        path = save_match_result(
            result, s.output_dir,
            include_sub_game=params.network_league.num_games > 1,
        )
        emit(f"Technical loss recorded (opponent unreachable); result saved to {path}")
        return path


def role_for_subgame(natural_role: AgentRole, series_index: int) -> AgentRole:
    """Alternate roles while each repository keeps its natural first-game role."""
    if series_index < 0:
        raise ValueError("series_index must be non-negative")
    if series_index % 2 == 0:
        return natural_role
    return AgentRole.THIEF if natural_role is AgentRole.COP else AgentRole.COP


class NetworkMatchSeriesRunner:
    """Run an agreed multi-game series over one long-lived MCP connection."""

    def __init__(
        self, settings: NetworkMatchSettings, inboxes: PeerInboxes,
        gemini_advisor: GeminiAgentAdvisor | None = None,
        transport: McpPeerTransport | None = None,
    ) -> None:
        self.settings = settings
        self.inboxes = inboxes
        self.gemini_advisor = gemini_advisor
        self.transport = transport or McpPeerTransport(settings.opponent_url, inboxes)

    def run(self, stop: Event, emit: EventSink = lambda _message: None) -> Path:
        params = load_match_parameters(self.settings.shared_config)
        num_games = params.network_league.num_games
        subgames: list[dict] = []
        totals: dict[str, int] = {}
        participants: dict[str, dict] | None = None
        series_started_at = datetime.now().astimezone().isoformat()
        for series_index in range(num_games):
            sub_game_number = self.settings.sub_game_number + series_index
            role = role_for_subgame(self.settings.role, series_index)
            emit(
                f"Starting sub-game {series_index + 1}/{num_games} as "
                f"{WIRE_ROLES[role.value].upper()}"
            )
            child_settings = replace(
                self.settings,
                role=role,
                sub_game_number=sub_game_number,
                email_mode="series_deferred",
            )
            subgame_started_at = datetime.now().astimezone().isoformat()
            path = NetworkMatchRunner(
                child_settings, self.inboxes, self.gemini_advisor, self.transport,
            ).run(stop, emit)
            subgame_ended_at = datetime.now().astimezone().isoformat()
            result = json.loads(path.read_text(encoding="utf-8"))
            if participants is None:
                participants = result["participants"]
                totals = dict.fromkeys(participants, 0)
            own_group = next(
                key for key, value in participants.items()
                if value["group_name"] == self.settings.team_name
            )
            peer_group = next(key for key in participants if key != own_group)
            own_score_key = "cop_score" if role is AgentRole.COP else "thief_score"
            peer_score_key = "thief_score" if role is AgentRole.COP else "cop_score"
            score = {
                own_group: int(result[own_score_key]),
                peer_group: int(result[peer_score_key]),
            }
            totals[own_group] += score[own_group]
            totals[peer_group] += score[peer_group]
            subgames.append({
                "sub_game_number": sub_game_number,
                "roles": {
                    own_group: role.value,
                    peer_group: (
                        AgentRole.THIEF.value if role is AgentRole.COP else AgentRole.COP.value
                    ),
                },
                "started_at": subgame_started_at,
                "ended_at": subgame_ended_at,
                "outcome": result["outcome"],
                "score": score,
                "tokens": result["token_usage_by_group"],
                "mutual_sign_off": result["mutual_sign_off"],
                "cop_score": result["cop_score"],
                "thief_score": result["thief_score"],
                "log_sha256": result["log_sha256"],
                "result_file": path.name,
            })
            emit(f"Sub-game {series_index + 1}/{num_games} verified")

        # Tie Rule (Sec. 9.2.8-9.2.9 / Appendix F Table 17 row 5): a tied
        # cumulative series total credits each side the tie score on top of
        # its raw subtotal, so the emailed aggregate carries e.g. 77-77.
        group_a, group_b = totals
        totals[group_a], totals[group_b] = apply_tie_rule(
            totals[group_a], totals[group_b], params.scoring.tie_score,
        )
        ordered_totals = dict(sorted(totals.items(), key=lambda item: item[0].casefold()))
        highest = max(ordered_totals.values())
        winners = [team for team, score in ordered_totals.items() if score == highest]
        series_result = {
            "schema_version": "1.00",
            "game_id": self.settings.game_id,
            "num_games": num_games,
            "first_sub_game_number": self.settings.sub_game_number,
            "mutual_sign_off": all(
                bool(row["mutual_sign_off"]) for row in subgames
            ),
            "sub_games": subgames,
            "team_scores": ordered_totals,
            "winner": winners[0] if len(winners) == 1 else "tie",
        }
        path = save_series_result(series_result, self.settings.output_dir, self.settings.game_id)
        if participants is None:
            raise RuntimeError("series completed without participant metadata")
        terms = NetworkMatchRunner(
            self.settings, self.inboxes, self.gemini_advisor, self.transport,
        )._terms(params)
        try:
            submission_paths = finalize_submission_bundle(
                self.settings.output_dir,
                game_id=self.settings.game_id,
                terms=terms,
                participants=participants,
                series_result=series_result,
                game_started_at=series_started_at,
                token_budget=params.network_league.token_budget_per_series,
            )
        except SubmissionBundleError as exc:
            errors, _ = validate_submission_directory(
                self.settings.output_dir, self.settings.game_id,
            )
            report = save_submission_validation_report(
                self.settings.output_dir,
                self.settings.game_id,
                errors,
                str(exc),
            )
            path = self.settings.output_dir / f"result_{self.settings.game_id}.json"
            emit(
                "WARNING: submission has "
                f"{len(errors)} validation error(s); report saved to {report}"
            )
            _deliver_unverified_result(
                path, params, self.settings, emit,
            )
            return path
        path = self.settings.output_dir / f"result_{self.settings.game_id}.json"
        emit(
            f"Series complete; {len(submission_paths)} validated submission JSON files "
            f"ready in {self.settings.output_dir}"
        )
        if self.settings.email_mode == "real":
            _try_email_result(path, params, self.settings, emit)
        else:
            emit("Email mode is dry_run; aggregate JSON created but not sent")
        return path


def _try_email_result(path: Path, params, settings: NetworkMatchSettings, emit: EventSink) -> None:
    """Email delivery is best-effort: by the time this runs, the match is
    already audited and the result already saved -- a missing dependency,
    missing OAuth setup, or a transient Gmail failure must not crash an
    already-successful, already-recorded match."""
    from police_thief.services.network_reporting import email_result_file

    try:
        email_result_file(path, params, settings, emit)
    except RuntimeError as exc:
        emit(f"Email delivery failed (result already saved to {path}): {exc}")


def _deliver_unverified_result(
    result_path: Path, params, settings: NetworkMatchSettings,
    emit: EventSink,
) -> bool:
    """Deliver only the aggregate result without claiming it is verified."""
    if not result_path.is_file():
        emit(
            "Submission email could not be created because the aggregate result "
            f"is missing: {result_path.name}"
        )
        return False
    if settings.email_mode != "real":
        emit(
            "Email mode is dry_run; unverified aggregate result was created but not sent"
        )
        return False
    emit(
        "Sending only the aggregate result JSON despite validation warnings; "
        "supporting artifacts remain local and no values were fabricated or confirmed"
    )
    _try_email_result(result_path, params, settings, emit)
    return True
