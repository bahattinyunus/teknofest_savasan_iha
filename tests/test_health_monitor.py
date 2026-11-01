"""
HealthMonitor ve Failsafe Durum Makinesi Birim Testleri.
"""

import pytest
from core.health_monitor import (
    HealthMonitor,
    FailsafeLevel,
    FailSafeAction,
    SystemHealthMetrics
)


def test_health_monitor_nominal():
    monitor = HealthMonitor()
    metrics = SystemHealthMetrics(
        battery_pct=95.0,
        mavlink_heartbeat_age_s=0.2,
        referee_last_response_age_s=0.1,
        gps_fix_type=3,
        gps_hdop=0.8,
        cpu_temp_c=45.0,
        camera_fps=30.0
    )
    level = monitor.evaluate(metrics)
    assert level == FailsafeLevel.NOMINAL
    assert monitor.current_action == FailSafeAction.NONE
    assert len(monitor.active_faults) == 0


def test_health_monitor_battery_escalation():
    monitor = HealthMonitor()
    
    # 1. Uyarı seviyesi (< %25)
    metrics_warn = SystemHealthMetrics(battery_pct=22.0)
    level = monitor.evaluate(metrics_warn)
    assert level == FailsafeLevel.WARNING
    assert monitor.current_action == FailSafeAction.DISENGAGE_COMBAT
    assert any("BATARYA" in f for f in monitor.active_faults)
    
    # 2. Kritik seviye (< %15)
    metrics_crit = SystemHealthMetrics(battery_pct=13.0)
    level = monitor.evaluate(metrics_crit)
    assert level == FailsafeLevel.CRITICAL
    assert monitor.current_action == FailSafeAction.RTL
    
    # 3. Acil iniş (< %10)
    metrics_emerg = SystemHealthMetrics(battery_pct=8.0)
    level = monitor.evaluate(metrics_emerg)
    assert level == FailsafeLevel.EMERGENCY
    assert monitor.current_action == FailSafeAction.LAND_IMMEDIATE


def test_health_monitor_link_loss_and_callbacks():
    monitor = HealthMonitor()
    rtl_triggered = []
    
    monitor.register_action_callback(FailSafeAction.RTL, lambda: rtl_triggered.append(True))
    
    # 35 saniye boyunca bağlantı yok -> EMERGENCY & RTL
    metrics = SystemHealthMetrics(
        mavlink_heartbeat_age_s=35.0,
        referee_last_response_age_s=35.0
    )
    level = monitor.evaluate(metrics)
    assert level == FailsafeLevel.EMERGENCY
    assert monitor.current_action == FailSafeAction.RTL
    assert len(rtl_triggered) == 1


def test_health_monitor_host_sample():
    metrics = HealthMonitor.sample_host_metrics()
    assert "cpu_percent" in metrics
    assert "ram_percent" in metrics
    assert "disk_free_gb" in metrics
    assert metrics["disk_free_gb"] > 0
