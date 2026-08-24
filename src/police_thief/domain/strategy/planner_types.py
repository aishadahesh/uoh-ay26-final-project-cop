"""The scored action and the ranked plan the planner returns."""

from __future__ import annotations

from dataclasses import dataclass

from police_thief.domain.board import Move, Position


@dataclass(frozen=True)
class ActionEvaluation:
    move: Move
    destination: Position
    total: float
    path_distance: float
    mobility: int
    future_value: float
    revisit_penalty: float
    loop_penalty: float
    dead_end_penalty: float
    variation_bonus: float
    direct_capture_risk: float = 0.0
    proximity_risk: float = 0.0
    escape_routes: float = 0.0
    trap_risk: float = 0.0
    intercept_distance: float = 0.0
    containment: float = 0.0
    escape_space: float = 0.0
    boundary_penalty: float = 0.0

    def summary(self) -> str:
        return (
            f"total={self.total:.2f}, path={self.path_distance:.2f}, "
            f"mobility={self.mobility}, future={self.future_value:.2f}, "
            f"revisit={self.revisit_penalty:.2f}, loop={self.loop_penalty:.2f}, "
            f"dead_end={self.dead_end_penalty:.2f}, variation={self.variation_bonus:.2f}, "
            f"direct_capture_risk={self.direct_capture_risk:.3f}, "
            f"proximity_risk={self.proximity_risk:.3f}, "
            f"escape_routes={self.escape_routes:.2f}, trap_risk={self.trap_risk:.3f}, "
            f"boundary={self.boundary_penalty:.2f}"
        )


@dataclass(frozen=True)
class StrategyPlan:
    selected: Move
    evaluations: tuple[ActionEvaluation, ...]
    allowed_moves: tuple[Move, ...]
    loop_detected: bool
    loop_reason: str
    excluded_moves: tuple[Move, ...]
    recent_positions: tuple[Position, ...]
    recent_actions: tuple[Move, ...]
