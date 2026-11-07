"""
AeroCombat - Elektronik Harp (EH / Electronic Warfare - EW),
Karıştırma / Aldatma Tespiti ve Karşı Tedbir (ECCM) Yönetim Modülü

Modern hava sahasında ve muharebe yarışmalarında İHA'lar yoğun GNSS karıştırması (jamming),
GNSS aldatması (spoofing), telemetri bağlantı kopması ve optik sahte hedef (flare/decoy)
tehditleriyle karşılaşır. Bu modül; sinyal anomalilerini, atalet sensörleriyle GNSS
uyumsuzluklarını ve RF link kalitesini gerçek zamanlı denetleyerek otonom karşı tedbirler üretir.
"""

import time
import math
from collections import deque
from typing import List, Tuple, Optional, Dict, Any

from core.models import EWAlertLevel, EWStatus, HedefKutusu
from core.logger import logger


class ElectronicWarfareSuite:
    """
    Tümleşik Elektronik Harp ve Karşı Tedbir (ECCM) Sistemi.
    
    Bileşenler:
      1. GNSS Anti-Spoofing / Anti-Jamming Algoritması
      2. RF Veri Bağı (Datalink) Karıştırma ve Paket Kaybı Analizörü
      3. Optik Sahte Hedef / Parlama (Decoy / Flare) Filtresi
      4. EMCON (Emisyon Kontrolü) ve Otonom Sessizlik Protokolü
    """

    EARTH_RADIUS_M: float = 6371000.0

    def __init__(
        self,
        max_physical_speed_mps: float = 55.0,
        max_physical_accel_g: float = 6.0,
        rolling_window_size: int = 25
    ):
        self.max_physical_speed = max_physical_speed_mps
        self.max_physical_accel = max_physical_accel_g * 9.80665
        self.window_size = rolling_window_size

        # GNSS Geçmiş Takibi
        self._last_gnss_time: Optional[float] = None
        self._last_lat: Optional[float] = None
        self._last_lon: Optional[float] = None
        self._last_alt: Optional[float] = None
        self._gnss_spoofed: bool = False
        self._gnss_jammed: bool = False
        self._consecutive_gnss_errors: int = 0

        # RF Telemetri & Datalink Takibi
        self._telemetry_history: deque = deque(maxlen=rolling_window_size)
        self._consecutive_crc_failures: int = 0
        self._rf_jammed: bool = False

        # Optik Hedef Geçmişi
        self._decoy_detected: bool = False

        # EMCON Durumu
        self._emcon_mode: bool = False

    @staticmethod
    def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """İki enlem/boylam noktası arasındaki küresel mesafeyi metre cinsinden hesaplar."""
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = (
            math.sin(delta_phi / 2.0) ** 2
            + math.cos(phi1) * math.cos(phi2) * (math.sin(delta_lambda / 2.0) ** 2)
        )
        c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
        return ElectronicWarfareSuite.EARTH_RADIUS_M * c

    def update_gnss_sanity(
        self,
        lat: float,
        lon: float,
        alt_m: float,
        hdop: float = 1.0,
        sat_count: int = 10,
        reported_speed_mps: float = 20.0,
        imu_speed_estimate: Optional[float] = None,
        timestamp_s: Optional[float] = None
    ) -> Tuple[bool, str]:
        """
        GNSS verisinin gerçekliğini ve güvenilirliğini denetler.
        Dönüş: (is_valid, reason)
        """
        now = timestamp_s if timestamp_s is not None else time.time()

        # 1. Uydu sayısı ve HDOP kontrolü
        if sat_count < 4:
            self._gnss_jammed = True
            self._consecutive_gnss_errors += 1
            return False, f"GNSS_JAMMING: Yetersiz uydu ({sat_count} < 4)"

        if hdop > 3.8:
            self._gnss_jammed = True
            self._consecutive_gnss_errors += 1
            return False, f"GNSS_DEGRADED: Yüksek HDOP ({hdop:.2f} > 3.8)"

        # İlk veri noktasıysa başlangıcı kaydet
        if self._last_gnss_time is None:
            self._last_gnss_time = now
            self._last_lat = lat
            self._last_lon = lon
            self._last_alt = alt_m
            self._gnss_spoofed = False
            self._gnss_jammed = False
            self._consecutive_gnss_errors = 0
            return True, "GNSS_INITIALIZED"

        dt = max(0.001, now - self._last_gnss_time)

        # 2. Fiziksel mesafe ve hız sıçraması kontrolü (Teleportasyon / Spoofing)
        dist_m = self.haversine_distance_m(self._last_lat, self._last_lon, lat, lon)
        apparent_velocity = dist_m / dt

        if apparent_velocity > self.max_physical_speed * 1.5:
            self._gnss_spoofed = True
            self._consecutive_gnss_errors += 1
            return False, f"GNSS_SPOOFING: İmkansız hız sıçraması ({apparent_velocity:.1f} m/s)"

        # 3. İrtifa sıçraması kontrolü
        d_alt = abs(alt_m - self._last_alt)
        alt_rate = d_alt / dt
        if alt_rate > 35.0:  # 35 m/s dikey hız İHA için fizik dışı
            self._gnss_spoofed = True
            self._consecutive_gnss_errors += 1
            return False, f"GNSS_SPOOFING: Ani dikey irtifa sıçraması ({alt_rate:.1f} m/s)"

        # 4. IMU Ataletsel Hız ile GNSS Hız Karşılaştırması
        if imu_speed_estimate is not None:
            diff = abs(reported_speed_mps - imu_speed_estimate)
            if diff > 18.0:
                self._gnss_spoofed = True
                self._consecutive_gnss_errors += 1
                return False, f"GNSS_SPOOFING: GNSS/IMU hız çelişkisi ({diff:.1f} m/s fark)"

        # Veri güvenli; referansı güncelle
        self._last_gnss_time = now
        self._last_lat = lat
        self._last_lon = lon
        self._last_alt = alt_m
        self._gnss_spoofed = False
        self._gnss_jammed = False
        self._consecutive_gnss_errors = max(0, self._consecutive_gnss_errors - 1)
        return True, "GNSS_SECURE"

    def record_telemetry_packet(
        self,
        success: bool,
        latency_ms: float = 50.0,
        rssi_dbm: float = -65.0,
        crc_valid: bool = True
    ) -> None:
        """
        Gelen/giden telemetri paketinin RF ve iletişim metriklerini kaydeder.
        """
        if not crc_valid:
            self._consecutive_crc_failures += 1
        else:
            self._consecutive_crc_failures = 0

        self._telemetry_history.append({
            "success": success,
            "latency_ms": latency_ms,
            "rssi_dbm": rssi_dbm,
            "crc_valid": crc_valid,
            "time": time.time()
        })

        # RF karıştırma analizi: arka arkaya 3 CRC hatası veya son paketlerde %35 üzeri kayıp
        if self._consecutive_crc_failures >= 3:
            self._rf_jammed = True
        elif len(self._telemetry_history) >= 5:
            failures = sum(1 for p in self._telemetry_history if not p["success"] or not p["crc_valid"])
            loss_ratio = failures / float(len(self._telemetry_history))
            self._rf_jammed = (loss_ratio >= 0.35)
        else:
            self._rf_jammed = False

    def filter_visual_decoys(
        self,
        detected_boxes: List[HedefKutusu],
        active_target: Optional[HedefKutusu] = None,
        dt: float = 0.033
    ) -> List[HedefKutusu]:
        """
        Sahte hedef / flare / yanıltıcı parlamaları filtreler.
        Gerçek İHA'lar aerodinamik sınırlamalara tabidir; aniden > 12G ivmeyle beliren
        veya aşırı derecede genişleyen/parlayan sahte kutular elenir.
        """
        if not detected_boxes:
            self._decoy_detected = False
            return []

        dt = max(0.005, dt)
        valid_targets = []
        decoy_found = False

        for box in detected_boxes:
            # En/boy oranı mantık kontrolü (Uçak en-boy oranı aşırı uç noktalarda olamaz)
            w = box.genislik
            h = box.yukseklik
            if w <= 2 or h <= 2:
                continue

            aspect_ratio = w / float(h)
            if aspect_ratio < 0.15 or aspect_ratio > 6.0:
                decoy_found = True
                continue

            # Aktif hedef takip ediliyorsa, hedef kutusundaki ani sıçramayı test et
            if active_target is not None and box.track_id == active_target.track_id:
                disp_px = math.hypot(box.merkez_x - active_target.merkez_x, box.merkez_y - active_target.merkez_y)
                px_speed = disp_px / dt
                # 720p ekranda 1 saniyede 3000 piksel atlama fizik dışı yanıltmadır
                if px_speed > 3200.0:
                    decoy_found = True
                    continue

            valid_targets.append(box)

        self._decoy_detected = decoy_found
        return valid_targets

    def set_emcon(self, active: bool) -> None:
        """Emisyon Kontrolü (EMCON - Emission Control) modunu açar/kapatır."""
        self._emcon_mode = active
        if active:
            logger.warning("[EW] EMCON PROTOKOLÜ AKTİF: Telsiz sessizliği başlatıldı.")
        else:
            logger.info("[EW] EMCON DEVRE DIŞI: Standart RF yayınına dönüldü.")

    def get_status(self) -> EWStatus:
        """Mevcut Elektronik Harp tehdit seviyesini ve tavsiye edilen eylemi döndürür."""
        if self._emcon_mode:
            level = EWAlertLevel.EMCON
            action = "EMCON_SILENT_FLIGHT_DEAD_RECKONING"
            quality = 0.2
        elif self._gnss_spoofed or (self._gnss_jammed and self._rf_jammed):
            level = EWAlertLevel.CRITICAL_JAMMING
            action = "FALLBACK_GNSS_DENIED_INS_VO"
            quality = 0.1
        elif self._gnss_jammed or self._rf_jammed:
            level = EWAlertLevel.THREAT
            action = "SWITCH_OPTICAL_ODOMETRY_AND_FREQ_HOPPING"
            quality = 0.45
        elif self._decoy_detected or self._consecutive_crc_failures > 0:
            level = EWAlertLevel.CAUTION
            action = "REJECT_DECOYS_AND_STABILIZE_TRACK"
            quality = 0.75
        else:
            level = EWAlertLevel.NORMAL
            action = "STANDART_SEYRUSEFER"
            quality = 1.0

        return EWStatus(
            tehdit_seviyesi=level,
            gnss_aldatma_tespiti=self._gnss_spoofed,
            rf_karistirma_tespiti=self._rf_jammed,
            optik_sahte_hedef_tespiti=self._decoy_detected,
            emcon_aktif=self._emcon_mode,
            sinyal_kalite_skoru=quality,
            onerilen_eylem=action
        )
