"""
GNSS-Denied / Anti-Jamming & Anti-Spoofing Navigasyon Modülü.
Elektronik harp (karıştırma/aldatma), GPS kesintisi veya tünel/hangar çevresi sinyal kayıplarında
Parakete Seyrüseferi (Dead Reckoning) ve Kalman Filtresi ile güvenli konumu sürdürür.
"""

import math
import time
from enum import Enum
from dataclasses import dataclass
from typing import Tuple, Optional, Dict, Any, List
from core.logger import logger
from core.event_bus import bus


class GNSSStatus(Enum):
    """GNSS/GPS Sağlık ve Güvenlik Durumu."""
    NOMINAL = "NOMINAL"           # Sağlıklı GPS sinyali
    DEGRADED = "DEGRADED"         # Yüksek HDOP, düşük uydu sayısı
    JAMMED = "JAMMED"             # Tam sinyal kaybı (Karıştırma)
    SPOOFED = "SPOOFED"           # Koordinat ışınlanması / Hız uyumsuzluğu (Aldatma)
    DEAD_RECKONING = "DEAD_RECKONING" # GNSS devre dışı, ataletsel yedeklemede


@dataclass
class GNSSSample:
    """Anlık GNSS sensör verisi."""
    lat: float
    lon: float
    alt: float
    speed_mps: float
    heading_deg: float
    hdop: float = 1.0
    satellites: int = 12
    timestamp: float = 0.0


class GNSSDeniedNavigator:
    """
    GPS Sinyal Doğrulama, Karıştırma/Aldatma Tespiti ve Ataletsel Parakete (Dead Reckoning) Motoru.
    """
    def __init__(
        self,
        max_position_jump_m: float = 40.0,
        max_speed_discrepancy_mps: float = 15.0,
        max_hdop_threshold: float = 3.5,
        min_satellites_threshold: int = 5,
        dr_drift_rate_mps: float = 0.5  # Tahmini rüzgar belirsizliği sürüklenme oranı
    ):
        self.max_jump_m = max_position_jump_m
        self.max_speed_diff = max_speed_discrepancy_mps
        self.max_hdop = max_hdop_threshold
        self.min_sats = min_satellites_threshold
        self.dr_drift_rate = dr_drift_rate_mps

        self.status = GNSSStatus.NOMINAL
        self.last_valid_sample: Optional[GNSSSample] = None
        
        # Dead Reckoning Durum Değişkenleri (Metre cinsinden yerel ofsetler: NED)
        self.est_lat: float = 0.0
        self.est_lon: float = 0.0
        self.est_alt: float = 0.0
        self.est_speed: float = 0.0
        self.est_heading: float = 0.0
        
        self.last_update_ts: float = 0.0
        self.denied_duration_s: float = 0.0
        self.consecutive_invalid_count: int = 0
        self.recovery_stable_count: int = 0

    def update(
        self,
        gnss: Optional[GNSSSample],
        airspeed_mps: float,
        heading_deg: float,
        pitch_deg: float = 0.0,
        wind_north_mps: float = 0.0,
        wind_east_mps: float = 0.0,
        dt: Optional[float] = None
    ) -> Tuple[float, float, float, GNSSStatus]:
        """
        Sensör verilerini işler, GPS güvenilirliğini denetler ve tahmini (enlem, boylam, irtifa) döndürür.
        """
        now = gnss.timestamp if (gnss and gnss.timestamp > 0) else time.time()
        step_dt = dt if dt is not None else (max(0.001, now - self.last_update_ts) if self.last_update_ts > 0 else 0.05)
        self.last_update_ts = now

        # 1. GNSS Örneğini Doğrula (Spoofing & Jamming Kontrolü)
        is_gnss_valid = self._validate_gnss(gnss, airspeed_mps, heading_deg, step_dt)

        if is_gnss_valid and gnss is not None:
            self.recovery_stable_count += 1
            if self.recovery_stable_count >= 5:  # 5 ardışık geçerli örnekte tam nominale dön
                if self.status != GNSSStatus.NOMINAL:
                    logger.info("[AntiJamming] GNSS sinyali doğrulandı ve kurtarıldı. NOMINAL moda geçildi.")
                    bus.emit("GNSS_STATUS_CHANGE", status=GNSSStatus.NOMINAL.value)
                self.status = GNSSStatus.NOMINAL
                self.denied_duration_s = 0.0
                self.consecutive_invalid_count = 0
            
            # Konum güncellemesi
            self.est_lat = gnss.lat
            self.est_lon = gnss.lon
            self.est_alt = gnss.alt
            self.est_speed = gnss.speed_mps
            self.est_heading = gnss.heading_deg
            self.last_valid_sample = gnss
        else:
            # GPS Geçersiz -> Dead Reckoning (DR) Devrede!
            self.recovery_stable_count = 0
            self.consecutive_invalid_count += 1
            self.denied_duration_s += step_dt
            
            if self.status == GNSSStatus.NOMINAL:
                if gnss is None or gnss.satellites < self.min_sats or gnss.hdop > self.max_hdop:
                    self.status = GNSSStatus.JAMMED
                    logger.warning(f"[AntiJamming] GNSS Karıştırma / Sinyal Kaybı Algılandı! (JAMMED, {self.denied_duration_s:.1f}s)")
                else:
                    self.status = GNSSStatus.SPOOFED
                    logger.warning(f"[AntiJamming] GNSS Aldatma / Spoofing Şüphesi! (SPOOFED)")
                bus.emit("GNSS_STATUS_CHANGE", status=self.status.value)
            
            self._propagate_dead_reckoning(
                airspeed_mps=airspeed_mps,
                heading_deg=heading_deg,
                pitch_deg=pitch_deg,
                wind_north_mps=wind_north_mps,
                wind_east_mps=wind_east_mps,
                dt=step_dt
            )

        return self.est_lat, self.est_lon, self.est_alt, self.status

    def _validate_gnss(
        self,
        gnss: Optional[GNSSSample],
        airspeed_mps: float,
        heading_deg: float,
        dt: float
    ) -> bool:
        """GPS verisinin fiziksel olarak tutarlı olup olmadığını (Spoofing/Jamming) denetler."""
        if gnss is None:
            return False

        # Temel sinyal kalite filtreleri
        if gnss.satellites < self.min_sats or gnss.hdop > self.max_hdop:
            return False

        # İlk örnek ise kabul et
        if self.last_valid_sample is None:
            return True

        # Mesafe sıçraması (Position Jump) kontrolü
        d_lat = gnss.lat - self.last_valid_sample.lat
        d_lon = gnss.lon - self.last_valid_sample.lon
        d_north = d_lat * 111139.0
        d_east = d_lon * (111139.0 * math.cos(math.radians(gnss.lat)))
        dist_jump_m = math.sqrt(d_north ** 2 + d_east ** 2)

        # Beklenen maksimum yer değiştirme (Maks hız 40 m/s varsayımı)
        max_possible_dist = max(5.0, (airspeed_mps + 25.0) * dt + self.max_jump_m)
        if dist_jump_m > max_possible_dist:
            logger.warning(f"[AntiJamming] Anormal konum sıçraması: {dist_jump_m:.1f}m > limit {max_possible_dist:.1f}m!")
            return False

        # Hız tutarlılık testi (Hava hızı ile GPS yer hızı karşılaştırması)
        # 15 m/s'den fazla rüzgar hariç devasa hız farkı spoofing işaretidir
        speed_diff = abs(gnss.speed_mps - airspeed_mps)
        if speed_diff > self.max_speed_diff and airspeed_mps > 10.0:
            logger.warning(f"[AntiJamming] Hız tutarsızlığı: GPS={gnss.speed_mps:.1f} m/s, Airspeed={airspeed_mps:.1f} m/s!")
            return False

        return True

    def _propagate_dead_reckoning(
        self,
        airspeed_mps: float,
        heading_deg: float,
        pitch_deg: float,
        wind_north_mps: float,
        wind_east_mps: float,
        dt: float
    ) -> None:
        """Pusula yönelimi, hava sürati ve rüzgar tahmini ile koordinat ilerletme (Dead Reckoning)."""
        hdg_rad = math.radians(heading_deg)
        pitch_rad = math.radians(pitch_deg)

        # Uçağın havaya göre hız bileşenleri
        v_air_h = airspeed_mps * math.cos(pitch_rad)
        v_air_north = v_air_h * math.cos(hdg_rad)
        v_air_east = v_air_h * math.sin(hdg_rad)
        v_air_down = -airspeed_mps * math.sin(pitch_rad)

        # Yere göre hız bileşenleri (Hava sürati + Rüzgar)
        v_ground_north = v_air_north + wind_north_mps
        v_ground_east = v_air_east + wind_east_mps

        # Metre cinsinden yer değiştirme
        delta_north_m = v_ground_north * dt
        delta_east_m = v_ground_east * dt
        delta_alt_m = -v_air_down * dt

        # WGS84 koordinat integrasyonu
        meters_per_lat = 111139.0
        meters_per_lon = 111139.0 * math.cos(math.radians(self.est_lat if self.est_lat != 0 else 41.0))
        
        self.est_lat += (delta_north_m / meters_per_lat)
        self.est_lon += (delta_east_m / max(1.0, meters_per_lon))
        self.est_alt += delta_alt_m
        
        self.est_speed = math.sqrt(v_ground_north ** 2 + v_ground_east ** 2)
        self.est_heading = heading_deg

    def get_estimated_uncertainty_m(self) -> float:
        """GPS kesintisi boyunca biriken tahmini konum belirsizliği yarıçapını (metre) döndürür."""
        if self.status == GNSSStatus.NOMINAL:
            return 1.5
        return round(1.5 + (self.dr_drift_rate * self.denied_duration_s), 1)
