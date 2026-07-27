"""Interactive play mode: agent vs agent, human vs agent (either side), or
human vs human, in one local process.

docs/tasks.md never mandates a human-playable mode -- `BrainBase` (Chapter
6) is built entirely around autonomous agents, and the Live GUI (Chapter 7)
is built entirely around local-truth-only observation of one side's own
belief map. This module is a deliberate addition beyond the rulebook's own
scope, prompted directly by a request to bring the same "premium," mode-
selectable playable-GUI experience already proven in a separate prior
project into this one.

Kept pure and framework-agnostic (no Tkinter) -- the same "real logic in
domain/, the GUI only renders it" split established since Chapter 7's
`LiveViewModel` -- so every rule here is fully unit-testable without ever
constructing a `Tk()` window.

Local Truth (Chapter 7's headline guarantee) still holds in every mode that
involves at least one agent: `visible_view_for_current()` returns only the
current mover's own position and its belief about the opponent (built from
real scent), never the opponent's true position. `GameMode.HUMAN_VS_HUMAN`
is the one deliberate, explicitly user-confirmed exception: since both
humans share one physical screen by construction in this local hotseat
mode, `visible_view_for_current()` there returns both true positions
instead, matching the familiar shared-board hotseat convention the user
chose over a pass-and-play alternative that would have preserved local
truth even between two humans on one machine.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from police_thief.domain.belief import BeliefMap
from police_thief.domain.board import Board, Move, Position
from police_thief.domain.capture import check_capture, is_boxed_in
from police_thief.domain.heuristics import greedy_manhattan_move
from police_thief.domain.scent import ScentConfig, ScentField
from police_thief.domain.scoring import MatchOutcome
from police_thief.shared.constants import AgentRole


class PlayerType(StrEnum):
    AGENT = "agent"
    HUMAN = "human"


class GameMode(StrEnum):
    """The four selectable modes, mirroring the reference "playable GUI"
    experience this was modeled on, translated to this project's cop/thief
    terminology."""

    AGENT_VS_AGENT = "agent_vs_agent"
    NETWORK_AGENT_VS_AGENT = "network_agent_vs_agent"
    HUMAN_COP_VS_AGENT = "human_cop_vs_agent"
    AGENT_VS_HUMAN_THIEF = "agent_vs_human_thief"
    HUMAN_VS_HUMAN = "human_vs_human"


MODE_LABELS: dict[GameMode, str] = {
    GameMode.AGENT_VS_AGENT: "Agent vs Agent",
    GameMode.NETWORK_AGENT_VS_AGENT: "Agent vs Agent (Two Computers)",
    GameMode.HUMAN_COP_VS_AGENT: "Human (Cop) vs Agent",
    GameMode.AGENT_VS_HUMAN_THIEF: "Agent vs Human (Thief)",
    GameMode.HUMAN_VS_HUMAN: "Human vs Human",
}

_MODE_CONTROL: dict[GameMode, dict[AgentRole, PlayerType]] = {
    GameMode.AGENT_VS_AGENT: {AgentRole.COP: PlayerType.AGENT, AgentRole.THIEF: PlayerType.AGENT},
    GameMode.NETWORK_AGENT_VS_AGENT: {
        AgentRole.COP: PlayerType.AGENT,
        AgentRole.THIEF: PlayerType.AGENT,
    },
    GameMode.HUMAN_COP_VS_AGENT: {AgentRole.COP: PlayerType.HUMAN, AgentRole.THIEF: PlayerType.AGENT},
    GameMode.AGENT_VS_HUMAN_THIEF: {AgentRole.COP: PlayerType.AGENT, AgentRole.THIEF: PlayerType.HUMAN},
    GameMode.HUMAN_VS_HUMAN: {AgentRole.COP: PlayerType.HUMAN, AgentRole.THIEF: PlayerType.HUMAN},
}


def controller_for(mode: GameMode, role: AgentRole) -> PlayerType:
    return _MODE_CONTROL[mode][role]


def _other_role(role: AgentRole) -> AgentRole:
    return AgentRole.THIEF if role is AgentRole.COP else AgentRole.COP


@dataclass(frozen=True)
class VisibleView:
    """What the current mover is allowed to see this turn -- nothing more.

    `belief`/`opponent_position` are mutually exclusive: exactly one is
    populated, depending on whether Local Truth applies (see module
    docstring). Both `None` never happens; both set never happens.
    """

    own_position: Position
    own_role: AgentRole
    belief: BeliefMap | None
    opponent_position: Position | None


class InteractiveMatch:
    """One playable match: board state, both sides' scent/belief, and turn control."""

    def __init__(
        self,
        board: Board,
        cop_start: Position,
        thief_start: Position,
        mode: GameMode,
        max_moves: int,
    ) -> None:
        self.board = board
        self.mode = mode
        self.max_moves = max_moves
        self.positions: dict[AgentRole, Position] = {
            AgentRole.COP: cop_start,
            AgentRole.THIEF: thief_start,
        }
        self.scent: dict[AgentRole, ScentField] = {
            AgentRole.COP: ScentField(grid_size=board.config.grid_size, config=ScentConfig()),
            AgentRole.THIEF: ScentField(grid_size=board.config.grid_size, config=ScentConfig()),
        }
        self.belief: dict[AgentRole, BeliefMap] = {
            AgentRole.COP: BeliefMap(board),
            AgentRole.THIEF: BeliefMap(board),
        }
        self.current_role: AgentRole = AgentRole.COP  # an arbitrary, documented choice -- no rule mandates who moves first
        self.turns_played = 0
        self.outcome: MatchOutcome | None = None

    @property
    def is_finished(self) -> bool:
        return self.outcome is not None

    def is_human_turn(self) -> bool:
        return controller_for(self.mode, self.current_role) is PlayerType.HUMAN

    def legal_moves(self) -> dict[Move, Position]:
        return self.board.legal_moves(self.positions[self.current_role])

    def visible_view_for_current(self) -> VisibleView:
        role = self.current_role
        own_pos = self.positions[role]
        if self.mode is GameMode.HUMAN_VS_HUMAN:
            return VisibleView(
                own_position=own_pos, own_role=role, belief=None, opponent_position=self.positions[_other_role(role)]
            )
        return VisibleView(own_position=own_pos, own_role=role, belief=self.belief[role], opponent_position=None)

    def agent_move(self, advisor: Callable[[AgentRole, Position, Position, tuple[Move, ...], Move], Move] | None = None) -> Move:
        """The move the built-in Manhattan heuristic (Chapter 6) would make
        for the current, agent-controlled role: the cop chases its belief's
        best guess, the thief flees from it."""
        role = self.current_role
        guess = self.belief[role].arg_max()
        fallback = greedy_manhattan_move(
            self.board, self.positions[role], guess, chase=(role is AgentRole.COP)
        )
        if advisor is None:
            return fallback
        legal_moves = tuple(self.legal_moves())
        proposed = advisor(role, self.positions[role], guess, legal_moves, fallback)
        return proposed if proposed in legal_moves else fallback

    def _record_move_and_advance(self) -> None:
        """Shared bookkeeping after any legal action (move or barrier):
        capture/boxed-in/max-moves checks, then hand the turn over."""
        if not self.is_finished and check_capture(self.positions[AgentRole.COP], self.positions[AgentRole.THIEF]):
            self.outcome = MatchOutcome.CAPTURE
        if not self.is_finished and is_boxed_in(self.board, self.positions[AgentRole.THIEF]):
            self.outcome = MatchOutcome.CAPTURE
        self.turns_played += 1
        if not self.is_finished and self.turns_played >= self.max_moves:
            self.outcome = MatchOutcome.SURVIVAL
        if not self.is_finished:
            self.current_role = _other_role(self.current_role)

    def apply_move(self, move: Move) -> None:
        """Apply `move` for the current role: update position, scent, the
        opponent's belief, then advance the turn. Raises `MoveRejectedError`
        for an illegal move -- the caller must check `legal_moves()` first.
        """
        if self.is_finished:
            raise RuntimeError("match already finished")
        role = self.current_role
        opponent = _other_role(role)
        self.positions[role] = self.board.apply_move(self.positions[role], move)

        self.scent[role].decay()
        self.scent[role].emit(self.positions[role])
        self.belief[opponent].update_from_scent(self.scent[role])

        self._record_move_and_advance()

    def place_barrier(self, target: Position) -> None:
        """Cop-only: place a barrier at `target`, consuming the cop's turn.

        Raises `MoveRejectedError` for an illegal target/exhausted budget,
        or `ValueError` if it isn't currently the cop's turn.
        """
        if self.is_finished:
            raise RuntimeError("match already finished")
        if self.current_role is not AgentRole.COP:
            raise ValueError("only the cop may place a barrier, and only on its own turn")
        cop_pos = self.positions[AgentRole.COP]
        self.board.place_barrier(cop_pos, target)  # raises MoveRejectedError if illegal
        if check_capture(target, self.positions[AgentRole.THIEF]):
            self.outcome = MatchOutcome.CAPTURE
        self._record_move_and_advance()
