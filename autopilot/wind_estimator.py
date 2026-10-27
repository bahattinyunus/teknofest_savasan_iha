import math
import time
from typing import Tuple, Optional
from core.models import TelemetriPaketi
from core.logger import logger


class WindEstimator:
    """Sabit kanatlı İHA için rüzgar hızı ve yönü tahmin edicisi (Wind Triangle Estimation).
    
    Uçuş sırasında rüzgar etkisiyle oluşan sürüklenmeyi (Drift / Crab Angle)
    hesaplayarak güdüm algoritmalarının hedefi tam yakalamasını sağlar.
    
    V_ground = V_air + V_wind
    """

    def __init__(self, filter_gain: float = 0.05):
        self.filter_gain = filter_gain
        self.wind_north_m_s: float = 0.0
        self.wind_east_m_s: float = 0.0
        self.estimated_airspeed_m_s: float = 18.0
        self.last_time: float = time.time()

    def update(
        self,
        groundspeed_m_s: float,
        course_over_ground_deg: float,
        heading_deg: float,
        true_airspeed_m_s: Optional[float] = None
    ) -> Tuple[float, float, float]:
        """Yer hızı, yer izi rotası ve pusula yöneliminden anlık rüzgar vektörünü hesaplar."""
        now = time.time()
        dt = max(1e-3, now - self.last_time)
        self.last_time = now

        # Yer hızı vektörü (Kuzey, Doğu)
        cog_rad = math.radians(course_over_ground_deg)
        vg_north = groundspeed_m_s * math.cos(cog_rad)
        vg_east = groundspeed_m_s * math.sin(cog_rad)

        # Hava hızı (pitot tüpü yoksa tahmini kullanılır)
        tas = true_airspeed_m_s if true_airspeed_m_s is not None else self.estimated_airspeed_m_s
        hdg_rad = math.radians(heading_deg)
        va_north = tas * math.cos(hdg_rad)
        va_east = tas * math.sin(hdg_rad)

        # Rüzgar vektörü: V_wind = V_ground - V_air
        measured_wind_north = vg_north - va_north
        measured_wind_east = vg_east - va_east

        # Düşük geçiren filtre (Low-pass filter) ile yumuşatma
        self.wind_north_m_s += self.filter_gain * (measured_wind_north - self.wind_north_m_s)
        self.wind_east_m_s += self.filter_gain * (measured_wind_east - self.wind_east_m_s)

        # Toplam rüzgar şiddeti ve yönü (Rüzgarın geldiği yön)
        wind_speed = math.hypot(self.wind_north_m_s, self.wind_east_m_s)
        wind_from_dir = (math.degrees(math.atan2(-self.wind_east_m_s, -self.wind_north_m_s)) + 360.0) % 360.0

        # Rüzgar düzeltme açısı (Crab Angle / Drift Angle)
        # sin(crab) = (V_wind_cross) / V_air
        wind_rel_angle = math.radians(wind_from_dir - course_over_ground_deg)
        crosswind = wind_speed * math.sin(wind_rel_angle)
        
        crab_ratio = max(-0.99, min(0.99, crosswind / max(1.0, tas)))
        crab_angle_deg = math.degrees(math.asin(crab_ratio))

        return wind_speed, wind_from_dir, crab_angle_deg

    def apply_crab_compensation(self, desired_heading_deg: float, groundspeed: float, heading: float) -> float:
        """Güdüm rotasına rüzgar sürüklenme açısını ekleyerek düzeltilmiş rota üretir."""
        w_speed, _, crab_angle = self.update(groundspeed, desired_heading_deg, heading)
        # Rüzgara karşı burnu hafifçe rüzgar yönüne kır (Crab angle)
        compensated_heading = (desired_heading_deg + crab_angle + 360.0) % 360.0
        return compensated_heading
