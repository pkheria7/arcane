from __future__ import annotations

from enum import StrEnum


class Action(StrEnum):
    LEFT = "left"
    STRAIGHT = "straight"
    RIGHT = "right"
    STOP = "stop"


class ReasonCode(StrEnum):
    CLEAR_PATH = "clear_path"
    LEFT_OBSTACLE = "left_obstacle"
    RIGHT_OBSTACLE = "right_obstacle"
    FRONT_OBSTACLE_LEFT_GAP = "front_obstacle_left_gap"
    FRONT_OBSTACLE_RIGHT_GAP = "front_obstacle_right_gap"
    EMERGENCY_STOP = "emergency_stop"
    NO_SAFE_PATH = "no_safe_path"
    MANUAL_CONTROL = "manual_control"


ACTIONS = [Action.LEFT, Action.STRAIGHT, Action.RIGHT, Action.STOP]
