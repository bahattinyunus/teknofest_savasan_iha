import time
from typing import Optional, Dict, Any, Tuple, List
import requests

from core.models import (
    TelemetriPaketi,
    SunucuYaniti,
    KilitlenmePaketi,
    ZamanBilgisi,
    QRKoordinati,
    HSSBolgesi,
    KamikazePaketi
)
from core.logger import logger
from .time_sync import TimeSynchronizer


class RefereeClient:
    """TEKNOFEST Savaşan İHA Hakem Sunucusu REST API İstemcisi.
    
    Tüm uç noktalar şartnameye uygun olarak uygulanmıştır:
    - POST /api/giris
    - GET  /api/sunucusaati
    - POST /api/telemetri_gonder
    - POST /api/kilitlenme_bilgisi
    - GET  /api/cikis
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        username: str = "takim1",
        password: str = "sifre123",
        timeout: float = 1.5
    ):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout
        
        self.session = requests.Session()
        self.token: Optional[str] = None
        self.is_logged_in: bool = False
        self.time_sync = TimeSynchronizer()

    def giris_yap(self) -> bool:
        """Hakem sunucusunda oturum açar (/api/giris)."""
        url = f"{self.base_url}/api/giris"
        payload = {
            "kullanici_adi": self.username,
            "sifre": self.password
        }

        try:
            resp = self.session.post(url, json=payload, timeout=self.timeout)
            if resp.status_code in [200, 201]:
                self.is_logged_in = True
                data = resp.json() if resp.text else {}
                self.token = data.get("token") or data.get("session_id")
                logger.info(f"Hakem sunucusuna giriş başarılı! [Takım: {self.username}]")
                # Giriş sonrası hemen saat senkronizasyonu yap
                self.saat_senkronize_et()
                return True
            else:
                logger.error(f"Sunucu giriş reddedildi: HTTP {resp.status_code} - {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Hakem sunucusuna bağlanılamadı ({url}): {e}")
            return False

    def saat_senkronize_et(self) -> Optional[ZamanBilgisi]:
        """Sunucu saatini sorgular ve yerel saat ile senkronizasyon sağlar (/api/sunucusaati)."""
        url = f"{self.base_url}/api/sunucusaati"
        t_start = time.time()
        try:
            resp = self.session.get(url, timeout=self.timeout)
            t_end = time.time()
            if resp.status_code == 200:
                data = resp.json()
                server_time = ZamanBilgisi(
                    saat=int(data.get("saat", 0)),
                    dakika=int(data.get("dakika", 0)),
                    saniye=int(data.get("saniye", 0)),
                    milisaniye=int(data.get("milisaniye", 0))
                )
                self.time_sync.update_sync(server_time, t_start, t_end)
                return server_time
            else:
                logger.warning(f"Saat sorgusu başarısız: HTTP {resp.status_code}")
                return None
        except Exception as e:
            logger.warning(f"Sunucu saatine erişilemedi: {e}")
            return None

    def telemetri_gonder(self, telemetri: TelemetriPaketi) -> Tuple[bool, Optional[SunucuYaniti]]:
        """Uçağın anlık telemetrisini hakem sunucusuna iletir (/api/telemetri_gonder).
        
        Başarılı yanıtta sunucu saati ve rakip İHA konumları döner.
        """
        url = f"{self.base_url}/api/telemetri_gonder"
        payload = telemetri.to_dict()

        try:
            resp = self.session.post(url, json=payload, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                yanit = SunucuYaniti.from_dict(data)
                return True, yanit
            elif resp.status_code == 204:
                logger.error("Hakem sunucusu telemetri formatını reddetti! (HTTP 204 Format Yanlış)")
                return False, None
            elif resp.status_code == 400:
                logger.error(f"Hatalı telemetri isteği! (HTTP 400): {resp.text}")
                return False, None
            else:
                logger.warning(f"Telemetri gönderimi başarısız: HTTP {resp.status_code}")
                return False, None
        except Exception as e:
            logger.warning(f"Telemetri paketi iletilemedi: {e}")
            return False, None

    def kilitlenme_bilgisi_gonder(self, kilit_paketi: KilitlenmePaketi) -> bool:
        """Otonom 4.0 sn kilitlenme tamamlandığında sunucuya bildirir (/api/kilitlenme_bilgisi)."""
        url = f"{self.base_url}/api/kilitlenme_bilgisi"
        payload = kilit_paketi.to_dict()

        logger.info(f"Hakem sunucusuna kilitlenme paketi iletiliyor: {payload}")
        try:
            resp = self.session.post(url, json=payload, timeout=self.timeout)
            if resp.status_code in [200, 201]:
                logger.info(">>> KİLİTLENME SUNUCU TARAFINDAN ONAYLANDI! (Puan Alındı) <<<")
                return True
            else:
                logger.error(f"Kilitlenme reddedildi: HTTP {resp.status_code} - {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Kilitlenme paketi gönderilirken ağ hatası: {e}")
            return False

    def qr_koordinati_al(self) -> Optional[QRKoordinati]:
        """Kamikaze görevi için hedef QR koordinatını hakem sunucusundan çeker (/api/qr_koordinati)."""
        url = f"{self.base_url}/api/qr_koordinati"
        try:
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                koordinat = QRKoordinati.from_dict(data)
                logger.info(f"Hakem sunucusundan hedef QR koordinatı alındı: {koordinat}")
                return koordinat
            else:
                logger.warning(f"QR koordinatı alınamadı: HTTP {resp.status_code}")
                return None
        except Exception as e:
            logger.warning(f"QR koordinatı sorgu hatası: {e}")
            return None

    def hss_koordinatlari_al(self) -> List[HSSBolgesi]:
        """Hava Savunma Sistemi (HSS) tehdit hacimlerini sorgular (/api/hss_koordinatlari)."""
        url = f"{self.base_url}/api/hss_koordinatlari"
        try:
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code == 200:
                data = resp.json()
                hss_list = []
                for item in data.get("hss_bolgeleri", []):
                    hss_list.append(HSSBolgesi(
                        hss_id=int(item.get("id", 0)),
                        merkez_enlem=float(item.get("enlem", 0.0)),
                        merkez_boylam=float(item.get("boylam", 0.0)),
                        yaricap_m=float(item.get("yaricap", 50.0)),
                        alt_irtifa_m=float(item.get("alt_irtifa", 0.0)),
                        ust_irtifa_m=float(item.get("ust_irtifa", 120.0))
                    ))
                logger.info(f"Hakem sunucusundan {len(hss_list)} adet HSS tehdit bölgesi alındı.")
                return hss_list
            return []
        except Exception as e:
            logger.warning(f"HSS koordinat sorgu hatası: {e}")
            return []

    def kamikaze_bilgisi_gonder(self, kamikaze_paketi: KamikazePaketi) -> bool:
        """Kamikaze QR okuma ve dalış görevi tamamlandığında sunucuya bildirir (/api/kamikaze_bilgisi)."""
        url = f"{self.base_url}/api/kamikaze_bilgisi"
        payload = kamikaze_paketi.to_dict()

        logger.info(f"Hakem sunucusuna Kamikaze paketi iletiliyor: {payload}")
        try:
            resp = self.session.post(url, json=payload, timeout=self.timeout)
            if resp.status_code in [200, 201]:
                logger.info(">>> KAMİKAZE GÖREVİ SUNUCU TARAFINDAN ONAYLANDI! (+150 Puan) <<<")
                return True
            else:
                logger.error(f"Kamikaze paketi reddedildi: HTTP {resp.status_code} - {resp.text}")
                return False
        except Exception as e:
            logger.error(f"Kamikaze gönderim hatası: {e}")
            return False

    def cikis_yap(self) -> bool:
        """Uçuş görevi bittiğinde oturumu kapatır (/api/cikis)."""
        url = f"{self.base_url}/api/cikis"
        try:
            resp = self.session.get(url, timeout=self.timeout)
            self.is_logged_in = False
            logger.info("Hakem sunucusundan çıkış yapıldı.")
            return resp.status_code == 200
        except Exception as e:
            logger.warning(f"Çıkış yapılırken hata: {e}")
            self.is_logged_in = False
            return False
