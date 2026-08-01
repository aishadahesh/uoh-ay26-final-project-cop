"""Independent local-truth peer runtime over the four-tool MCP protocol."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from police_thief.domain.belief import BeliefMap
from police_thief.domain.board import Board, Position
from police_thief.domain.capture import is_boxed_in
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
)
from police_thief.services.mcp_client import McpPeerTransport
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
    verify_agreement,
)
from police_thief.services.step0 import (
    Step0Declaration,
    TokenUsage,
    gather_hardware_spec,
    get_git_commit_hash,
    sign_step0,
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


class _WireScent:
    def __init__(self, values: dict[str, float]) -> None:
        self.values = values

    def intensity_at(self, position: Position) -> float:
        return float(self.values.get(f"{position.row},{position.col}", 0.0))


class NetworkMatchRunner:
    def __init__(
        self, settings: NetworkMatchSettings, inboxes: PeerInboxes,
        gemini_advisor: GeminiAgentAdvisor | None = None,
        transport: McpPeerTransport | None = None,
    ) -> None:
        self.settings = settings
        self.gemini_advisor = gemini_advisor
        self.transport = transport or McpPeerTransport(settings.opponent_url, inboxes)

    def run(self, stop: Event, emit: EventSink = lambda _message: None) -> Path:
        params = load_match_parameters(self.settings.shared_config)
        timeout = params.network_league.response_timeout_sec
        terms = self._terms(params)
        emit("Negotiating signed game terms and peer identity")
        peer_agreement = self.transport.exchange_agreement(
            create_agreement(terms, self._identity()), timeout,
        )
        peer_identity = verify_agreement(peer_agreement, terms)
        emit(f"Negotiation verified with {peer_identity.get('group_name', 'opponent')}")
        self._write_pregame_files(params)
        self._send_control("enable", "READY")

        board = Board(params.board)
        own_position = (
            params.cop_start if self.settings.role is AgentRole.COP else params.thief_start
        )
        own_scent = ScentField(params.board.grid_size, params.scent)
        belief = BeliefMap(board)
        brain = ManhattanHeuristicBrain(self.settings.role)
        own_records: list[dict] = []
        peer_commits: dict[int, str] = {}
        peer_turns: list[TurnMessage] = []
        pending_claim_response: dict | None = None
        thief_boxed_in = False
        outcome = MatchOutcome.SURVIVAL
        wire_role = WIRE_ROLES[self.settings.role.value]
        emit(f"Peer ready as {wire_role.upper()} - game {self.settings.game_id}")

        for step in range(1, params.max_moves + 1):
            if stop.is_set():
                self._send_control("quit", "STOPPED")
                raise RuntimeError("network match cancelled")
            active_role = AgentRole.THIEF if step % 2 == 1 else AgentRole.COP
            if active_role is self.settings.role:
                self._send_control("status", "THINKING")
                fallback = brain._decide_move(board, own_position, belief)
                move, hint = self._choose_move(
                    board, belief, own_position, fallback, step, params.max_moves, emit,
                )
                state_before = own_position
                own_position = board.apply_move(own_position, move)
                own_scent.decay()
                own_scent.emit(own_position)
                barrier_placed = self._maybe_place_barrier(board, own_position, belief, brain, emit, step)
                payload = {
                    "step": step,
                    "role": wire_role,
                    "state": {"row": state_before.row, "col": state_before.col},
                    "position": [own_position.row, own_position.col],
                    "move": move.value,
                    "intent": True,
                    "hint": hint,
                }
                record = seal_payload(payload)
                own_records.append(record)
                capture_claim = (
                    [own_position.row, own_position.col]
                    if self.settings.role is AgentRole.COP else None
                )
                win_claim = (
                    {"type": "boxed_in"} if self.settings.role is AgentRole.THIEF and thief_boxed_in
                    else {"type": "survival"}
                    if self.settings.role is AgentRole.THIEF and step == params.max_moves
                    else None
                )
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
                emit(f"Step {step}: sealed turn delivered; nonce remains private")
                if pending_claim_response and pending_claim_response.get("caught"):
                    outcome = MatchOutcome.CAPTURE
                    break
                if win_claim:
                    outcome = MatchOutcome.CAPTURE if win_claim.get("type") == "boxed_in" else MatchOutcome.SURVIVAL
                    break
                if step == params.max_moves:
                    outcome = MatchOutcome.SURVIVAL
                    break
            else:
                self._send_control("status", "WAITING")
                message = TurnMessage.from_dict(self.transport.receive_turn(timeout))
                expected_sender = WIRE_ROLES[active_role.value]
                if message.step != step or message.sender != expected_sender:
                    raise NetworkProtocolError("received an out-of-order or wrong-role turn")
                peer_commits[step] = message.commit
                peer_turns.append(message)
                belief.update_from_scent(_WireScent(message.smell_grid))
                emit(f"Step {step}: received sealed {message.sender} turn")
                if message.barrier_placed is not None:
                    barrier_target = Position(*message.barrier_placed)
                    board.apply_declared_barrier(barrier_target)
                    emit(f"Step {step}: opponent publicly declared a barrier at {barrier_target}")
                if self.settings.role is AgentRole.THIEF:
                    claimed = [
                        list(claim) for claim in (message.capture_claim, message.barrier_placed)
                        if claim is not None
                    ]
                    if claimed:
                        caught = [own_position.row, own_position.col] in claimed
                        pending_claim_response = {"claim": claimed, "caught": caught}
                    if is_boxed_in(board, own_position):
                        thief_boxed_in = True
                        emit(f"Step {step}: no legal move remains -- boxed in (Sec. 3.3.5)")
                if (
                    self.settings.role is AgentRole.COP
                    and message.claim_response
                    and message.claim_response.get("caught")
                ):
                    outcome = MatchOutcome.CAPTURE
                    break
                if message.win_claim:
                    claim_type = message.win_claim.get("type")
                    outcome = MatchOutcome.CAPTURE if claim_type == "boxed_in" else MatchOutcome.SURVIVAL
                    break
                if step == params.max_moves:
                    outcome = MatchOutcome.SURVIVAL
                    break

        emit("Exchanging final audit records and nonce reveals")
        peer_audit = AuditPayload.from_dict(self.transport.exchange_audit(
            AuditPayload(wire_role, own_records, outcome.value).to_dict(), timeout,
        ))
        audit_ok, failed = audit_records(peer_audit.records, peer_commits)
        if not audit_ok:
            raise RuntimeError(f"opponent audit failed at steps {failed}")
        if peer_audit.result_claim != outcome.value:
            raise RuntimeError("opponent result claim does not match local result")
        entries = self._combined_log(own_records, peer_audit.records)
        path = self._write_result(params, entries, outcome, emit)
        self._send_control("status", "COMPLETE")
        if self.settings.email_mode == "real":
            from police_thief.services.network_reporting import email_result_file

            email_result_file(path, params, self.settings, emit)
        else:
            emit("Email mode is dry_run; JSON created but not sent")
        return path

    def _choose_move(self, board, belief, own, fallback, step, max_steps, emit):
        if self.gemini_advisor is None:
            return fallback, "Deterministic local-truth move"
        decision = self.gemini_advisor.choose_move(
            TacticalContext(
                role=self.settings.role, own_position=own, belief_peak=belief.arg_max(),
                legal_moves=tuple(board.legal_moves(own)), turn_number=step,
                max_turns=max_steps, remaining_barriers=board.remaining_barrier_budget,
            ),
            fallback,
        )
        source = "fallback" if decision.used_fallback else "Gemini"
        emit(f"Step {step}: {source} - {decision.rationale}")
        return decision.move, decision.rationale

    def _maybe_place_barrier(self, board, own_position, belief, brain, emit, step) -> list[int] | None:
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
        if self.settings.role is not AgentRole.COP:
            return None
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
            "min_center_intensity": params.scent.center_intensity,
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
        return {
            "group_id": s.team_name.lower().replace(" ", "-"),
            "group_name": s.team_name,
            "members": list(s.members),
            "repos": {"cop": s.own_cop_repo, "thief": s.own_thief_repo},
            "mcp_servers": {WIRE_ROLES[s.role.value]: s.public_url},
            "llm_model": "gemini",
            "protocol": {"name": "police-thief-mcp", "version": "3.0.0"},
        }

    @staticmethod
    def _scent_snapshot(scent: ScentField, size: int) -> dict[str, float]:
        return {
            f"{row},{col}": round(scent.intensity_at(Position(row, col)), 6)
            for row in range(size) for col in range(size)
            if scent.intensity_at(Position(row, col)) > 0
        }

    @staticmethod
    def _combined_log(own_records: list[dict], peer_records: list[dict]) -> list[LogEntry]:
        records = sorted((*own_records, *peer_records), key=lambda item: item["payload"]["step"])
        return [
            LogEntry(
                state=record["payload"]["state"], move=record["payload"]["move"],
                intent=record["payload"]["intent"], nonce=record["nonce"],
                h_commit=record["commit"],
            )
            for record in records
        ]

    def _write_pregame_files(self, params) -> None:
        s = self.settings
        fingerprint = config_fingerprint(s.shared_config)
        step0 = Step0Declaration(
            hardware=gather_hardware_spec("gemini-network-agent"), code_version="3.00",
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

    def _write_result(self, params, entries, outcome, emit: EventSink) -> Path:
        s = self.settings
        save_log(entries, s.output_dir / f"log_{s.game_id}_g{s.sub_game_number:02d}.json")
        cop_score, thief_score = score_for(outcome, params.scoring)
        result = build_match_result(
            s.game_id, s.sub_game_number, cop_score, thief_score, outcome.value, True,
            entries, TokenUsage(), RepoCrossLinks(
                s.own_cop_repo, s.own_thief_repo,
                s.opponent_cop_repo, s.opponent_thief_repo,
            ),
            ResultTeamIdentity(s.team_name, s.members),
            ResultTeamIdentity(s.opponent_team_name, s.opponent_members),
        )
        path = save_match_result(result, s.output_dir)
        emit(f"Audit verified; result saved to {path}")
        return path
