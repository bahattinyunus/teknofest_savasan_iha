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
    Hedef_merkez_X: int = 0         # Hedefin piksel merkez X koordinatı (Hedef yoksa 0)
    Hedef_merkez_Y: int = 0         # Hedefin piksel merkez Y koordinatı (Hedef yoksa 0)
    Hedef_genislik: int = 0         # Hedef kutusu piksel genişliği
    Hedef_yukseklik: int = 0        # Hedef kutusu piksel yüksekliği
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


RakipIHA = RakipIHABilgisi  # Kolay erişim için takma ad (alias)


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


class KamikazeDurumu(Enum):
    """Kamikaze / Yer Hedefi Dalış Görevi aşamaları."""
    BEKLEMEDE = "BEKLEMEDE"               # Görev başlamadı
    HEDEFE_YONELIS = "HEDEFE_YONELIS"     # QR koordinatına seyrüsefer
    DALISTA = "DALISTA"                   # Hedefe doğru otonom dalış
    QR_OKUNDU = "QR_OKUNDU"               # QR/ArUco başarıyla tespit edildi
    PAS_GECME = "PAS_GECME"               # Asgari irtifada otonom pull-up (tırmanış)
    TAMAMLANDI = "TAMAMLANDI"             # Kamikaze paketi sunucuya başarıyla iletildi


@dataclass
class QRKoordinati:
    """Hakem sunucusundan GET /api/qr_koordinati ile alınan yer hedefi koordinatı."""
    qrEnlem: float
    qrBoylam: float

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QRKoordinati":
        return cls(
            qrEnlem=float(data.get("qrEnlem", 0.0)),
            qrBoylam=float(data.get("qrBoylam", 0.0))
        )


@dataclass
class HSSBolgesi:
    """Hava Savunma Sistemi (HSS) / Uçuşa Yasak Tehdit Hacmi."""
    hss_id: int
    merkez_enlem: float
    merkez_boylam: float
    yaricap_m: float
    alt_irtifa_m: float
    ust_irtifa_m: float


@dataclass
class KamikazePaketi:
    """Başarılı QR okuma ve dalış sonrası sunucuya iletilen paket (POST /api/kamikaze_bilgisi)."""
    kamikazeBaslangicZamani: ZamanBilgisi
    kamikazeBitisZamani: ZamanBilgisi
    qrMetni: str
    otonom: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kamikazeBaslangicZamani": self.kamikazeBaslangicZamani.to_dict(),
            "kamikazeBitisZamani": self.kamikazeBitisZamani.to_dict(),
            "qrMetni": self.qrMetni,
            "otonom": self.otonom
        }


class EWAlertLevel(Enum):
    """Elektronik Harp ve Karıştırma Tehdit Düzeyi."""
    NORMAL = "NORMAL"                 # Herhangi bir tehdit veya karıştırma yok
    CAUTION = "CAUTION"               # Hafif sinyal bozulması veya paket kaybı
    THREAT = "THREAT"                 # Ciddi RF karıştırma veya GPS aldatması şüphesi
    CRITICAL_JAMMING = "CRITICAL_JAMMING" # Tam GNSS kaybı ve yoğun karıştırma
    EMCON = "EMCON"                   # Emisyon Kontrolü (Sessiz Çalışma / RF Susturma)


@dataclass
class EWStatus:
    """Elektronik harp ve karşı tedbir durum özeti."""
    tehdit_seviyesi: EWAlertLevel = EWAlertLevel.NORMAL
    gnss_aldatma_tespiti: bool = False
    rf_karistirma_tespiti: bool = False
    optik_sahte_hedef_tespiti: bool = False
    emcon_aktif: bool = False
    sinyal_kalite_skoru: float = 1.0     # 0.0 (tam kör) - 1.0 (mükemmel)
    onerilen_eylem: str = "STANDART_SEYRUSEFER"


@dataclass
class EnergyState:
    """John Boyd Enerji-Manevra (E-M) teorisi uçuş zarfı ve enerji durumu."""
    ozgurluk_enerjisi_He_m: float = 0.0          # Özgül Enerji Yüksekliği H_e = h + V^2 / (2g) [metre]
    ozgurluk_fazla_gucu_Ps_mps: float = 0.0      # P_s = (T - D)/W * V [m/s]
    manevra_kose_hizi_Vc_mps: float = 24.0       # Köşe hızı V_c [m/s] (maksimum anlık dönüş açısı)
    anlik_donus_hizi_dps: float = 0.0            # Maksimum anlık dönüş hızı [deg/s]
    surdurulebilir_donus_hizi_dps: float = 0.0    # Sürdürülebilir dönüş hızı (Ps = 0) [deg/s]
    asgari_donus_yaricapi_m: float = 20.0        # En küçük dönüş yarıçapı R_min [metre]
    enerji_avantaji_m: float = 0.0               # Hedefe kıyasla enerji farkı: He_own - He_target [m]
    onerilen_taktik: str = "RATE_FIGHT_2_CIRCLE" # "RATE_FIGHT_2_CIRCLE" veya "RADIUS_FIGHT_1_CIRCLE"
    perdovites_koruma_aktif: bool = False


@dataclass
class EKFState6DOF:
    """15-Durumlu Havacılık Genişletilmiş Kalman Filtresi Durum Vektörü."""
    pos_ned_m: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])       # Kuzey, Doğu, Aşağı (m)
    vel_ned_mps: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])     # V_N, V_E, V_D (m/s)
    quat: List[float] = field(default_factory=lambda: [1.0, 0.0, 0.0, 0.0])       # [q0, q1, q2, q3]
    euler_deg: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])       # [Roll, Pitch, Yaw]
    accel_bias: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])      # [b_ax, b_ay, b_az] (m/s^2)
    gyro_bias: List[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])       # [b_gx, b_gy, b_gz] (rad/s)
    covariance_diag: List[float] = field(default_factory=list)                    # Kovaryans matrisi köşegeni
    timestamp_s: float = 0.0


@dataclass
class ProofRecord:
    """Kriptografik kilitlenme zincirindeki tekil kare kaydı."""
    frame_index: int
    timestamp_s: float
    frame_hash_sha256: str
    target_box: Dict[str, Any]
    telemetry_summary: Dict[str, Any]
    previous_hash: str
    record_hash: str


@dataclass
class ProofChainManifest:
    """Bir kilitlenme sürecinin kriptografik mühür ve doğrulama sertifikası."""
    lock_id: str
    team_id: int
    start_time_iso: str
    end_time_iso: str
    total_frames: int
    duration_s: float
    merkle_root: str
    final_chain_hash: str
    digital_signature: str
    is_valid_rule_lock: bool
    score_earned: float
    records: List[ProofRecord] = field(default_factory=list)

