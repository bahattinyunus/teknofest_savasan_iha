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
    """Hava-hava it dalaşı için Oransal Seyrüsefer (Proportional Navigation - PN) güdüm kanunu."""

    def __init__(self, navigation_constant_N: float = 3.0):
        self.N = navigation_constant_N
        self.last_los_angle: Optional[float] = None
        self.last_time: float = time.time()

    def compute_heading_command(
        self,
        own_tel: TelemetriPaketi,
        rival: RakipIHABilgisi
    ) -> float:
        """Rakip İHA koordinatlarına göre en uygun rotayı (bearing/heading) hesaplar."""
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


class GuidanceController:
    """Tüm güdüm ve hedef takip mantığını koordine eden denetleyici."""

    def __init__(self, method: str = "visual_servoing", pn_N: float = 3.0):
        self.method = method
        self.visual_servoing = VisualServoingPID()
        self.pn = ProportionalNavigation(navigation_constant_N=pn_N)

    def step_visual(self, target: HedefKutusu, screen_w: int, screen_h: int) -> Tuple[float, float]:
        return self.visual_servoing.compute_control_commands(target, screen_w, screen_h)

    def step_gps_pursuit(self, own_tel: TelemetriPaketi, rival: RakipIHABilgisi) -> float:
        return self.pn.compute_heading_command(own_tel, rival)
