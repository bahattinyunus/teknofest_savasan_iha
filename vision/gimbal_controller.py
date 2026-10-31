import math
import time
from typing import Tuple, Optional
from core.models import HedefKutusu
from core.logger import logger


class GimbalController:
    """2 Eksenli (Pan/Tilt) Kamera Gimbal Takip ve Stabilizasyon Kontrolcüsü.
    
    Uçak gövdesi manevra yaparken veya hedeften hafifçe saparken dahi kamerayı
    hedef İHA üzerinde kilitli tutmak için 2 eksenli fırçasız gimbal (Brushless Gimbal)
    açı ve açısal hız komutları üretir (MAVLink MAV_CMD_DO_MOUNT_CONTROL uyumlu).
    """

    def __init__(
        self,
        fov_h_deg: float = 78.0,
        fov_v_deg: float = 46.0,
        kp_pan: float = 0.45,
        ki_pan: float = 0.02,
        kd_pan: float = 0.05,
        kp_tilt: float = 0.45,
        ki_tilt: float = 0.02,
        kd_tilt: float = 0.05,
        pan_limit_deg: float = 60.0,
        tilt_min_deg: float = -45.0,
        tilt_max_deg: float = 25.0
    ):
        self.fov_h = fov_h_deg
        self.fov_v = fov_v_deg

        # Pan PID
        self.kp_pan = kp_pan
        self.ki_pan = ki_pan
        self.kd_pan = kd_pan

        # Tilt PID
        self.kp_tilt = kp_tilt
        self.ki_tilt = ki_tilt
        self.kd_tilt = kd_tilt

        # Limitler (derece)
        self.pan_limit_deg = pan_limit_deg
        self.tilt_min_deg = tilt_min_deg
        self.tilt_max_deg = tilt_max_deg

        # Durum değişkenleri
        self.current_pan_deg: float = 0.0
        self.current_tilt_deg: float = 0.0

        self.integral_pan: float = 0.0
        self.integral_tilt: float = 0.0
        self.last_err_pan: float = 0.0
        self.last_err_tilt: float = 0.0
        self.last_time: float = time.time()

    def reset(self):
        """Gimbalı merkez konumuna (0, 0) sıfırlar."""
        self.current_pan_deg = 0.0
        self.current_tilt_deg = 0.0
        self.integral_pan = 0.0
        self.integral_tilt = 0.0
        self.last_err_pan = 0.0
        self.last_err_tilt = 0.0
        self.last_time = time.time()

    def compute_gimbal_angles(
        self,
        target_box: Optional[HedefKutusu],
        frame_w: int,
        frame_h: int
    ) -> Tuple[float, float]:
        """Kamera kadrajındaki hedef merkez pikselinden hedef Pan ve Tilt açılarını hesaplar."""
        now = time.time()
        dt = max(1e-3, now - self.last_time)
        self.last_time = now

        if target_box is None:
            # Hedef yoksa gimbal yavaşça merkeze döner
            self.current_pan_deg *= 0.95
            self.current_tilt_deg *= 0.95
            return self.current_pan_deg, self.current_tilt_deg

        # Kadraj merkezine olan piksel sapması
        center_x = frame_w / 2.0
        center_y = frame_h / 2.0
        dx = target_box.merkez_x - center_x
        dy = target_box.merkez_y - center_y

        # Piksel sapmasını derece açı hatasına dönüştür (Pinhole kamera modeli)
        err_pan_deg = (dx / (frame_w / 2.0)) * (self.fov_h / 2.0)
        err_tilt_deg = -(dy / (frame_h / 2.0)) * (self.fov_v / 2.0)  # Yukarı pozitif

        # 1. Pan PID
        self.integral_pan += err_pan_deg * dt
        self.integral_pan = max(-15.0, min(15.0, self.integral_pan))  # Anti-windup
        d_pan = (err_pan_deg - self.last_err_pan) / dt

        pan_cmd = (self.kp_pan * err_pan_deg) + (self.ki_pan * self.integral_pan) + (self.kd_pan * d_pan)
        self.current_pan_deg += pan_cmd * dt

        # 2. Tilt PID
        self.integral_tilt += err_tilt_deg * dt
        self.integral_tilt = max(-15.0, min(15.0, self.integral_tilt))
        d_tilt = (err_tilt_deg - self.last_err_tilt) / dt

        tilt_cmd = (self.kp_tilt * err_tilt_deg) + (self.ki_tilt * self.integral_tilt) + (self.kd_tilt * d_tilt)
        self.current_tilt_deg += tilt_cmd * dt

        # Limitleri uygula
        self.current_pan_deg = max(-self.pan_limit_deg, min(self.pan_limit_deg, self.current_pan_deg))
        self.current_tilt_deg = max(self.tilt_min_deg, min(self.tilt_max_deg, self.current_tilt_deg))

        self.last_err_pan = err_pan_deg
        self.last_err_tilt = err_tilt_deg

        return round(self.current_pan_deg, 2), round(self.current_tilt_deg, 2)

    def get_mavlink_mount_command(self) -> Tuple[int, int, int]:
        """MAVLink MAV_CMD_DO_MOUNT_CONTROL için centi-degree (0.01 derece) formatında açıları döner."""
        pitch_cdeg = int(round(self.current_tilt_deg * 100))
        roll_cdeg = 0
        yaw_cdeg = int(round(self.current_pan_deg * 100))
        return pitch_cdeg, roll_cdeg, yaw_cdeg
