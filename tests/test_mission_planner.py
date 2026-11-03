"""
Taktiksel Görev Planlayıcı Birim Testleri.
"""

import pytest
from autopilot.mission_planner import (
    TacticalMissionPlanner,
    SearchPattern,
    Waypoint
)


def test_mission_planner_creeping_line():
    planner = TacticalMissionPlanner()
    polygon = [
        [41.100, 28.900],
        [41.100, 28.910],
        [41.108, 28.910],
        [41.108, 28.900]
    ]
    wps = planner.generate_creeping_line(polygon, spacing_m=100.0)
    assert len(wps) >= 4
    assert planner.active_pattern == SearchPattern.CREEPING_LINE
    # Waypoint'lerin koordinatları poligon sınırları civarında olmalı
    for wp in wps:
        assert 41.099 <= wp.lat <= 41.109
        assert 28.899 <= wp.lon <= 28.911


def test_mission_planner_figure_8():
    planner = TacticalMissionPlanner()
    wps = planner.generate_figure_8(
        center_lat=41.100,
        center_lon=28.900,
        radius_m=100.0,
        points_per_loop=6
    )
    # İki halka x 6 nokta = 12 nokta
    assert len(wps) == 12
    assert planner.active_pattern == SearchPattern.FIGURE_8
    assert planner.get_current_waypoint() is not None


def test_mission_planner_orbit():
    planner = TacticalMissionPlanner()
    wps = planner.generate_orbit(
        center_lat=41.100,
        center_lon=28.900,
        radius_m=80.0,
        num_points=8
    )
    assert len(wps) == 8
    assert planner.active_pattern == SearchPattern.ORBIT_LOITER


def test_mission_planner_intercept_and_resume():
    planner = TacticalMissionPlanner()
    planner.generate_orbit(center_lat=41.100, center_lon=28.900, radius_m=50.0, num_points=4)
    original_wps_len = len(planner.waypoints)
    
    # Hedef tespit edildi -> Taktiksel Önleme ekle
    intercept_wp = planner.insert_tactical_intercept(
        target_lat=41.105,
        target_lon=28.905,
        target_alt_m=95.0
    )
    assert len(planner.waypoints) == 1
    assert planner.get_current_waypoint().is_intercept is True
    assert planner.get_current_waypoint().lat == 41.105

    # Hedef kaybedildi veya görev bitti -> Devriyeye dön
    resumed_wp = planner.resume_patrol()
    assert resumed_wp is not None
    assert len(planner.waypoints) == original_wps_len


def test_mission_planner_waypoint_advance():
    planner = TacticalMissionPlanner(acceptance_radius_m=20.0)
    planner.waypoints = [
        Waypoint(lat=41.100, lon=28.900, alt_m=80.0, id=1),
        Waypoint(lat=41.105, lon=28.900, alt_m=80.0, id=2)
    ]
    planner.current_wp_idx = 0
    
    # 5 metre yakınına geldik -> Sıradaki WP'ye geçmeli
    next_wp = planner.update(current_lat=41.10003, current_lon=28.900, current_alt_m=80.0)
    assert next_wp.id == 2
    assert planner.current_wp_idx == 1
