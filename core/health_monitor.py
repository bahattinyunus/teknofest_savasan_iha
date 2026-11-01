"""
Sistem Sağlığı ve Akıllı Acil Durum / Fail-Safe İzleyicisi (Health & Fail-Safe Monitor).
Batarya, GPS kalitesi, MAVLink bağlantısı, hakem sunucusu RTT'si ve sistem kaynaklarını (CPU/RAM/Sıcaklık)
izler; kademeli acil durum durum makinesiyle (FSM) otonom güvenlik kararları üretir.
"""

import time
import os
import psutil
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Callable
from core.logger import logger
from core.event_bus import bus


class FailsafeLevel(Enum):
    """Kademeli güvenlik alarm seviyeleri."""
    NOMINAL = "NOMINAL"       # Tüm sistemler normal
    ADVISORY = "ADVISORY"     # Düşük öncelikli dikkat (örn. GPS HDOP hafif yüksek, CPU %70)
    WARNING = "WARNING"       # Uyarı (örn. batarya <%25, telemetri gecikmesi > 3sn)
    CRITICAL = "CRITICAL"     # Kritik (örn. batarya <%15, bağlantı kaybı > 15sn, Geofence uyarısı)
    EMERGENCY = "EMERGENCY"   # Acil durum (örn. batarya <%10, tam sinyal kaybı > 30sn, motor arızası)


class FailSafeAction(Enum):
    """Güvenlik seviyesine göre tetiklenecek otonom aksiyonlar."""
    NONE = "NONE"
    ALERT_OPERATOR = "ALERT_OPERATOR"
    DISENGAGE_COMBAT = "DISENGAGE_COMBAT"
    LOITER = "LOITER"
    RTL = "RTL"                    # Return to Launch (Kalkış noktasına dön)
    LAND_IMMEDIATE = "LAND_IMMEDIATE" # Acil iniş
    TERMINATE = "TERMINATE"        # Acil motor durdurma / paraşüt


@dataclass
class SystemHealthMetrics:
    """Anlık toplanan sistem sağlığı metrikleri."""
    timestamp: float = field(default_factory=time.time)
    
    # Batarya metrikleri
    battery_pct: float = 100.0
    battery_voltage: float = 16.8      # 4S LiPo nominal tam dolu
    battery_current_a: float = 0.0
    cell_delta_v: float = 0.02         # Hücre voltaj dengesizliği
    
    # Otopilot & MAVLink
    mavlink_heartbeat_age_s: float = 0.0
    gps_fix_type: int = 3              # 3: 3D Fix, 4: DGPS, 5: RTK Float, 6: RTK Fixed
    gps_hdop: float = 0.9              # Yatay hassasiyet (< 1.5 iyi)
    satellites_visible: int = 14
    
    # Hakem Sunucusu & RF Bağı
    referee_rtt_ms: float = 45.0
    referee_last_response_age_s: float = 0.1
    referee_packet_loss_pct: float = 0.0
    
    # Bilgisayar & Görüntü Donanımı
    cpu_percent: float = 25.0
    cpu_temp_c: float = 48.0
    ram_used_pct: float = 35.0
    disk_free_gb: float = 50.0
    camera_fps: float = 30.0
    camera_dropout_count: int = 0


class HealthMonitor:
    """
    Sistem sağlığını sürekli denetleyen ve acil durum eskalasyon merdivenini yöneten sınıf.
    """
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or {}
        health_cfg = cfg.get("saglik_izleme", {})
        
        self.battery_warn_pct = float(health_cfg.get("batarya_uyari_yuzdesi", 25.0))
        self.battery_crit_pct = float(health_cfg.get("batarya_kritik_yuzdesi", 15.0))
        self.battery_emerg_pct = float(health_cfg.get("batarya_acil_yuzdesi", 10.0))
        
        self.link_loss_warn_s = float(health_cfg.get("baglanti_kopma_uyari_sn", 5.0))
        self.link_loss_crit_s = float(health_cfg.get("baglanti_kopma_kritik_sn", 15.0))
        self.link_loss_emerg_s = float(health_cfg.get("baglanti_kopma_acil_sn", 30.0))
        
        self.max_cpu_temp_c = float(health_cfg.get("max_cpu_sicaklik_c", 80.0))
        self.max_hdop = float(health_cfg.get("max_gps_hdop", 2.2))
        self.min_camera_fps = float(health_cfg.get("min_kamera_fps", 12.0))
        
        self.current_level = FailsafeLevel.NOMINAL
        self.current_action = FailSafeAction.NONE
        self.active_faults: List[str] = []
        self._action_callbacks: Dict[FailSafeAction, List[Callable[[], None]]] = {}

    def register_action_callback(self, action: FailSafeAction, callback: Callable[[], None]) -> None:
        """Belirli bir failsafe aksiyonu tetiklendiğinde çağrılacak işlevi kaydeder."""
        if action not in self._action_callbacks:
            self._action_callbacks[action] = []
        self._action_callbacks[action].append(callback)

    def evaluate(self, metrics: SystemHealthMetrics) -> FailsafeLevel:
        """
        Gelen metrikleri kurallara göre değerlendirir, hata listesini günceller ve seviyeyi belirler.
        """
        faults: List[str] = []
        level = FailsafeLevel.NOMINAL
        action = FailSafeAction.NONE

        # 1. Batarya Kontrolleri
        if metrics.battery_pct <= self.battery_emerg_pct:
            faults.append(f"ACIL_DUSUK_BATARYA (%{metrics.battery_pct:.1f})")
            level = max(level, FailsafeLevel.EMERGENCY, key=lambda l: self._level_priority(l))
            action = FailSafeAction.LAND_IMMEDIATE
        elif metrics.battery_pct <= self.battery_crit_pct:
            faults.append(f"KRITIK_DUSUK_BATARYA (%{metrics.battery_pct:.1f})")
            level = max(level, FailsafeLevel.CRITICAL, key=lambda l: self._level_priority(l))
            action = max(action, FailSafeAction.RTL, key=lambda a: self._action_priority(a))
        elif metrics.battery_pct <= self.battery_warn_pct:
            faults.append(f"UYARI_BATARYA_AZALDI (%{metrics.battery_pct:.1f})")
            level = max(level, FailsafeLevel.WARNING, key=lambda l: self._level_priority(l))
            action = max(action, FailSafeAction.DISENGAGE_COMBAT, key=lambda a: self._action_priority(a))

        # 2. Bağlantı / Link Kaybı (MAVLink veya Hakem)
        link_age = max(metrics.mavlink_heartbeat_age_s, metrics.referee_last_response_age_s)
        if link_age >= self.link_loss_emerg_s:
            faults.append(f"ACIL_BAGLANTI_KOPUKLUĞU ({link_age:.1f}s)")
            level = max(level, FailsafeLevel.EMERGENCY, key=lambda l: self._level_priority(l))
            action = max(action, FailSafeAction.RTL, key=lambda a: self._action_priority(a))
        elif link_age >= self.link_loss_crit_s:
            faults.append(f"KRITIK_BAGLANTI_KOPUKLUĞU ({link_age:.1f}s)")
            level = max(level, FailsafeLevel.CRITICAL, key=lambda l: self._level_priority(l))
            action = max(action, FailSafeAction.LOITER, key=lambda a: self._action_priority(a))
        elif link_age >= self.link_loss_warn_s:
            faults.append(f"UYARI_BAGLANTI_GECIKMESI ({link_age:.1f}s)")
            level = max(level, FailsafeLevel.WARNING, key=lambda l: self._level_priority(l))
            action = max(action, FailSafeAction.ALERT_OPERATOR, key=lambda a: self._action_priority(a))

        # 3. GPS Kalitesi
        if metrics.gps_fix_type < 3 or metrics.gps_hdop > self.max_hdop:
            faults.append(f"KOTU_GPS_SINYALI (HDOP={metrics.gps_hdop:.2f}, Fix={metrics.gps_fix_type})")
            level = max(level, FailsafeLevel.WARNING, key=lambda l: self._level_priority(l))
            action = max(action, FailSafeAction.DISENGAGE_COMBAT, key=lambda a: self._action_priority(a))

        # 4. İşlemci Sıcaklığı
        if metrics.cpu_temp_c >= self.max_cpu_temp_c:
            faults.append(f"YUKSEK_CPU_SICAKLIGI ({metrics.cpu_temp_c:.1f}C)")
            level = max(level, FailsafeLevel.WARNING, key=lambda l: self._level_priority(l))

        # 5. Kamera Akışı
        if metrics.camera_fps < self.min_camera_fps and metrics.camera_fps > 0:
            faults.append(f"DUSUK_KAMERA_FPS ({metrics.camera_fps:.1f} FPS)")
            level = max(level, FailsafeLevel.ADVISORY, key=lambda l: self._level_priority(l))

        # Durum değişikliği kontrolü
        old_level = self.current_level
        self.current_level = level
        self.current_action = action
        self.active_faults = faults

        if old_level != level:
            logger.warning(
                f"[HealthMonitor] Seviye değişti: {old_level.value} -> {level.value} | "
                f"Aksiyon: {action.value} | Hatalar: {faults}"
            )
            bus.emit(
                "FAILSAFE_STATE_CHANGE",
                old_level=old_level.value,
                new_level=level.value,
                action=action.value,
                faults=faults
            )
            self._trigger_action(action)

        return level

    def _trigger_action(self, action: FailSafeAction) -> None:
        """İlgili aksiyon için kayıtlı geri çağrıları çalıştırır."""
        if action in self._action_callbacks:
            for cb in self._action_callbacks[action]:
                try:
                    cb()
                except Exception as e:
                    logger.error(f"[HealthMonitor] Aksiyon callback hatası ({action.value}): {e}")

    @staticmethod
    def _level_priority(lvl: FailsafeLevel) -> int:
        mapping = {
            FailsafeLevel.NOMINAL: 0,
            FailsafeLevel.ADVISORY: 1,
            FailsafeLevel.WARNING: 2,
            FailsafeLevel.CRITICAL: 3,
            FailsafeLevel.EMERGENCY: 4
        }
        return mapping.get(lvl, 0)

    @staticmethod
    def _action_priority(act: FailSafeAction) -> int:
        mapping = {
            FailSafeAction.NONE: 0,
            FailSafeAction.ALERT_OPERATOR: 1,
            FailSafeAction.DISENGAGE_COMBAT: 2,
            FailSafeAction.LOITER: 3,
            FailSafeAction.RTL: 4,
            FailSafeAction.LAND_IMMEDIATE: 5,
            FailSafeAction.TERMINATE: 6
        }
        return mapping.get(act, 0)

    @staticmethod
    def sample_host_metrics() -> Dict[str, float]:
        """Yerel donanım yükünü (CPU, RAM, Disk) örnekler."""
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory().percent
        disk = psutil.disk_usage(os.path.abspath(os.sep)).free / (1024 ** 3)
        return {
            "cpu_percent": float(cpu),
            "ram_percent": float(ram),
            "disk_free_gb": float(round(disk, 2))
        }
