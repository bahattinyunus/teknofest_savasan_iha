"""
Hava Çarpışma Önleme Sistemi (Airborne Collision Avoidance System - ACAS / TCAS).
Hakem sunucusundan gelen çoklu rakip telemetrilerini izler; En Yakın Yaklaşma Noktası (Closest Point of Approach - CPA)
ve Hız Engeli (Velocity Obstacle) hesaplayarak otonom çarpışma önleme manevraları (Resolution Advisory - RA) üretir.
"""

import math
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple
from core.models import RakipIHA, TelemetriPaketi
from core.logger import logger


class ACASAlertLevel(Enum):
    """ACAS Tehdit Seviyeleri."""
    CLEAR = "CLEAR"                   # Güvenli mesafe
    TRAFFIC_ADVISORY = "TRAFFIC_ADVISORY" # Yakında trafik var (TA - Görsel/Durumsal Farkındalık)
    RESOLUTION_ADVISORY = "RESOLUTION_ADVISORY" # Çarpışma rotasında! Acil kaçınma manevrası (RA)


class AvoidanceManeuver(Enum):
    """Otonom Kaçınma Manevrası Türü."""
    MAINTAIN = "MAINTAIN"       # Mevcut rotayı koru
    CLIMB = "CLIMB"             # Acil Tırmanış (+İrtifa)
    DESCEND = "DESCEND"         # Acil Alçalış (-İrtifa)
    TURN_LEFT = "TURN_LEFT"     # Sola Kaçınma Dönüşü
    TURN_RIGHT = "TURN_RIGHT"   # Sağa Kaçınma Dönüşü
    COORDINATED_ESCAPE = "COORDINATED_ESCAPE" # Hem irtifa hem yön değişimi


@dataclass
class ThreatAssessment:
    """Tek bir hedefe ilişkin ACAS tehdit analizi."""
    rakip_id: int
    current_distance_m: float
    cpa_distance_m: float
    time_to_cpa_s: float
    relative_speed_mps: float
    alert_level: ACASAlertLevel
    bearing_deg: float
    alt_difference_m: float      # Pozitif: Rakip bizim üstümüzde, Negatif: Altımızda


@dataclass
class AvoidanceAdvisory:
    """Otopilot seyrüseferine iletilen kaçınma tavsiyesi."""
    alert_level: ACASAlertLevel
    maneuver: AvoidanceManeuver
    target_heading_deg: Optional[float] = None
    target_altitude_m: Optional[float] = None
    critical_threat_id: Optional[int] = None
    details: str = "Trafik temiz"


class CollisionAvoidanceSystem:
    """
    3D ACAS / TCAS Mantığı ve Çarpışma Önleme Motoru.
    """
    def __init__(
        self,
        ta_distance_m: float = 75.0,
        ta_time_s: float = 8.0,
        ra_distance_m: float = 25.0,
        ra_time_s: float = 4.5,
        vertical_separation_m: float = 15.0,
        horizontal_escape_deg: float = 35.0,
        min_allowed_alt_m: float = 25.0,
        max_allowed_alt_m: float = 150.0
    ):
        self.ta_dist = ta_distance_m
        self.ta_time = ta_time_s
        self.ra_dist = ra_distance_m
        self.ra_time = ra_time_s
        self.vert_sep = vertical_separation_m
        self.horiz_deg = horizontal_escape_deg
        self.min_alt = min_allowed_alt_m
        self.max_alt = max_allowed_alt_m

    def assess_threats(
        self,
        own_telemetry: TelemetriPaketi,
        rivals: List[RakipIHA]
    ) -> List[ThreatAssessment]:
        """
        Tüm rakip İHA'lara karşı CPA ve çarpışma riski analizi yapar.
        """
        threats: List[ThreatAssessment] = []
        
        # Kendi hız vektörümüz (Kuzey, Doğu, Dikey)
        own_speed = max(0.1, own_telemetry.IHA_hiz)
        own_yaw_rad = math.radians(own_telemetry.IHA_yonelme)
        own_pitch_rad = math.radians(own_telemetry.IHA_dikilme)
        
        # Düzlemsel ve dikey bileşenler
        own_vn = own_speed * math.cos(own_pitch_rad) * math.cos(own_yaw_rad)
        own_ve = own_speed * math.cos(own_pitch_rad) * math.sin(own_yaw_rad)
        own_vd = -own_speed * math.sin(own_pitch_rad) # Aşağı pozitif
        
        for rival in rivals:
            # Bağıl mesafe vektörü (Metre cinsinden NED)
            d_lat = rival.IHA_enlem - own_telemetry.IHA_enlem
            d_lon = rival.IHA_boylam - own_telemetry.IHA_boylam
            
            # WGS84 yaklaşık dönüşüm
            r_north = d_lat * 111139.0
            r_east = d_lon * (111139.0 * math.cos(math.radians(own_telemetry.IHA_enlem)))
            r_down = -(rival.IHA_irtifa - own_telemetry.IHA_irtifa) # -Delta_alt
            
            curr_dist = math.sqrt(r_north ** 2 + r_east ** 2 + r_down ** 2)
            alt_diff = rival.IHA_irtifa - own_telemetry.IHA_irtifa
            
            # Rakip hız vektörü (varsayım: rakip kendi yönelmesinde uçuyor)
            # Eğer rakip hızı bilinmiyorsa tipik 18 m/s varsayılır
            rival_speed = 18.0
            rival_yaw_rad = math.radians(rival.IHA_yonelme)
            rival_pitch_rad = math.radians(rival.IHA_dikilme)
            
            rival_vn = rival_speed * math.cos(rival_pitch_rad) * math.cos(rival_yaw_rad)
            rival_ve = rival_speed * math.cos(rival_pitch_rad) * math.sin(rival_yaw_rad)
            rival_vd = -rival_speed * math.sin(rival_pitch_rad)
            
            # Bağıl hız vektörü: V_rel = V_rival - V_own
            v_rel_n = rival_vn - own_vn
            v_rel_e = rival_ve - own_ve
            v_rel_d = rival_vd - own_vd
            
            v_rel_sq = v_rel_n ** 2 + v_rel_e ** 2 + v_rel_d ** 2
            v_rel_mag = math.sqrt(v_rel_sq)
            
            # CPA Hesabı: tau = - (r . v_rel) / |v_rel|^2
            r_dot_v = (r_north * v_rel_n) + (r_east * v_rel_e) + (r_down * v_rel_d)
            
            if v_rel_mag > 0.5 and r_dot_v < 0: # Yaklaşma var (Closing)
                tau_cpa = -r_dot_v / v_rel_sq
                cpa_n = r_north + v_rel_n * tau_cpa
                cpa_e = r_east + v_rel_e * tau_cpa
                cpa_d = r_down + v_rel_d * tau_cpa
                dist_cpa = math.sqrt(cpa_n ** 2 + cpa_e ** 2 + cpa_d ** 2)
            else:
                tau_cpa = 999.0
                dist_cpa = curr_dist
                
            # Azimut açısı (Bearing)
            bearing_deg = (math.degrees(math.atan2(r_east, r_north))) % 360.0
            
            # Tehdit seviyesi belirleme
            alert = ACASAlertLevel.CLEAR
            if dist_cpa <= self.ra_dist and tau_cpa <= self.ra_time:
                alert = ACASAlertLevel.RESOLUTION_ADVISORY
            elif curr_dist <= self.ta_dist or tau_cpa <= self.ta_time:
                alert = ACASAlertLevel.TRAFFIC_ADVISORY
                
            threats.append(ThreatAssessment(
                rakip_id=rival.takim_numarasi,
                current_distance_m=round(curr_dist, 1),
                cpa_distance_m=round(dist_cpa, 1),
                time_to_cpa_s=round(tau_cpa, 2),
                relative_speed_mps=round(v_rel_mag, 1),
                alert_level=alert,
                bearing_deg=round(bearing_deg, 1),
                alt_difference_m=round(alt_diff, 1)
            ))

        # En tehlikeliye göre sırala (RA olanlar öne, sonra en düşük tau_cpa)
        threats.sort(key=lambda t: (
            0 if t.alert_level == ACASAlertLevel.RESOLUTION_ADVISORY else (1 if t.alert_level == ACASAlertLevel.TRAFFIC_ADVISORY else 2),
            t.time_to_cpa_s,
            t.cpa_distance_m
        ))
        
        return threats

    def compute_advisory(
        self,
        own_telemetry: TelemetriPaketi,
        rivals: List[RakipIHA]
    ) -> AvoidanceAdvisory:
        """
        Tehdit değerlendirmesi sonucunda otopilota doğrudan uygulanacak kaçınma rotasını belirler.
        """
        threats = self.assess_threats(own_telemetry, rivals)
        if not threats or threats[0].alert_level == ACASAlertLevel.CLEAR:
            return AvoidanceAdvisory(
                alert_level=ACASAlertLevel.CLEAR,
                maneuver=AvoidanceManeuver.MAINTAIN,
                details="Trafik güvenli mesafede."
            )
            
        critical = threats[0]
        
        # Yalnızca Trafik Uyarısı (TA) varsa rota değiştirme, sadece operatörü ve radarı uyar
        if critical.alert_level == ACASAlertLevel.TRAFFIC_ADVISORY:
            return AvoidanceAdvisory(
                alert_level=ACASAlertLevel.TRAFFIC_ADVISORY,
                maneuver=AvoidanceManeuver.MAINTAIN,
                critical_threat_id=critical.rakip_id,
                details=f"Trafik Uyarısı: İHA #{critical.rakip_id} mesafe {critical.current_distance_m}m (tau: {critical.time_to_cpa_s}s)"
            )
            
        # RESOLUTION ADVISORY (RA) - Acil Kaçınma Kararı!
        logger.warning(
            f"[ACAS] RESOLUTION ADVISORY! Rakip #{critical.rakip_id} | "
            f"CPA={critical.cpa_distance_m}m, Tau={critical.time_to_cpa_s}s"
        )
        
        current_alt = own_telemetry.IHA_irtifa
        current_heading = own_telemetry.IHA_yonelme
        
        # 1. Dikey Kaçınma Stratejisi
        # Eğer rakip bizim üstümüzde ise ALÇAL, altımızda ise TIRMAN
        target_alt = current_alt
        vertical_maneuver = AvoidanceManeuver.MAINTAIN
        
        if critical.alt_difference_m >= 0: # Rakip üstümüzde veya aynı seviyede
            if current_alt - self.vert_sep >= self.min_alt:
                target_alt = current_alt - self.vert_sep
                vertical_maneuver = AvoidanceManeuver.DESCEND
            else:
                target_alt = min(self.max_alt, current_alt + self.vert_sep)
                vertical_maneuver = AvoidanceManeuver.CLIMB
        else: # Rakip altımızda
            if current_alt + self.vert_sep <= self.max_alt:
                target_alt = current_alt + self.vert_sep
                vertical_maneuver = AvoidanceManeuver.CLIMB
            else:
                target_alt = max(self.min_alt, current_alt - self.vert_sep)
                vertical_maneuver = AvoidanceManeuver.DESCEND

        # 2. Yatay Kaçınma Stratejisi (Bearing'e göre ters yöne kır)
        # Bize göre rakip sağda mı solda mı?
        rel_bearing = (critical.bearing_deg - current_heading + 180.0) % 360.0 - 180.0
        if rel_bearing >= 0: # Rakip sağda -> Sola kaç
            target_heading = (current_heading - self.horiz_deg) % 360.0
            horizontal_maneuver = AvoidanceManeuver.TURN_LEFT
        else: # Rakip solda -> Sağa kaç
            target_heading = (current_heading + self.horiz_deg) % 360.0
            horizontal_maneuver = AvoidanceManeuver.TURN_RIGHT

        return AvoidanceAdvisory(
            alert_level=ACASAlertLevel.RESOLUTION_ADVISORY,
            maneuver=AvoidanceManeuver.COORDINATED_ESCAPE,
            target_heading_deg=round(target_heading, 1),
            target_altitude_m=round(target_alt, 1),
            critical_threat_id=critical.rakip_id,
            details=(
                f"ACİL KAÇINMA (RA): İHA #{critical.rakip_id} CPA={critical.cpa_distance_m}m! "
                f"Manevra: {vertical_maneuver.value} + {horizontal_maneuver.value} | "
                f"Yeni Rota={target_heading:.1f}deg, İrtifa={target_alt:.1f}m"
            )
        )
