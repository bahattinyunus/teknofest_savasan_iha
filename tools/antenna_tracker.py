import math
import time
from typing import Tuple, Dict, Any, Optional
from core.models import TelemetriPaketi
from core.logger import logger


class GroundAntennaTracker:
    """Yer İstasyonu Yönlü Anten Takipçisi (Antenna Tracker - AAT).
    
    Yarışma esnasında 5.8 GHz yüksek kazançlı yönlü yagi/patch video antenini
    ve 868/915 MHz telemetri antenini uçağın anlık GPS koordinatlarına yönelterek
    görüntü donmasını ve telemetri kopmalarını engeller.
    
    Hesaplamalar:
    - Azimuth (Yatay Yönelim Açısı / Bearing): 0° - 360° (Kuzey referanslı)
    - Elevation (Dikey Yükseliş Açısı): 0° - 90° (Ufuk referanslı)
    - Eğimli Mesafe (Slant Range): 3D Öklid mesafesi
    """

    def __init__(
        self,
        home_lat: float = 41.1000,
        home_lon: float = 28.9000,
        home_alt_m: float = 40.0,
        min_elevation_deg: float = 0.0,
        max_elevation_deg: float = 85.0
    ):
        self.home_lat = home_lat
        self.home_lon = home_lon
        self.home_alt_m = home_alt_m
        self.min_elevation_deg = min_elevation_deg
        self.max_elevation_deg = max_elevation_deg

        self.current_azimuth_deg: float = 0.0
        self.current_elevation_deg: float = 0.0
        self.slant_range_m: float = 0.0
        self.last_update_time: float = time.time()

    def set_home_position(self, lat: float, lon: float, alt_m: float):
        """Yer anteninin GPS koordinatlarını günceller."""
        self.home_lat = lat
        self.home_lon = lon
        self.home_alt_m = alt_m
        logger.info(f"Anten Takipçisi Home Konumu Ayarlandı -> Lat: {lat:.6f}, Lon: {lon:.6f}, Alt: {alt_m:.1f}m")

    def calculate_tracking_angles(
        self,
        uav_lat: float,
        uav_lon: float,
        uav_alt_m: float
    ) -> Tuple[float, float, float]:
        """İHA'nın koordinatlarına göre Azimuth, Elevation ve 3D Mesafe hesaplar."""
        # 1. Yatay Mesafe ve Rota Açısı (Haversine & Forward Azimuth)
        lat1 = math.radians(self.home_lat)
        lon1 = math.radians(self.home_lon)
        lat2 = math.radians(uav_lat)
        lon2 = math.radians(uav_lon)

        d_lat = lat2 - lat1
        d_lon = lon2 - lon1

        # Haversine formülü ile küresel yer mesafesi (Ground distance)
        R_earth = 6371000.0  # metre
        a = math.sin(d_lat / 2.0)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2.0)**2
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
        ground_distance_m = R_earth * c

        # Azimuth / Bearing formülü
        y = math.sin(d_lon) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(d_lon)
        azimuth_rad = math.atan2(y, x)
        azimuth_deg = (math.degrees(azimuth_rad) + 360.0) % 360.0

        # 2. İrtifa Farkı ve Yükseliş Açısı (Elevation)
        alt_diff_m = uav_alt_m - self.home_alt_m
        
        # Dünya eğriliği düzeltmesi (yaklaşık: d^2 / (2 * R_earth))
        curvature_correction_m = (ground_distance_m**2) / (2.0 * R_earth)
        effective_alt_diff = alt_diff_m - curvature_correction_m

        elevation_rad = math.atan2(effective_alt_diff, max(1.0, ground_distance_m))
        elevation_deg = math.degrees(elevation_rad)

        # Elevation limitleri
        elevation_deg = max(self.min_elevation_deg, min(self.max_elevation_deg, elevation_deg))

        # 3. 3D Eğimli Mesafe (Slant Range)
        slant_range_m = math.hypot(ground_distance_m, effective_alt_diff)

        self.current_azimuth_deg = round(azimuth_deg, 2)
        self.current_elevation_deg = round(elevation_deg, 2)
        self.slant_range_m = round(slant_range_m, 1)
        self.last_update_time = time.time()

        return self.current_azimuth_deg, self.current_elevation_deg, self.slant_range_m

    def update_from_telemetry(self, tel: TelemetriPaketi) -> Tuple[float, float, float]:
        """Gelen TelemetriPaketi üzerinden anten açılarını anında günceller."""
        return self.calculate_tracking_angles(tel.IHA_enlem, tel.IHA_boylam, tel.IHA_irtifa)

    def get_servo_pwm(
        self,
        azimuth_servo_range: Tuple[int, int] = (1000, 2000),
        elevation_servo_range: Tuple[int, int] = (1000, 2000)
    ) -> Tuple[int, int]:
        """Pan/Tilt mekanik servoları için standart PWM (mikrosaniye: 1000-2000) değerlerini döner."""
        # Azimuth: 0-360 derece -> 1000 - 2000 us (veya 180 derece servolar için orantılı)
        az_ratio = (self.current_azimuth_deg % 360.0) / 360.0
        az_pwm = int(azimuth_servo_range[0] + az_ratio * (azimuth_servo_range[1] - azimuth_servo_range[0]))

        # Elevation: 0-90 derece -> 1000 - 2000 us
        el_ratio = max(0.0, min(1.0, self.current_elevation_deg / 90.0))
        el_pwm = int(elevation_servo_range[0] + el_ratio * (elevation_servo_range[1] - elevation_servo_range[0]))

        return az_pwm, el_pwm
