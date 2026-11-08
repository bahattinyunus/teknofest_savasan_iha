"""
AeroCombat - Taktiksel Tehdit Sınıflandırıcı ve RWR (Radar Warning Receiver) Erken Uyarı Motoru.

Görüntüleme ve kinematik takip verilerinden:
1. Hedef Hava Aracı Tipini Sınıflandırma (Sabit Kanat vs Döner Kanat)
   - Bounding box en-boy oranı (aspect ratio w/h)
   - Doğrusal hız ve açısal dönüş hızı profili
2. Tehdit Seviyesi ve RWR (Radar Warning Receiver) Erken Uyarısı:
   - Düşman burnunun bizim arkamıza kilitlenip kilitlenmediğini hesaplar.
   - RWR Uyarı Durumları: SEARCH (Tarama), TRACK (İzleme), LOCK_WARNING (Kilitlenme Uyarısı!)
   - Önerilen Kaçış Vektörü (Break Turn Azimuth) üretir.
"""

import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Tuple, Optional
import numpy as np

from core.models import HedefKutusu
from core.threat_library import AirframeType, ThreatLevel, THREAT_LIBRARY, ThreatProfile


class RWRStatus(Enum):
    CLEAR = "CLEAR"               # Tehdit yok, arka sektör temiz
    SEARCH = "SEARCH"             # Düşman menzilde ancak bize yönelmemiş
    TRACK = "TRACK"               # Düşman bize doğru manevra yapıyor
    LOCK_WARNING = "LOCK_WARNING" # Düşman arkamızda ve WEZ konisinde kilitlenmek üzere!


@dataclass
class ThreatAssessment:
    """Belirli bir hedefin tehdit değerlendirme sonucu."""
    target_id: int
    airframe_type: AirframeType
    confidence: float
    threat_level: ThreatLevel
    rwr_status: RWRStatus
    threat_score: float           # [0.0 - 1.0]
    evasive_break_dir: str        # "LEFT", "RIGHT", "NONE"
    recommended_turn_deg: float   # Kaçış baş açısı


class ThreatClassifierRWR:
    """
    Hedef Tehdit Sınıflandırıcı ve Radar Warning Receiver Sistemi.
    """

    def __init__(self, lock_threat_time_threshold_s: float = 1.2):
        self.lock_threat_threshold = lock_threat_time_threshold_s
        self._target_history: Dict[int, List[Tuple[float, float, float]]] = {}  # id -> [(t, x, y), ...]
        self._lock_threat_timers: Dict[int, float] = {}  # id -> ilk kilit tehdidi tespit zamanı

    def classify_target(self,
                        target: HedefKutusu,
                        estimated_speed_mps: float = 20.0,
                        turn_rate_dps: float = 0.0) -> Tuple[AirframeType, float]:
        """
        Kamera tespiti ve kinematikten hava platformu tipini kestirir.
        """
        w = max(1.0, float(target.genislik))
        h = max(1.0, float(target.yukseklik))
        ratio = w / h

        # Sabit kanatlı uçaklar önden/arkadan geniş, ince görünür (w/h >= 1.6)
        if ratio >= 1.6:
            prob_fixed = min(0.95, 0.5 + (ratio - 1.6) * 0.25)
            return AirframeType.FIXED_WING_FIGHTER, prob_fixed

        # Döner kanatlılar (drone) genellikle kareye yakın kutu verir (0.8 <= w/h <= 1.4)
        if 0.7 <= ratio <= 1.4:
            # Hız da düşükse (< 18 m/s) döner kanat olasılığı çok yüksektir
            speed_factor = 0.2 if estimated_speed_mps < 18.0 else 0.0
            prob_rotary = min(0.92, 0.65 + speed_factor)
            return AirframeType.ROTARY_WING_KAMIKAZE, prob_rotary

        # Çok küçük veya aşırı hızlı hareketler sahte hedef (flare/decoy) olabilir
        norm_area = (target.genislik * target.yukseklik) / (1280.0 * 720.0)
        if norm_area < 0.005 and estimated_speed_mps > 35.0:
            return AirframeType.OPTICAL_DECOY, 0.85


        return AirframeType.SURVEILLANCE_GLIDER, 0.60

    def evaluate_threat(self,
                        target_id: int,
                        airframe_type: AirframeType,
                        range_m: float,
                        ata_deg: float,
                        aspect_angle_deg: float,
                        closure_rate_mps: float = 0.0,
                        dt: float = 0.05) -> ThreatAssessment:
        """
        Kendi İHA'mıza göre tehdit seviyesini ve RWR durumunu hesaplar.
        ata_deg: Bizim burnumuzun hedefe olan açısı.
        aspect_angle_deg: Hedefin arkasına olan açı.
        Eğer aspect_angle_deg > 135°, hedef arkamızda ve burnu bize dönüktür!
        """
        now = time.time()
        profile = THREAT_LIBRARY.get(airframe_type, THREAT_LIBRARY[AirframeType.FIXED_WING_FIGHTER])

        # RWR Kilitlenme Tehlikesi Hesaplama
        # Düşman arkamızdaysa (aspect_angle > 130°) ve menzil WEZ içinde (< profile.wez_lock_range_m)
        is_in_enemy_wez = (aspect_angle_deg > 130.0) and (range_m <= profile.wez_lock_range_m)

        if is_in_enemy_wez:
            if target_id not in self._lock_threat_timers:
                self._lock_threat_timers[target_id] = now

            duration_in_wez = now - self._lock_threat_timers[target_id]

            if duration_in_wez >= self.lock_threat_threshold:
                rwr_status = RWRStatus.LOCK_WARNING
                threat_level = ThreatLevel.CRITICAL
                threat_score = 0.98
            else:
                rwr_status = RWRStatus.TRACK
                threat_level = ThreatLevel.HIGH
                threat_score = 0.75 + (duration_in_wez / self.lock_threat_threshold) * 0.2
        else:
            self._lock_threat_timers.pop(target_id, None)
            if range_m < profile.wez_lock_range_m * 1.5:
                rwr_status = RWRStatus.SEARCH
                threat_level = ThreatLevel.MEDIUM
                threat_score = 0.45
            else:
                rwr_status = RWRStatus.CLEAR
                threat_level = ThreatLevel.LOW
                threat_score = 0.15

        # Kaçış Yönü Belirleme
        # Hedef arkamızdaysa en keskin dönüş (Break turn) sol veya sağ 90 derecedir
        evasive_dir = "LEFT" if (target_id % 2 == 0) else "RIGHT"
        turn_angle = -90.0 if evasive_dir == "LEFT" else 90.0

        return ThreatAssessment(
            target_id=target_id,
            airframe_type=airframe_type,
            confidence=0.88,
            threat_level=threat_level,
            rwr_status=rwr_status,
            threat_score=round(threat_score, 2),
            evasive_break_dir=evasive_dir,
            recommended_turn_deg=turn_angle
        )
