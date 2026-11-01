"""
AeroCombat Simulation & Synthetic Feed Module
"""
from .virtual_camera import VirtualCameraFeed
from .dogfight_simulator import (
    DogfightSimulator,
    TargetBehavior,
    AircraftState,
    DogfightStepResult
)

__all__ = [
    "VirtualCameraFeed",
    "DogfightSimulator",
    "TargetBehavior",
    "AircraftState",
    "DogfightStepResult"
]
