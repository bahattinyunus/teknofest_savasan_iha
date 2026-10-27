import math
import time
from enum import Enum
from typing import Optional, Tuple, List
from core.models import TelemetriPaketi, RakipIHABilgisi
from core.logger import logger


class ManevraTipi(Enum):
    DUZ_UCUS = "DUZ_UCUS"
    BREAK_TURN = "BREAK_TURN"       # Sert yatışlı ani kaçış dönüşü
    HIGH_YO_YO = "HIGH_YO_YO"       # Hız düşürüp irtifa kazanarak rakibi öne geçirme
    SCISSORS = "SCISSORS"           # Makas manevrası (Zikzaklar ile rakibi taşırma)


class BFMEvasiveTactics:
    """Temel Savaş Manevraları (Basic Fighter Maneuvers - BFM) ve Taktiksel Kaçış Denetleyicisi.
    
    Arkamızda bir rakip İHA kilitlenmeye başladığında, kilitlenme geometrisini bozmak
    ve rakibi öne düşürmek (overshoot induction) için otomatik hava muharebesi manevraları üretir.
    """

    def __init__(
        self,
        tehdit_mesafesi_m: float = 120.0,
        tehdit_aci_konisi_deg: float = 35.0,
        maks_yatis_acisi_deg: float = 45.0
    ):
        self.tehdit_mesafesi_m = tehdit_mesafesi_m
        self.tehdit_aci_konisi_deg = tehdit_aci_konisi_deg
        self.maks_yatis_acisi_deg = maks_yatis_acisi_deg

        self.aktif_manevra = ManevraTipi.DUZ_UCUS
        self.manevra_baslangic_zamani: float = 0.0
        self.makas_yonu: int = 1

    def evaluate_threat(self, own_tel: TelemetriPaketi, rivals: List[RakipIHABilgisi]) -> Optional[RakipIHABilgisi]:
        """Arkamızda tehlike oluşturan (kilit açısında) bir rakip İHA olup olmadığını denetler."""
        if not rivals:
            return None

        own_heading = own_tel.IHA_yonelme

        for r in rivals:
            # 1. Yatay Mesafe
            d_lat = (r.IHA_enlem - own_tel.IHA_enlem) * 111139.0
            d_lon = (r.IHA_boylam - own_tel.IHA_boylam) * 111139.0 * math.cos(math.radians(own_tel.IHA_enlem))
            dist = math.hypot(d_lat, d_lon)

            if dist > self.tehdit_mesafesi_m:
                continue

            # 2. Göreceli Açı (Bearing from own to rival)
            bearing_to_rival = (math.degrees(math.atan2(d_lon, d_lat)) + 360.0) % 360.0
            
            # Uçağın arkası: (own_heading + 180) % 360
            rear_angle = (own_heading + 180.0) % 360.0
            angle_diff = abs((bearing_to_rival - rear_angle + 180.0) % 360.0 - 180.0)

            # Rakip arkamızdaki tehdit konisinde mi?
            if angle_diff <= self.tehdit_aci_konisi_deg:
                return r

        return None

    def execute_evasion(
        self,
        own_tel: TelemetriPaketi,
        threat: Optional[RakipIHABilgisi]
    ) -> Tuple[ManevraTipi, float, float, float]:
        """Tehdit durumuna göre kaçış roll, pitch ve hedef rota (heading) komutu üretir."""
        now = time.time()

        if threat is None:
            self.aktif_manevra = ManevraTipi.DUZ_UCUS
            return ManevraTipi.DUZ_UCUS, 0.0, 0.0, own_tel.IHA_yonelme

        # Yeni manevra başlat
        if self.aktif_manevra == ManevraTipi.DUZ_UCUS:
            self.aktif_manevra = ManevraTipi.BREAK_TURN
            self.manevra_baslangic_zamani = now
            logger.warning(f"TEHDİT ALGILANDI! Rakip İHA {threat.takim_numarasi} arkamızda! BFM Kaçış Başlatıldı: {self.aktif_manevra.value}")

        dt = now - self.manevra_baslangic_zamani

        # 1. Aşama: Break Turn (Sert Yatışlı Dönüş - İlk 3 saniye)
        if dt < 3.0:
            self.aktif_manevra = ManevraTipi.BREAK_TURN
            roll_cmd = self.maks_yatis_acisi_deg  # Maksimum sağa yatış
            pitch_cmd = 3.0  # İrtifa kaybetmemek için burun hafif yukarı
            heading_cmd = (own_tel.IHA_yonelme + 90.0) % 360.0
            return self.aktif_manevra, roll_cmd, pitch_cmd, heading_cmd

        # 2. Aşama: Scissors (Makas Manevrası - Yön değiştirerek rakibi öne fırlatma)
        elif dt < 8.0:
            self.aktif_manevra = ManevraTipi.SCISSORS
            # Her 2 saniyede bir yön değiştir
            cycle = int((dt - 3.0) / 2.0)
            direction = -1 if cycle % 2 == 1 else 1
            roll_cmd = direction * self.maks_yatis_acisi_deg
            pitch_cmd = 2.0
            heading_cmd = (own_tel.IHA_yonelme + (direction * 70.0) + 360.0) % 360.0
            return self.aktif_manevra, roll_cmd, pitch_cmd, heading_cmd

        # 3. Aşama: High Yo-Yo (Tırmanıp hız kesme)
        elif dt < 12.0:
            self.aktif_manevra = ManevraTipi.HIGH_YO_YO
            roll_cmd = 10.0
            pitch_cmd = 15.0  # Sert tırmanış
            heading_cmd = own_tel.IHA_yonelme
            return self.aktif_manevra, roll_cmd, pitch_cmd, heading_cmd

        else:
            # Döngüyü başa sar
            self.manevra_baslangic_zamani = now
            return self.aktif_manevra, 0.0, 0.0, own_tel.IHA_yonelme
