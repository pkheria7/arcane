from inference.runtime import NavigationRuntime
from navigation_ai.actions import Action
from sensor_layer.types import SensorFrame


def test_runtime_falls_back_to_expert_without_model():
    decision = NavigationRuntime(model_path=None).decide(SensorFrame.empty())
    assert decision.action == Action.STRAIGHT
    assert abs(sum(decision.probabilities.values()) - 1.0) < 1e-9
