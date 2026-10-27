import math
import time
from typing import Tuple, Optional
from core.models import HedefKutusu, RakipIHABilgisi, TelemetriPaketi
from core.logger import logger


class VisualServoingPID:
    """Kamera görüntüsündeki hedefi ekran merkezinde tutmak için PID tabanlı yönlendirme."""

    def __init__(
        self,
        kp_yaw: float = 0.08,
        kd_yaw: float = 0.02,
        kp_pitch: float = 0.06,
        kd_pitch: float = 0.01
    ):
        self.kp_yaw = kp_yaw
        self.kd_yaw = kd_yaw
        self.kp_pitch = kp_pitch
        self.kd_pitch = kd_pitch

        self.last_err_x = 0.0
        self.last_err_y = 0.0
        self.last_time = time.time()

    def compute_control_commands(
        self,
        target: HedefKutusu,
        screen_w: int,
        screen_h: int
    ) -> Tuple[float, float]:
        """Piksel hatasından roll/yaw rate ve pitch açısı komutları üretir."""
        now = time.time()
        dt = max(1e-3, now - self.last_time)

        # Normalize edilmiş piksel hatası (-1.0 ile +1.0 arası)
        center_x = screen_w / 2.0
        center_y = screen_h / 2.0
        err_x = (target.merkez_x - center_x) / center_x
        err_y = (target.merkez_y - center_y) / center_y

        # Türev (Derivative)
        d_err_x = (err_x - self.last_err_x) / dt
        d_err_y = (err_y - self.last_err_y) / dt

        # PD Kontrol çıkışları
        # err_x pozitifse (hedef sağdaysa), sağa yatış/dönüş (yaw_cmd > 0)
        yaw_cmd = (self.kp_yaw * err_x) + (self.kd_yaw * d_err_x)
        # err_y pozitifse (hedef aşağıdaysa), burun aşağı (pitch_cmd < 0)
        pitch_cmd = -((self.kp_pitch * err_y) + (self.kd_pitch * d_err_y))

        # Limitler (-1.0 ile +1.0 normalizasyon)
        yaw_cmd = max(-1.0, min(1.0, yaw_cmd))
        pitch_cmd = max(-1.0, min(1.0, pitch_cmd))

        self.last_err_x = err_x
        self.last_err_y = err_y
        self.last_time = now

        return yaw_cmd, pitch_cmd


class ProportionalNavigation:
    """Hava-hava it dalaşı için Oransal Seyrüsefer (Proportional Navigation - PN) güdüm kanunu.
    
    Formül: a_cmd = N * V_c * lambda_dot
    Hedefin görüş hattı dönüş hızına (LOS rate) orantılı ivme üreterek rotasını keser.
    """

    def __init__(self, navigation_constant_N: float = 3.0):
        self.N = navigation_constant_N
        self.last_los_angle: Optional[float] = None
        self.last_time: float = time.time()

    def compute_heading_command(
        self,
        own_tel: TelemetriPaketi,
        rival: RakipIHABilgisi
    ) -> float:
        """Rakip İHA koordinatlarına göre en uygun önleme rotasını (bearing/heading) hesaplar."""
        now = time.time()
        dt = max(1e-3, now - self.last_time)

        # İki İHA arasındaki Line-of-Sight (Görüş Hattı / LOS) Açısı
        d_lat = rival.IHA_enlem - own_tel.IHA_enlem
        d_lon = rival.IHA_boylam - own_tel.IHA_boylam
        
        los_angle = math.atan2(d_lon, d_lat)  # Radyan

        if self.last_los_angle is None:
            self.last_los_angle = los_angle

        # LOS Dönüş Hızı (LOS Rate - lambda_dot)
        los_rate = (los_angle - self.last_los_angle) / dt

        # PN komutu: a = N * V * los_rate
        heading_correction_deg = math.degrees(self.N * los_rate * dt)
        desired_heading = (math.degrees(los_angle) + heading_correction_deg + 360.0) % 360.0

        self.last_los_angle = los_angle
        self.last_time = now

        return desired_heading


class PurePursuit:
    """Hedefin doğrudan arkasına veya anlık konumuna doğru yönelen Saf Takip algoritması."""

    @staticmethod
    def compute_heading(own_lat: float, own_lon: float, target_lat: float, target_lon: float) -> float:
        d_lat = target_lat - own_lat
        d_lon = target_lon - own_lon
        bearing_rad = math.atan2(d_lon, d_lat)
        return (math.degrees(bearing_rad) + 360.0) % 360.0


class FlightEnvelopeLimiter:
    """Manevralar sırasında uçağın perdövites (stall) olmasını ve aşırı G çekmesini önleyen uçuş zarfı denetleyicisi."""

    def __init__(self, max_bank_deg: float = 45.0, max_g_load: float = 2.5):
        self.max_bank_deg = max_bank_deg
        self.max_g_load = max_g_load
        self.g = 9.80665

    def calculate_coordinated_bank(self, groundspeed_m_s: float, turn_rate_deg_s: float) -> float:
        """Koordineli dönüş için gereken yatış açısını (bank angle) ve G yükünü hesaplar."""
        turn_rate_rad_s = math.radians(turn_rate_deg_s)
        # phi = atan(V * omega / g)
        bank_rad = math.atan((groundspeed_m_s * turn_rate_rad_s) / self.g)
        bank_deg = math.degrees(bank_rad)

        # Limit uygula
        limited_bank = max(-self.max_bank_deg, min(self.max_bank_deg, bank_deg))
        
        # G Yükü n = 1 / cos(phi)
        cos_phi = max(0.1, math.cos(math.radians(limited_bank)))
        g_load = 1.0 / cos_phi

        if g_load > self.max_g_load:
            limited_bank = math.copysign(math.degrees(math.acos(1.0 / self.max_g_load)), limited_bank)

        return limited_bank


class GuidanceController:
    """Tüm güdüm, saf takip ve hedef izleme mantığını koordine eden denetleyici."""

    def __init__(self, method: str = "visual_servoing", pn_N: float = 3.0):
        self.method = method
        self.visual_servoing = VisualServoingPID()
        self.pn = ProportionalNavigation(navigation_constant_N=pn_N)
        self.pure_pursuit = PurePursuit()
        self.envelope_limiter = FlightEnvelopeLimiter()

    def step_visual(self, target: HedefKutusu, screen_w: int, screen_h: int) -> Tuple[float, float]:
        return self.visual_servoing.compute_control_commands(target, screen_w, screen_h)

    def step_gps_pursuit(self, own_tel: TelemetriPaketi, rival: RakipIHABilgisi) -> float:
        if self.method == "pure_pursuit":
            return self.pure_pursuit.compute_heading(
                own_tel.IHA_enlem, own_tel.IHA_boylam,
                rival.IHA_enlem, rival.IHA_boylam
            )
        return self.pn.compute_heading_command(own_tel, rival)

    def compute_safe_bank(self, speed: float, turn_rate: float) -> float:
        return self.envelope_limiter.calculate_coordinated_bank(speed, turn_rate)
