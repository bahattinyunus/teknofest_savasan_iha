"""
AeroCombat - Hava Tehdit Kütüphanesi ve Kinematik/Optik İmza Sınıflandırması.

TEKNOFEST Savaşan İHA ve muharebe ortamında karşılaşılan hava platformlarının
kinematik karakteristikleri, manevra yetenekleri ve tehdit derecelendirmesi.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Optional


class AirframeType(Enum):
    UNKNOWN = "UNKNOWN"
    FIXED_WING_FIGHTER = "FIXED_WING_FIGHTER"   # Sabit Kanat İt Dalaşı İHA'sı (İtişli / Çift Motor)
    ROTARY_WING_KAMIKAZE = "ROTARY_WING_KAMIKAZE" # Döner Kanat (Quadcopter / Hexacopter Kamikaze)
    SURVEILLANCE_GLIDER = "SURVEILLANCE_GLIDER" # Yavaş Süzülen / Keşif İHA'sı
    OPTICAL_DECOY = "OPTICAL_DECOY"             # Flare / Sahte Isı veya Görüntü Hedefi


class ThreatLevel(Enum):
    NONE = 0
    LOW = 1          # Menzil > 80m, görüş açısı dışında
    MEDIUM = 2       # Menzil 40-80m, takip yönünde
    HIGH = 3         # Menzil < 40m, manevra ile arkamıza geçiyor
    CRITICAL = 4     # Hedef arkamızda (<30m) ve kilitlenme konisinde (RWR Alarm!)


@dataclass
class ThreatProfile:
    """Belirli bir hava aracı sınıfının aerodinamik ve taktiksel profili."""
    name: str
    airframe_type: AirframeType
    cruise_speed_mps: float
    max_speed_mps: float
    max_turn_rate_dps: float
    nominal_wingspan_m: float
    wez_lock_range_m: float
    lock_cone_deg: float
    danger_index: float  # [0.0 - 1.0]


# Standart Tehdit Kütüphanesi Veritabanı
THREAT_LIBRARY: Dict[AirframeType, ThreatProfile] = {
    AirframeType.FIXED_WING_FIGHTER: ThreatProfile(
        name="Sabit Kanat Avcı İHA",
        airframe_type=AirframeType.FIXED_WING_FIGHTER,
        cruise_speed_mps=22.0,
        max_speed_mps=36.0,
        max_turn_rate_dps=45.0,
        nominal_wingspan_m=1.6,
        wez_lock_range_m=75.0,
        lock_cone_deg=25.0,
        danger_index=0.95
    ),
    AirframeType.ROTARY_WING_KAMIKAZE: ThreatProfile(
        name="Döner Kanat Kamikaze İHA",
        airframe_type=AirframeType.ROTARY_WING_KAMIKAZE,
        cruise_speed_mps=14.0,
        max_speed_mps=22.0,
        max_turn_rate_dps=90.0,
        nominal_wingspan_m=0.8,
        wez_lock_range_m=35.0,
        lock_cone_deg=40.0,
        danger_index=0.75
    ),
    AirframeType.SURVEILLANCE_GLIDER: ThreatProfile(
        name="Keşif Planörü",
        airframe_type=AirframeType.SURVEILLANCE_GLIDER,
        cruise_speed_mps=12.0,
        max_speed_mps=18.0,
        max_turn_rate_dps=20.0,
        nominal_wingspan_m=2.2,
        wez_lock_range_m=45.0,
        lock_cone_deg=20.0,
        danger_index=0.30
    ),
    AirframeType.OPTICAL_DECOY: ThreatProfile(
        name="Optik Yanıltıcı / Karıştırıcı",
        airframe_type=AirframeType.OPTICAL_DECOY,
        cruise_speed_mps=0.0,
        max_speed_mps=10.0,
        max_turn_rate_dps=180.0,
        nominal_wingspan_m=0.3,
        wez_lock_range_m=0.0,
        lock_cone_deg=0.0,
        danger_index=0.05
    )
}
