import math
import time
from enum import Enum
from typing import Tuple, Optional, List, Dict
import numpy as np

from core.models import TelemetriPaketi, RakipIHABilgisi, KilitDurumu
from core.logger import logger
from .bfm_maneuvers import BFMEvasiveTactics, ManevraTipi
from .guidance import GuidanceController


class TacticalState(Enum):
    """Hava muharebesi taktiksel durum fazları (NATO BFM Standartları)."""
    PATROL = "PATROL"                     # Hedef aranıyor / devriye uçuşu
    OFFENSIVE_PURSUIT = "OFFENSIVE_PURSUIT" # Rakibin arkasındayız, önleme güdümü aktif
    OFFENSIVE_WEZ = "OFFENSIVE_WEZ"       # Kilit menzilinde (Weapons Employment Zone) kilitlenme takibi
    DEFENSIVE_EVASION = "DEFENSIVE_EVASION"# Rakip arkamızda, kilitlenmeyi bozma manevrası
    HEAD_ON_MERGE = "HEAD_ON_MERGE"       # Burun buruna karşılaşma (Lead turn manevrası)
    DISENGAGE = "DISENGAGE"               # Düşük batarya veya sınır ihlali -> Güvenli eve dönüş


class TacticalDecisionAgent:
    """DARPA AlphaDogfight ve BFM standartlarında taktiksel hava muharebe karar ajanı.
    
    4 temel geometri metriğini sürekli hesaplar:
    - ATA (Antenna Train Angle / Boresight Açısı): Kendi burnumuz ile hedef görüş hattı (LOS) arasındaki açı.
    - AA (Aspect Angle): Hedefin kuyruk vektörü ile bize olan görüş hattı arasındaki açı.
    - R (Range): Hedefe olan 3D Öklid mesafesi.
    - Vc (Closing Velocity): Hedefe yaklaşma hızı (-dR/dt).
    """

    def __init__(
        self,
        wez_range_max_m: float = 120.0,
        wez_ata_max_deg: float = 30.0,
        wez_aa_max_deg: float = 60.0,
        threat_range_m: float = 120.0
    ):
        self.wez_range_max_m = wez_range_max_m
        self.wez_ata_max_deg = wez_ata_max_deg
        self.wez_aa_max_deg = wez_aa_max_deg
        self.threat_range_m = threat_range_m

        self.state = TacticalState.PATROL
        self.guidance = GuidanceController(method="proportional_navigation")
        self.evasion = BFMEvasiveTactics()
        self.last_range: Optional[float] = None
        self.last_time: float = time.time()

    def compute_combat_geometry(
        self,
        own_tel: TelemetriPaketi,
        rival: RakipIHABilgisi
    ) -> Dict[str, float]:
        """İki uçak arasındaki göreceli BFM geometrisini (Range, ATA, Aspect Angle, Vc) hesaplar."""
        now = time.time()
        dt = max(1e-3, now - self.last_time)

        # 1. 3D Mesafe (Range)
        lat_m = (rival.IHA_enlem - own_tel.IHA_enlem) * 111139.0
        lon_m = (rival.IHA_boylam - own_tel.IHA_boylam) * 111139.0 * math.cos(math.radians(own_tel.IHA_enlem))
        alt_m = rival.IHA_irtifa - own_tel.IHA_irtifa
        r_3d = math.sqrt(lat_m**2 + lon_m**2 + alt_m**2)

        # 2. Yaklaşma Hızı (Closing Velocity: Vc = -dR/dt)
        vc = 0.0
        if self.last_range is not None:
            vc = -(r_3d - self.last_range) / dt
        self.last_range = r_3d
        self.last_time = now

        # 3. Görüş Hattı Açısı (LOS Bearing from own to rival)
        los_bearing_deg = (math.degrees(math.atan2(lon_m, lat_m)) + 360.0) % 360.0

        # 4. ATA (Antenna Train Angle): Kendi yönelimimiz ile hedef görüş hattı arasındaki açı (0 - 180 deg)
        own_hdg = own_tel.IHA_yonelme
        ata_deg = abs((los_bearing_deg - own_hdg + 180.0) % 360.0 - 180.0)

        # 5. Aspect Angle (AA): Hedefin uçuş vektörü ile bize olan görüş hattı arasındaki açı
        # Hedefin arkasındaysak (aynı yöne uçuyorsak) AA ~ 0 deg (Tail aspect)
        # Burun burunaysak (karşıdan geliyorsa) AA ~ 180 deg (Head-on)
        aa_deg = abs((los_bearing_deg - rival.IHA_yonelme + 180.0) % 360.0 - 180.0)

        return {
            "range_m": r_3d,
            "closing_velocity_m_s": vc,
            "ata_deg": ata_deg,
            "aspect_angle_deg": aa_deg,
            "los_bearing_deg": los_bearing_deg
        }

    def evaluate_tactics(
        self,
        own_tel: TelemetriPaketi,
        rivals: List[RakipIHABilgisi],
        lock_status: KilitDurumu = KilitDurumu.IDLE
    ) -> Tuple[TacticalState, float, float, float]:
        """Taktiksel duruma göre (Roll, Pitch, Heading) komutları üretir."""
        # Batarya veya güvenlik acil durumu
        if own_tel.IHA_batarya < 15:
            self.state = TacticalState.DISENGAGE
            return self.state, 0.0, 5.0, own_tel.IHA_yonelme

        # 1. Arkamızdaki Tehdit Kontrolü (Defensive Check)
        threat = self.evasion.evaluate_threat(own_tel, rivals)
        if threat is not None and lock_status != KilitDurumu.LOCKED:
            self.state = TacticalState.DEFENSIVE_EVASION
            _, roll, pitch, heading = self.evasion.execute_evasion(own_tel, threat)
            return self.state, roll, pitch, heading

        # 2. Eğer hedef yoksa devriye modu
        if not rivals:
            self.state = TacticalState.PATROL
            return self.state, 0.0, 0.0, own_tel.IHA_yonelme

        # En yakın veya en tehditkar rakibi seç
        primary_rival = rivals[0]
        geom = self.compute_combat_geometry(own_tel, primary_rival)

        r_3d = geom["range_m"]
        ata = geom["ata_deg"]
        aa = geom["aspect_angle_deg"]

        # 3. Kilitlenme Bölgesi (Offensive WEZ): Hedef önümüzde ve arkasındayız
        if r_3d <= self.wez_range_max_m and ata <= self.wez_ata_max_deg and aa <= self.wez_aa_max_deg:
            self.state = TacticalState.OFFENSIVE_WEZ
            heading_cmd = self.guidance.step_gps_pursuit(own_tel, primary_rival)
            # Kilitlenme anında sabit kanat yatışı (stabil görüntü için minimum roll)
            return self.state, 0.0, 0.0, heading_cmd

        # 4. Burun Buruna Karşılaşma (Head-On Merge): İki uçak birbirine doğru uçuyor
        elif ata <= 45.0 and aa >= 135.0:
            self.state = TacticalState.HEAD_ON_MERGE
            # 3-9 hattında avantaj elde etmek için hafif sağa ofset dönüş (Lead turn)
            heading_cmd = (geom["los_bearing_deg"] + 25.0) % 360.0
            return self.state, 15.0, 2.0, heading_cmd

        # 5. Taarruz Takibi (Offensive Pursuit): Hedefe doğru önleme rotası
        else:
            self.state = TacticalState.OFFENSIVE_PURSUIT
            heading_cmd = self.guidance.step_gps_pursuit(own_tel, primary_rival)
            # Dönüş açısına göre yumuşak koordineli yatış
            heading_err = (heading_cmd - own_tel.IHA_yonelme + 180.0) % 360.0 - 180.0
            roll_cmd = max(-30.0, min(30.0, heading_err * 0.8))
            return self.state, roll_cmd, 0.0, heading_cmd
