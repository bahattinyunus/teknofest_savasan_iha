import os
import cv2
import json
import time
from collections import deque
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any
import numpy as np

from core.models import HedefKutusu, KilitDurumu, ZamanBilgisi, KilitlenmePaketi
from core.logger import logger
from core.event_bus import (
    bus,
    EVENT_LOCK_STARTED,
    EVENT_LOCK_PROGRESS,
    EVENT_LOCK_SUCCESS,
    EVENT_LOCK_LOST
)


class LockEngine:
    """TEKNOFEST Savaşan İHA Otonom Kilitlenme Motoru.
    
    Özellikler:
    - Ekran merkezleme toleransı denetimi
    - %5 boyut / alan şartı denetimi
    - Kesintisiz 4.0 saniye kilitlenme sayacı
    - Anlık titreme / kayıplar için tolerans süresi (grace time)
    - Otomatik kanıt video ve JSON paketi oluşturma
    """

    def __init__(
        self,
        gerekli_sure_sn: float = 4.0,
        hedef_alan_orani_min: float = 0.05,
        merkez_tolerans_orani: float = 0.35,
        kayip_toleransi_sn: float = 0.35,
        kanit_dizini: str = "proofs",
        kanit_fps: int = 20,
        kanit_on_kayit_sn: float = 2.0
    ):
        self.gerekli_sure_sn = gerekli_sure_sn
        self.hedef_alan_orani_min = hedef_alan_orani_min
        self.merkez_tolerans_orani = merkez_tolerans_orani
        self.kayip_toleransi_sn = kayip_toleransi_sn
        self.kanit_dizini = kanit_dizini
        self.kanit_fps = kanit_fps
        self.kanit_on_kayit_sn = kanit_on_kayit_sn

        os.makedirs(self.kanit_dizini, exist_ok=True)

        # Durum Değişkenleri
        self.durum = KilitDurumu.IDLE
        self.aktif_hedef: Optional[HedefKutusu] = None
        self.kilit_baslangic_zamani: Optional[float] = None
        self.kilit_baslangic_bilgisi: Optional[ZamanBilgisi] = None
        self.son_gorulme_zamani: Optional[float] = None
        self.gecen_sure_sn: float = 0.0
        self.kilit_sayisi: int = 0

        # Kanıt videosu için döngüsel kare tamponu (Rolling buffer)
        # Örnek: (4.0s + 2.0s) * 20 fps = 120 kare
        tampon_boyutu = int((self.gerekli_sure_sn + self.kanit_on_kayit_sn + 1.0) * self.kanit_fps)
        self.kare_tamponu = deque(maxlen=tampon_boyutu)

    def _hedef_kriterleri_sagliyor_mu(
        self,
        hedef: HedefKutusu,
        ekran_genislik: int,
        ekran_yukseklik: int
    ) -> Tuple[bool, Dict[str, Any]]:
        """Hedefin şartnamedeki kilitlenme kriterlerine uygunluğunu test eder."""
        # 1. Alan Oranı Testi (%5 Kuralı)
        alan_orani = hedef.alan_orani(ekran_genislik, ekran_yukseklik)
        alan_uygun = alan_orani >= self.hedef_alan_orani_min

        # 2. Merkezleme Testi
        ekran_merkez_x = ekran_genislik / 2.0
        ekran_merkez_y = ekran_yukseklik / 2.0
        
        tolerans_yaricap = min(ekran_genislik, ekran_yukseklik) * (self.merkez_tolerans_orani / 2.0)
        dx = hedef.merkez_x - ekran_merkez_x
        dy = hedef.merkez_y - ekran_merkez_y
        merkez_uzaklik = np.hypot(dx, dy)
        merkez_uygun = merkez_uzaklik <= tolerans_yaricap

        uygun = alan_uygun and merkez_uygun
        
        ayrintilar = {
            "alan_orani": alan_orani,
            "alan_uygun": alan_uygun,
            "merkez_uzaklik": merkez_uzaklik,
            "merkez_tolerans": tolerans_yaricap,
            "merkez_uygun": merkez_uygun
        }
        return uygun, ayrintilar

    def _sec_en_iyi_hedef(
        self,
        hedefler: List[HedefKutusu],
        ekran_genislik: int,
        ekran_yukseklik: int
    ) -> Optional[HedefKutusu]:
        """Kadrajdaki hedefler arasından merkezde ve önceden kilitlenilmekte olanı önceliklendirir."""
        if not hedefler:
            return None

        # Önceden kilitlenilen hedef kadrajdaysa aynı hedefi sürdür (Track ID ile)
        if self.aktif_hedef is not None and self.aktif_hedef.track_id is not None:
            for h in hedefler:
                if h.track_id == self.aktif_hedef.track_id:
                    return h

        # Aksi takdirde ekranda merkeze en yakın ve kriterleri sağlayan en uygun hedefi seç
        ekran_merkez_x = ekran_genislik / 2.0
        ekran_merkez_y = ekran_yukseklik / 2.0

        def uzaklik(h: HedefKutusu):
            return np.hypot(h.merkez_x - ekran_merkez_x, h.merkez_y - ekran_merkez_y)

        return min(hedefler, key=uzaklik)

    def update(
        self,
        frame: np.ndarray,
        hedefler: List[HedefKutusu],
        server_offset_ms: float = 0.0
    ) -> Tuple[KilitDurumu, float, Optional[HedefKutusu]]:
        """Her video karesinde kilitlenme mantığını günceller."""
        now = time.time()
        h, w = frame.shape[:2]

        # Kanıt tamponuna kareyi ekle
        self.kare_tamponu.append(frame.copy())

        secilen_hedef = self._sec_en_iyi_hedef(hedefler, w, h)
        kriter_saglandi = False

        if secilen_hedef is not None:
            kriter_saglandi, _ = self._hedef_kriterleri_sagliyor_mu(secilen_hedef, w, h)

        if kriter_saglandi and secilen_hedef is not None:
            self.son_gorulme_zamani = now
            self.aktif_hedef = secilen_hedef

            if self.durum in [KilitDurumu.IDLE, KilitDurumu.TRACKING, KilitDurumu.LOST]:
                # Yeni kilitlenme sayacı başlat
                self.durum = KilitDurumu.LOCKING
                self.kilit_baslangic_zamani = now
                self.kilit_baslangic_bilgisi = ZamanBilgisi.now(server_offset_ms)
                self.gecen_sure_sn = 0.0
                bus.emit(EVENT_LOCK_STARTED, hedef=secilen_hedef, baslangic=self.kilit_baslangic_bilgisi)
                logger.info(f"Kilitlenme sayacı başladı! Hedef ID: {secilen_hedef.track_id}")
            elif self.durum == KilitDurumu.LOCKING:
                # Sayacı artır
                self.gecen_sure_sn = now - (self.kilit_baslangic_zamani or now)
                ilerleme_yuzdesi = min(100.0, (self.gecen_sure_sn / self.gerekli_sure_sn) * 100.0)
                bus.emit(EVENT_LOCK_PROGRESS, sure=self.gecen_sure_sn, yuzde=ilerleme_yuzdesi)

                # 4.0 saniye tamamlandı mı?
                if self.gecen_sure_sn >= self.gerekli_sure_sn:
                    self.durum = KilitDurumu.LOCKED
                    self.kilit_sayisi += 1
                    bitis_bilgisi = ZamanBilgisi.now(server_offset_ms)
                    
                    paket = KilitlenmePaketi(
                        kilitlenmeBaslangicZamani=self.kilit_baslangic_bilgisi or bitis_bilgisi,
                        kilitlenmeBitisZamani=bitis_bilgisi,
                        otonom_kilitlenme=1
                    )
                    
                    logger.info(f"*** KİLİTLENME BAŞARILI! Toplam Kilit: {self.kilit_sayisi} ***")
                    
                    # Kanıt videosunu ve JSON metadata dosyasını kaydet
                    kanit_dosyasi = self._kaydet_kanit(paket, secilen_hedef)
                    
                    bus.emit(EVENT_LOCK_SUCCESS, paket=paket, kanit_yolu=kanit_dosyasi)

        else:
            # Şartlar sağlanmıyor veya hedef kayboldu
            if self.durum == KilitDurumu.LOCKING:
                # Tolerans süresi kontrolü (Kısa süreli sapmalar sıfırlamasın)
                zaman_farki = now - (self.son_gorulme_zamani or now)
                if zaman_farki > self.kayip_toleransi_sn:
                    logger.warning(f"Kilitlenme kriteri bozuldu! Sayaç sıfırlandı. Süre: {self.gecen_sure_sn:.2f} sn")
                    self.durum = KilitDurumu.TRACKING if secilen_hedef else KilitDurumu.IDLE
                    self.kilit_baslangic_zamani = None
                    self.gecen_sure_sn = 0.0
                    bus.emit(EVENT_LOCK_LOST)
                else:
                    self.durum = KilitDurumu.LOST
            elif self.durum == KilitDurumu.LOCKED:
                # Zaten kilitlenildi, hedef uzaklaşana veya kullanıcı resetleyene kadar bekle
                if not secilen_hedef:
                    self.durum = KilitDurumu.IDLE
                    self.gecen_sure_sn = 0.0
            else:
                self.durum = KilitDurumu.TRACKING if secilen_hedef else KilitDurumu.IDLE
                self.gecen_sure_sn = 0.0

        return self.durum, self.gecen_sure_sn, self.aktif_hedef

    def _kaydet_kanit(self, paket: KilitlenmePaketi, hedef: HedefKutusu) -> str:
        """Kilitlenme anına ait video kaydı ve JSON dosyasını oluşturur."""
        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        video_adi = f"kilit_kanit_{timestamp_str}.mp4"
        json_adi = f"kilit_kanit_{timestamp_str}.json"
        
        video_yolu = os.path.join(self.kanit_dizini, video_adi)
        json_yolu = os.path.join(self.kanit_dizini, json_adi)

        # 1. Video Kaydı
        if len(self.kare_tamponu) > 0:
            h, w = self.kare_tamponu[0].shape[:2]
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(video_yolu, fourcc, float(self.kanit_fps), (w, h))
            for k in self.kare_tamponu:
                writer.write(k)
            writer.release()
            logger.info(f"Kanıt videosu kaydedildi: {video_yolu}")

        # 2. JSON Metadata Kaydı
        metadata = {
            "paket": paket.to_dict(),
            "hedef": {
                "track_id": hedef.track_id,
                "merkez_x": hedef.merkez_x,
                "merkez_y": hedef.merkez_y,
                "genislik": hedef.genislik,
                "yukseklik": hedef.yukseklik,
                "conf": hedef.conf
            },
            "video_dosyasi": video_adi,
            "olusturuldu_ts": time.time()
        }
        with open(json_yolu, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

        logger.info(f"Kanıt metadata kaydedildi: {json_yolu}")
        return video_yolu

    def reset(self):
        """Kilit motorunu sıfırlar."""
        self.durum = KilitDurumu.IDLE
        self.kilit_baslangic_zamani = None
        self.kilit_baslangic_bilgisi = None
        self.son_gorulme_zamani = None
        self.gecen_sure_sn = 0.0
        self.aktif_hedef = None
