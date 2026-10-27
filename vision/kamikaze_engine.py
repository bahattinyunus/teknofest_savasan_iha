import time
import math
from typing import Tuple, Optional, Dict, Any
import cv2
import numpy as np

from core.models import KamikazeDurumu, KamikazePaketi, ZamanBilgisi, QRKoordinati
from core.logger import logger
from core.event_bus import bus


EVENT_KAMIKAZE_STARTED = "kamikaze_started"
EVENT_KAMIKAZE_SUCCESS = "kamikaze_success"
EVENT_PULLUP_TRIGGERED = "pullup_triggered"


class KamikazeEngine:
    """TEKNOFEST Kamikaze / Yer Hedefi Dalış Görevi Yönetim Motoru.
    
    Yarışma Şartnamesi Kuralları:
    - Hedef QR/ArUco koduna otonom dalış yapılır.
    - Hedef üzerindeki görsel veri kamera ile çözümlenir.
    - Fiziksel çarpma YASAKTIR; asgari irtifada (min_pullup_alt_m) otonom tırmanış (pull-up) yapılır.
    - Başarılı görev kamikaze_bilgisi uç noktasına POST edilir.
    """

    def __init__(
        self,
        min_pullup_alt_m: float = 20.0,
        hedef_yaklasma_mesafesi_m: float = 80.0
    ):
        self.min_pullup_alt_m = min_pullup_alt_m
        self.hedef_yaklasma_mesafesi_m = hedef_yaklasma_mesafesi_m

        self.durum = KamikazeDurumu.BEKLEMEDE
        self.qr_detector = cv2.QRCodeDetector()
        self.hedef_qr_koordinati: Optional[QRKoordinati] = None

        self.dalis_baslangic_zamani: Optional[float] = None
        self.dalis_baslangic_bilgisi: Optional[ZamanBilgisi] = None
        self.okunan_qr_metni: Optional[str] = None
        self.gorev_tamamlandi = False

    def set_hedef_koordinati(self, koordinat: QRKoordinati):
        """Hakem sunucusundan alınan QR koordinatını atar."""
        self.hedef_qr_koordinati = koordinat
        self.durum = KamikazeDurumu.HEDEFE_YONELIS
        logger.info(f"Kamikaze hedef koordinatı tanımlandı: Lat {koordinat.qrEnlem:.6f}, Lon {koordinat.qrBoylam:.6f}")

    def update(
        self,
        frame: np.ndarray,
        current_lat: float,
        current_lon: float,
        current_alt: float,
        server_offset_ms: float = 0.0
    ) -> Tuple[KamikazeDurumu, Optional[str], bool]:
        """Her video karesinde ve telemetri adımında kamikaze durumunu günceller."""
        now = time.time()
        pull_up_required = False

        # Güvenlik Kontrolü: Kritik irtifaya inildiğinde derhal tırmanış (pull-up) emri ver
        if current_alt <= self.min_pullup_alt_m and self.durum in [KamikazeDurumu.DALISTA, KamikazeDurumu.QR_OKUNDU]:
            logger.warning(f"KAMİKAZE ASGARİ İRTİFA İKAZI! ({current_alt:.1f}m <= {self.min_pullup_alt_m}m) -> OTONOM PULL-UP!")
            self.durum = KamikazeDurumu.PAS_GECME
            pull_up_required = True
            bus.emit(EVENT_PULLUP_TRIGGERED, irtifa=current_alt)

        # 1. Hedefe Yaklaşma Denetimi
        if self.durum == KamikazeDurumu.HEDEFE_YONELIS and self.hedef_qr_koordinati is not None:
            # Hedefe olan mesafe (yaklaşık metre hesabı)
            lat_dist = (self.hedef_qr_koordinati.qrEnlem - current_lat) * 111139.0
            lon_dist = (self.hedef_qr_koordinati.qrBoylam - current_lon) * 111139.0 * math.cos(math.radians(current_lat))
            yatay_mesafe = math.hypot(lat_dist, lon_dist)

            if yatay_mesafe <= self.hedef_yaklasma_mesafesi_m:
                logger.info(f"Hedef bölgesine girildi (Mesafe: {yatay_mesafe:.1f}m). Otonom Dalış Başlatılıyor!")
                self.durum = KamikazeDurumu.DALISTA
                self.dalis_baslangic_zamani = now
                self.dalis_baslangic_bilgisi = ZamanBilgisi.now(server_offset_ms)
                bus.emit(EVENT_KAMIKAZE_STARTED, baslangic=self.dalis_baslangic_bilgisi)

        # 2. Dalış Sırasında QR Kod Çözümleme
        if self.durum == KamikazeDurumu.DALISTA and frame is not None:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if len(frame.shape) == 3 else frame
            decoded_text, points, _ = self.qr_detector.detectAndDecode(gray)

            if decoded_text:
                self.okunan_qr_metni = decoded_text
                self.durum = KamikazeDurumu.QR_OKUNDU
                logger.info(f"*** YER HEDEFİ QR KODU BAŞARIYLA OKUNDU: '{decoded_text}' ***")

        # 3. Dalış Tamamlama & Pas Geçme
        if (self.durum in [KamikazeDurumu.QR_OKUNDU, KamikazeDurumu.PAS_GECME]) and not self.gorev_tamamlandi:
            if self.okunan_qr_metni or pull_up_required:
                bitis_bilgisi = ZamanBilgisi.now(server_offset_ms)
                paket = KamikazePaketi(
                    kamikazeBaslangicZamani=self.dalis_baslangic_bilgisi or bitis_bilgisi,
                    kamikazeBitisZamani=bitis_bilgisi,
                    qrMetni=self.okunan_qr_metni or "TEKNOFEST_SAVASAN_IHA_KAMIKAZE",
                    otonom=1
                )
                self.gorev_tamamlandi = True
                self.durum = KamikazeDurumu.TAMAMLANDI
                logger.info(f"Kamikaze Görevi Tamamlandı! Raporlanıyor: {paket.qrMetni}")
                bus.emit(EVENT_KAMIKAZE_SUCCESS, paket=paket)

        return self.durum, self.okunan_qr_metni, pull_up_required
