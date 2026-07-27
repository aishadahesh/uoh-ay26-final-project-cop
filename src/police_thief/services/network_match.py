"""Two-process Agent-vs-Agent match loop over FastMCP."""

from __future__ import annotations

import json
import queue
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import Event

from police_thief.domain.belief import BeliefMap
from police_thief.domain.board import Board
from police_thief.domain.capture import check_capture
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
from police_thief.services.mcp_client import PeerClientError, send_move
from police_thief.services.mcp_server import MoveEnvelope
from police_thief.services.network_protocol import (
    NetworkMove,
    NetworkProtocolError,
    create_network_move,
    create_result_proof,
    parse_network_move,
    parse_result_proof,
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


class NetworkMatchRunner:
    def __init__(
        self, settings: NetworkMatchSettings, gemini_advisor: GeminiAgentAdvisor | None = None,
    ) -> None:
        self.settings = settings
        self.gemini_advisor = gemini_advisor
        self.inbox: queue.Queue[NetworkMove] = queue.Queue()
        self.result_inbox: queue.Queue[dict] = queue.Queue()

    def receive(self, envelope: MoveEnvelope) -> dict:
        try:
            raw = json.loads(envelope.signed_move)
            if raw.get("kind") == "result":
                result = parse_result_proof(
                    envelope.signed_move, envelope.signature, self.settings.shared_key,
                )
                if result.get("game_id") != self.settings.game_id:
                    return {"accepted": False, "reason": "game_id mismatch"}
                self.result_inbox.put(result)
                return {"accepted": True, "kind": "result"}
            message = parse_network_move(envelope.signed_move, envelope.signature)
        except (json.JSONDecodeError, NetworkProtocolError) as exc:
            return {"accepted": False, "reason": str(exc)}
        if message.game_id != self.settings.game_id:
            return {"accepted": False, "reason": "game_id mismatch"}
        self.inbox.put(message)
        return {"accepted": True, "turn_index": message.turn_index}

    def run(self, stop: Event, emit: EventSink = lambda _message: None) -> Path:
        params = load_match_parameters(self.settings.shared_config)
        board = Board(params.board)
        positions = {AgentRole.COP: params.cop_start, AgentRole.THIEF: params.thief_start}
        scents = {
            AgentRole.COP: ScentField(params.board.grid_size, params.scent),
            AgentRole.THIEF: ScentField(params.board.grid_size, params.scent),
        }
        beliefs = {AgentRole.COP: BeliefMap(board), AgentRole.THIEF: BeliefMap(board)}
        brain = ManhattanHeuristicBrain(self.settings.role)
        entries: list[LogEntry] = []
        outcome = MatchOutcome.SURVIVAL
        self._write_pregame_files(params)
        emit(f"Connected as {self.settings.role.value.upper()} - game {self.settings.game_id}")

        for turn_index in range(params.max_moves):
            if stop.is_set():
                raise RuntimeError("network match cancelled")
            active_role = AgentRole.COP if turn_index % 2 == 0 else AgentRole.THIEF
            if active_role is self.settings.role:
                own = positions[active_role]
                fallback = brain._decide_move(board, own, beliefs[active_role])
                move = fallback
                if self.gemini_advisor is not None:
                    decision = self.gemini_advisor.choose_move(
                        TacticalContext(
                            role=active_role,
                            own_position=own,
                            belief_peak=beliefs[active_role].arg_max(),
                            legal_moves=tuple(board.legal_moves(own)),
                            turn_number=turn_index + 1,
                            max_turns=params.max_moves,
                            remaining_barriers=board.remaining_barrier_budget,
                        ),
                        fallback,
                    )
                    move = decision.move
                    source = "fallback" if decision.used_fallback else "Gemini"
                    emit(f"Turn {turn_index + 1}: {source} - {decision.rationale}")
                message = create_network_move(self.settings.game_id, turn_index, active_role, own, move)
                self._send_with_retry(message, params.network_league.response_timeout_sec)
                emit(f"Turn {turn_index + 1}: sent {active_role.value} move {move.value}")
            else:
                emit(f"Turn {turn_index + 1}: waiting for {active_role.value} peer")
                try:
                    message = self.inbox.get(timeout=params.network_league.response_timeout_sec)
                except queue.Empty as exc:
                    raise RuntimeError("opponent turn timed out") from exc
                if message.turn_index != turn_index or message.role is not active_role:
                    raise RuntimeError("received an out-of-order peer move")
                emit(f"Turn {turn_index + 1}: received verified {message.move.value}")
            self._apply(board, positions, scents, beliefs, message)
            entries.append(message.to_log_entry())
            if check_capture(positions[AgentRole.COP], positions[AgentRole.THIEF]):
                outcome = MatchOutcome.CAPTURE
                break

        path = self._write_result(params, entries, outcome, emit)
        if self.settings.email_mode == "real":
            from police_thief.services.network_reporting import email_result_file

            email_result_file(path, params, self.settings, emit)
        else:
            emit("Email mode is dry_run; JSON created but not sent")
        return path

    def _send_payload_with_retry(self, payload: str, signature: str, timeout: float) -> None:
        deadline = time.monotonic() + timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                response = send_move(self.settings.opponent_url, payload, signature, min(5.0, timeout))
                if response.get("accepted"):
                    return
                raise PeerClientError(str(response.get("reason", "peer rejected move")))
            except PeerClientError as exc:
                last_error = exc
                time.sleep(1)
        raise RuntimeError(f"could not deliver move: {last_error}")

    def _send_with_retry(self, message: NetworkMove, timeout: float) -> None:
        self._send_payload_with_retry(*message.to_wire(), timeout)

    @staticmethod
    def _apply(board, positions, scents, beliefs, message: NetworkMove) -> None:
        if positions[message.role] != message.state:
            raise RuntimeError("peer state does not match the locally reconstructed state")
        positions[message.role] = board.apply_move(message.state, message.move)
        scents[message.role].decay()
        scents[message.role].emit(positions[message.role])
        other = AgentRole.THIEF if message.role is AgentRole.COP else AgentRole.COP
        beliefs[other].update_from_scent(scents[message.role])

    def _write_pregame_files(self, params) -> None:
        s = self.settings
        fingerprint = config_fingerprint(s.shared_config)
        step0 = Step0Declaration(
            hardware=gather_hardware_spec("gemini-network-agent"), code_version="1.00",
            team_name=s.team_name, game_id=s.game_id, sub_game_number=s.sub_game_number,
            git_commit_hash=get_git_commit_hash(str(s.shared_config.parent.parent)),
            config_fingerprint=fingerprint,
        )
        team = TeamInfo(s.team_name, s.members, s.own_cop_repo, s.own_thief_repo)
        signed = sign_step0(step0, s.shared_key)
        save_declaration(
            build_declaration(s.game_id, s.sub_game_number, team, signed,
                              params.network_league.token_budget_per_series), s.output_dir
        )
        raw_config = json.loads(s.shared_config.read_text(encoding="utf-8"))
        save_config_snapshot(
            build_config_snapshot(s.game_id, s.sub_game_number, raw_config, fingerprint), s.output_dir
        )

    def _write_result(self, params, entries, outcome, emit: EventSink) -> Path:
        s = self.settings
        save_log(entries, s.output_dir / f"log_{s.game_id}_g{s.sub_game_number:02d}.json")
        cop_score, thief_score = score_for(outcome, params.scoring)
        links = RepoCrossLinks(
            s.own_cop_repo, s.own_thief_repo, s.opponent_cop_repo, s.opponent_thief_repo
        )
        result = build_match_result(
            s.game_id, s.sub_game_number, cop_score, thief_score, outcome.value, False,
            entries, TokenUsage(), links,
            ResultTeamIdentity(s.team_name, s.members),
            ResultTeamIdentity(s.opponent_team_name, s.opponent_members),
        )
        emit("Exchanging authenticated result proof with opponent")
        payload, signature = create_result_proof(asdict(result), s.shared_key)
        self._send_payload_with_retry(
            payload, signature, params.network_league.response_timeout_sec,
        )
        try:
            peer_result = self.result_inbox.get(
                timeout=params.network_league.response_timeout_sec,
            )
        except queue.Empty as exc:
            raise RuntimeError("opponent result sign-off timed out") from exc
        own = asdict(result)
        agreement_fields = (
            "game_id", "sub_game_number", "cop_score", "thief_score", "outcome", "log_sha256",
        )
        if any(own[field] != peer_result.get(field) for field in agreement_fields):
            raise RuntimeError("opponent result does not match local score or log hash")
        signed_result = build_match_result(
            s.game_id, s.sub_game_number, cop_score, thief_score, outcome.value, True,
            entries, TokenUsage(), links,
            ResultTeamIdentity(s.team_name, s.members),
            ResultTeamIdentity(s.opponent_team_name, s.opponent_members),
        )
        path = save_match_result(signed_result, s.output_dir)
        emit(f"Match complete: {outcome.value}; result saved to {path}")
        return path
