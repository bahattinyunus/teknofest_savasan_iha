"""
AeroCombat Autopilot & Guidance Module
"""
from .mavlink_bridge import MavlinkBridge, MockMavlinkBridge
from .guidance import (
    GuidanceController,
    ProportionalNavigation,
    VisualServoingPID,
    PurePursuit,
    FlightEnvelopeLimiter
)
from .geofence import GeofenceMonitor
from .bfm_maneuvers import BFMEvasiveTactics, ManevraTipi
from .wind_estimator import WindEstimator
from .tactical_decision_agent import TacticalDecisionAgent, TacticalState
from .swarm_tactics import SwarmTacticsController, SwarmFormation, SwarmRole
from .collision_avoidance import (
    CollisionAvoidanceSystem,
    ACASAlertLevel,
    AvoidanceManeuver,
    AvoidanceAdvisory,
    ThreatAssessment
)
from .gnss_denied_nav import GNSSDeniedNavigator, GNSSStatus, GNSSSample
from .mission_planner import TacticalMissionPlanner, SearchPattern, Waypoint
from .energy_manager import EnergyManeuverabilityGovernor
from .neural_combat_pilot import NeuralCombatPilot
from .cooperative_combat import CooperativeCombatGovernor
from .mppi_guidance import MPPILockGuidanceController, MPPIControlCommand
from .mesh_datalink import TacticalMeshDatalink, MeshPacket, TriangulatedTarget3D, SwarmAllocationResult

__all__ = [
    "MavlinkBridge",
    "MockMavlinkBridge",
    "GuidanceController",
    "ProportionalNavigation",
    "VisualServoingPID",
    "PurePursuit",
    "FlightEnvelopeLimiter",
    "GeofenceMonitor",
    "BFMEvasiveTactics",
    "ManevraTipi",
    "WindEstimator",
    "TacticalDecisionAgent",
    "TacticalState",
    "SwarmTacticsController",
    "SwarmFormation",
    "SwarmRole",
    "CollisionAvoidanceSystem",
    "ACASAlertLevel",
    "AvoidanceManeuver",
    "AvoidanceAdvisory",
    "ThreatAssessment",
    "GNSSDeniedNavigator",
    "GNSSStatus",
    "GNSSSample",
    "TacticalMissionPlanner",
    "SearchPattern",
    "Waypoint",
    "EnergyManeuverabilityGovernor",
    "NeuralCombatPilot",
    "CooperativeCombatGovernor",
    "MPPILockGuidanceController",
    "MPPIControlCommand",
    "TacticalMeshDatalink",
    "MeshPacket",
    "TriangulatedTarget3D",
    "SwarmAllocationResult"
]
