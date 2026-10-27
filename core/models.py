import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import List, Optional, Dict, Any
from datetime import datetime


class KilitDurumu(Enum):
    """Kilitlenme motoru durum makinesi aşamaları."""
    IDLE = "IDLE"               # Hedef aranıyor
    TRACKING = "TRACKING"       # Hedef takipte fakat kilit kriterleri tam değil
    LOCKING = "LOCKING"         # 4 saniyelik geri sayım başladı (kesintisiz şartlar sağlanıyor)
    LOCKED = "LOCKED"           # 4 saniye başarıyla tamamlandı, kilitlendi!
    LOST = "LOST"               # Hedef kaybedildi (tolerans süresi devrede)


@dataclass
class ZamanBilgisi:
    """TEKNOFEST şartnamesine uygun zaman damgası nesnesi."""
    saat: int = 0
    dakika: int = 0
    saniye: int = 0
    milisaniye: int = 0

    @classmethod
    def now(cls, server_offset_ms: float = 0.0) -> "ZamanBilgisi":
        """Sunucu senkronizasyon ofsetini de dikkate alarak geçerli zamanı üretir."""
        current_ts = time.time() + (server_offset_ms / 1000.0)
        dt = datetime.fromtimestamp(current_ts)
        return cls(
            saat=dt.hour,
            dakika=dt.minute,
            saniye=dt.second,
            milisaniye=int(dt.microsecond / 1000)
        )

    def to_dict(self) -> Dict[str, int]:
        return asdict(self)

    def to_seconds(self) -> float:
        return self.saat * 3600 + self.dakika * 60 + self.saniye + self.milisaniye / 1000.0

    def __str__(self) -> str:
        return f"{self.saat:02d}:{self.dakika:02d}:{self.saniye:02d}.{self.milisaniye:03d}"


@dataclass
class HedefKutusu:
    """Görüntü işlemeden gelen tespit ve takip edilen nesne kutusu."""
    x1: float
    y1: float
    x2: float
    y2: float
    conf: float = 0.0
    track_id: Optional[int] = None
    class_id: int = 0
    class_name: str = "iha"

    @property
    def genislik(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def yukseklik(self) -> float:
        return max(0.0, self.y2 - self.y1)

    @property
    def merkez_x(self) -> float:
        return self.x1 + self.genislik / 2.0

    @property
    def merkez_y(self) -> float:
        return self.y1 + self.yukseklik / 2.0

    @property
    def alan(self) -> float:
        return self.genislik * self.yukseklik

    def alan_orani(self, ekran_genislik: float, ekran_yukseklik: float) -> float:
        """Kutunun tüm ekran alanına oranını döndürür (%5 kuralı kontrolü için)."""
        ekran_alani = max(1.0, ekran_genislik * ekran_yukseklik)
        return self.alan / ekran_alani


@dataclass
class TelemetriPaketi:
    """TEKNOFEST Hakem Sunucusuna gönderilen telemetri JSON yapısı."""
    takim_numarasi: int
    IHA_enlem: float
    IHA_boylam: float
    IHA_irtifa: float
    IHA_dikilme: float          # Pitch (derece)
    IHA_yonelme: float          # Yaw / Heading (0-360 derece)
    IHA_yatis: float            # Roll (derece)
    IHA_hiz: float              # m/s cinsinden yer hızı
    IHA_batarya: int            # Kalan batarya yüzdesi (%0-100)
    IHA_otonom: int             # 1: Otonom mod, 0: Manuel
    IHA_kilitlenme: int         # 1: Kilitlenme gerçekleşiyor/gerçekleşti, 0: Yok
    Hedef_merkez_X: int         # Hedefin piksel merkez X koordinatı (Hedef yoksa 0)
    Hedef_merkez_Y: int         # Hedefin piksel merkez Y koordinatı (Hedef yoksa 0)
    Hedef_genislik: int         # Hedef kutusu piksel genişliği
    Hedef_yukseklik: int        # Hedef kutusu piksel yüksekliği
    GPSSaati: ZamanBilgisi = field(default_factory=ZamanBilgisi.now)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["GPSSaati"] = self.GPSSaati.to_dict()
        return data


@dataclass
class RakipIHABilgisi:
    """Hakem sunucusundan dönen rakip İHA konum telemetrisi."""
    takim_numarasi: int
    IHA_enlem: float
    IHA_boylam: float
    IHA_irtifa: float
    IHA_dikilme: float
    IHA_yonelme: float
    IHA_yatis: float
    zaman_farki: int = 0        # Milisaniye cinsinden gecikme

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RakipIHABilgisi":
        return cls(
            takim_numarasi=int(data.get("takim_numarasi", 0)),
            IHA_enlem=float(data.get("IHA_enlem", 0.0)),
            IHA_boylam=float(data.get("IHA_boylam", 0.0)),
            IHA_irtifa=float(data.get("IHA_irtifa", 0.0)),
            IHA_dikilme=float(data.get("IHA_dikilme", 0.0)),
            IHA_yonelme=float(data.get("IHA_yonelme", 0.0)),
            IHA_yatis=float(data.get("IHA_yatis", 0.0)),
            zaman_farki=int(data.get("zaman_farki", 0)),
        )


@dataclass
class SunucuYaniti:
    """Hakem sunucusunun telemetri gönderim isteğine döndüğü yanıt."""
    sunucusaati: ZamanBilgisi
    konumBilgileri: List[RakipIHABilgisi] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SunucuYaniti":
        saat_raw = data.get("sunucusaati", {})
        saat = ZamanBilgisi(
            saat=int(saat_raw.get("saat", 0)),
            dakika=int(saat_raw.get("dakika", 0)),
            saniye=int(saat_raw.get("saniye", 0)),
            milisaniye=int(saat_raw.get("milisaniye", 0)),
        )
        rakipler = [RakipIHABilgisi.from_dict(r) for r in data.get("konumBilgileri", [])]
        return cls(sunucusaati=saat, konumBilgileri=rakipler)


@dataclass
class KilitlenmePaketi:
    """Başarılı 4.0 saniye kilitlenme sonrası sunucuya iletilen paket."""
    kilitlenmeBaslangicZamani: ZamanBilgisi
    kilitlenmeBitisZamani: ZamanBilgisi
    otonom_kilitlenme: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kilitlenmeBaslangicZamani": self.kilitlenmeBaslangicZamani.to_dict(),
            "kilitlenmeBitisZamani": self.kilitlenmeBitisZamani.to_dict(),
            "otonom_kilitlenme": self.otonom_kilitlenme
        }
