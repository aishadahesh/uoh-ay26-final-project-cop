"""Independent local-truth peer runtime over the four-tool MCP protocol."""

from __future__ import annotations

import json
import platform
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from threading import Event

from police_thief.domain.belief import BeliefMap
from police_thief.domain.board import Board, Position
from police_thief.domain.capture import is_boxed_in
from police_thief.domain.hints import TemplateHintProvider
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
    llm_model: str = "deterministic-heuristic"


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
        own_identity = self._identity()
        peer_agreement = self.transport.exchange_agreement(
            create_agreement(terms, own_identity), timeout,
        )
        peer_identity = verify_agreement(peer_agreement, terms)
        self._validate_peer_identity(peer_identity)
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
        hint_provider = TemplateHintProvider(params.world.hint_max_words)
        own_records: list[dict] = [self._sealed_system_spec()]
        peer_commits: dict[int, str] = {}
        pending_claim_response: dict | None = None
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
                self._send_control("status", "THINKING")
                fallback = brain._decide_move(board, own_position, belief)
                move, _private_reason = self._choose_move(
                    board, belief, own_position, fallback, step, params.max_moves, emit,
                )
                # Gemini's rationale is private reasoning and may mention local
                # truth.  Only a bounded direction claim crosses the wire.
                hint = hint_provider.generate(move, tell_truth=True).text
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
                    if self.settings.role is AgentRole.THIEF and step >= params.max_moves
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
                belief.update_from_scent(_WireScent(message.smell_grid))
                emit(f"Step {step}: received sealed {message.sender} turn")
                if message.barrier_placed is not None:
                    barrier_target = Position(*message.barrier_placed)
                    board.apply_declared_barrier(barrier_target)
                    emit(f"Step {step}: opponent publicly declared a barrier at {barrier_target}")
                if self.settings.role is AgentRole.THIEF:
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

        emit("Exchanging final audit records and nonce reveals")
        peer_audit = AuditPayload.from_dict(self.transport.exchange_audit(
            AuditPayload(wire_role, own_records, outcome.value).to_dict(), timeout,
        ))
        audit_ok, failed = audit_records(peer_audit.records, peer_commits, require_step0=True)
        if not audit_ok:
            raise RuntimeError(f"opponent audit failed at steps {failed}")
        if peer_audit.result_claim != outcome.value:
            raise RuntimeError("opponent result claim does not match local result")
        entries = self._combined_log(
            own_records, peer_audit.records, wire_role, peer_audit.sender,
        )
        path = self._write_result(params, entries, outcome, peer_identity, emit)
        self._send_control("status", "COMPLETE")
        if self.settings.email_mode == "real":
            from police_thief.services.network_reporting import email_result_file

            email_result_file(path, params, self.settings, emit)
        elif self.settings.email_mode == "dry_run":
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
            "mcp_servers": {WIRE_ROLES[s.role.value]: s.public_url},
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
            if configured and identity.get(field) != value:
                raise NetworkProtocolError(
                    f"opponent identity mismatch for {field}: configured {value!r}, "
                    f"negotiated {identity.get(field)!r}"
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
            (own_role, record) for record in own_records if record["payload"]["step"] > 0
        ] + [
            (peer_role, record) for record in peer_records if record["payload"]["step"] > 0
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

    def _write_result(self, params, entries, outcome, peer_identity: dict, emit: EventSink) -> Path:
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
        result = build_match_result(
            s.game_id, s.sub_game_number, cop_score, thief_score, outcome.value, True,
            entries, TokenUsage(), RepoCrossLinks(
                str(repos_a.get("cop", "")), str(repos_a.get("thief", "")),
                str(repos_b.get("cop", "")), str(repos_b.get("thief", "")),
            ),
            ResultTeamIdentity(
                str(team_a.get("group_name", "")), tuple(team_a.get("members", ())),
            ),
            ResultTeamIdentity(
                str(team_b.get("group_name", "")), tuple(team_b.get("members", ())),
            ),
        )
        path = save_match_result(
            result, s.output_dir,
            include_sub_game=params.network_league.num_games > 1,
        )
        emit(f"Audit verified; result saved to {path}")
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
        if num_games == 1:
            return NetworkMatchRunner(
                self.settings, self.inboxes, self.gemini_advisor, self.transport,
            ).run(stop, emit)

        subgames: list[dict] = []
        totals: dict[str, int] = {
            self.settings.team_name: 0,
            self.settings.opponent_team_name: 0,
        }
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
            path = NetworkMatchRunner(
                child_settings, self.inboxes, self.gemini_advisor, self.transport,
            ).run(stop, emit)
            result = json.loads(path.read_text(encoding="utf-8"))
            own_score_key = "cop_score" if role is AgentRole.COP else "thief_score"
            peer_score_key = "thief_score" if role is AgentRole.COP else "cop_score"
            totals[self.settings.team_name] += int(result[own_score_key])
            totals[self.settings.opponent_team_name] += int(result[peer_score_key])
            subgames.append({
                "sub_game_number": sub_game_number,
                "roles": {
                    self.settings.team_name: role.value,
                    self.settings.opponent_team_name: (
                        AgentRole.THIEF.value if role is AgentRole.COP else AgentRole.COP.value
                    ),
                },
                "outcome": result["outcome"],
                "cop_score": result["cop_score"],
                "thief_score": result["thief_score"],
                "log_sha256": result["log_sha256"],
                "result_file": path.name,
            })
            emit(f"Sub-game {series_index + 1}/{num_games} verified")

        ordered_totals = dict(sorted(totals.items(), key=lambda item: item[0].casefold()))
        highest = max(ordered_totals.values())
        winners = [team for team, score in ordered_totals.items() if score == highest]
        series_result = {
            "schema_version": "1.00",
            "game_id": self.settings.game_id,
            "num_games": num_games,
            "first_sub_game_number": self.settings.sub_game_number,
            "mutual_sign_off": True,
            "sub_games": subgames,
            "team_scores": ordered_totals,
            "winner": winners[0] if len(winners) == 1 else "tie",
        }
        path = save_series_result(series_result, self.settings.output_dir, self.settings.game_id)
        emit(f"Series complete; aggregate result saved to {path}")
        if self.settings.email_mode == "real":
            from police_thief.services.network_reporting import email_result_file

            email_result_file(path, params, self.settings, emit)
        else:
            emit("Email mode is dry_run; aggregate JSON created but not sent")
        return path
