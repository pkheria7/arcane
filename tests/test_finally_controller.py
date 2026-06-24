from __future__ import annotations

import importlib


cfg_mod = importlib.import_module("finally.config")
controller_mod = importlib.import_module("finally.controller")
models_mod = importlib.import_module("finally.models")
motors_mod = importlib.import_module("finally.motors")


def sensor(**updates):
    data = models_mod.SensorSnapshot.empty().__dict__ | updates
    return models_mod.SensorSnapshot(**data)


def test_single_low_ultrasonic_spike_does_not_block():
    ctl = controller_mod.RuleController(cfg_mod.AutonomyConfig())
    decision = ctl.update(sensor(ultrasonic_cm=20.0), now=1.0)
    assert decision.state == "drive"


def test_front_block_exits_through_reverse_pivot_recover():
    cfg = cfg_mod.AutonomyConfig(blocked_stop_s=0.1, reverse_s=0.1, pivot_s=0.1, recover_s=0.1)
    ctl = controller_mod.RuleController(cfg)
    states = []
    for i in range(12):
        decision = ctl.update(sensor(ultrasonic_cm=28.0, left_gap=0.2, right_gap=0.8), now=1.0 + i * 0.11)
        states.append(decision.state)
    assert "blocked_stop" in states
    assert "reverse" in states
    assert "pivot" in states
    assert "recover" in states


def test_left_and_right_ir_steer_away():
    ctl = controller_mod.RuleController(cfg_mod.AutonomyConfig())
    left = ctl.update(sensor(ir_left=1, ultrasonic_cm=100.0), now=1.0)
    assert left.state == "avoid_side"
    assert left.command.front_right < left.command.front_left

    ctl = controller_mod.RuleController(cfg_mod.AutonomyConfig())
    right = ctl.update(sensor(ir_right=1, ultrasonic_cm=100.0), now=1.0)
    assert right.state == "avoid_side"
    assert right.command.front_left < right.command.front_right


def test_motor_mix_four_wheel_signs():
    straight = motors_mod.command_all(0.4, "forward")
    assert straight.front_left > 0
    assert straight.front_right > 0
    assert straight.rear_left > 0
    assert straight.rear_right > 0

    reverse = motors_mod.command_all(-0.4, "reverse")
    assert reverse.front_left < 0
    assert reverse.front_right < 0
    assert reverse.rear_left < 0
    assert reverse.rear_right < 0

    left = motors_mod.pivot(-1, 0.4)
    assert left.front_left < 0
    assert left.rear_left < 0
    assert left.front_right > 0
    assert left.rear_right > 0

    right = motors_mod.pivot(1, 0.4)
    assert right.front_left > 0
    assert right.rear_left > 0
    assert right.front_right < 0
    assert right.rear_right < 0
