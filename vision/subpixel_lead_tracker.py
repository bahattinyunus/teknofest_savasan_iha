import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import numpy as np

from core.models import HedefKutusu


@dataclass
class SubPixelLeadSolution:
    """Kalman alt-piksel iyileştirme ve 3D dinamik nişangah önleme (Lead Reticle) çözümü."""
    refined_box: HedefKutusu
    subpixel_center_xy: Tuple[float, float]
    lead_reticle_xy: Tuple[float, float]
    lead_offset_px: Tuple[float, float]
    ego_rotation_delta_px: Tuple[float, float]
    stabilized_area_ratio_pct: float
    jitter_reduction_db: float
    is_within_5_percent_rule: bool


class SubPixelDynamicLeadCompensator:
    """Alt-Piksel (Sub-Pixel) Kutu Sabitleyici, Kendi Açısal Hız (Ego-Motion p,q,r)
    Kompanzatörü ve Dinamik Önleme Nişangahı (Dynamic Lead Reticle) Motoru.

    TEKNOFEST Savaşan İHA yarışmasında:
      1. Kendi İHA'mızın anlık açısal dönüş hızlarından (roll_rate p, pitch_rate q, yaw_rate r)
         kaynaklanan görünür piksel kaymasını (Ego-Motion Optical Rotation) hesaplayıp
         gerçek hedef hızından ayırır,
      2. YOLO bounding box köşelerindeki yüksek frekanslı kuantizasyon titremesini
         (box jitter) iki aşamalı adaptif alt-piksel Kalman süzgeciyle bastırarak
         `%5` alan kuralı sınırındaki hedeflerin kilit düşürmesini önler,
      3. Sistem gecikmesi + otopilot servo tepki süresi ($\tau_{\text{lead}}$) kadar
         sonraki alt-piksel önleme noktasını (Dynamic Lead Reticle) hesaplar.
    """

    def __init__(
        self,
        frame_width: int = 1280,
        frame_height: int = 720,
        hfov_deg: float = 78.0,
        vfov_deg: float = 46.0,
        lead_horizon_s: float = 0.14,
        smoothing_alpha: float = 0.62
    ):
        self.w = float(frame_width)
        self.h = float(frame_height)
        self.hfov_rad = math.radians(float(hfov_deg))
        self.vfov_rad = math.radians(float(vfov_deg))
        self.lead_horizon_s = float(lead_horizon_s)
        self.alpha = float(smoothing_alpha)

        # Odak uzaklığı (piksel)
        self.fx = (self.w / 2.0) / math.tan(self.hfov_rad / 2.0)
        self.fy = (self.h / 2.0) / math.tan(self.vfov_rad / 2.0)

        # Hedef ID başına alt-piksel durum hafızası: [cx, cy, bw, bh, vx, vy]
        self._states: Dict[int, np.ndarray] = {}
        self._raw_jitter_var: Dict[int, float] = {}
        self._smooth_jitter_var: Dict[int, float] = {}

    def compute_ego_motion_pixel_shift(
        self,
        target_cx: float,
        target_cy: float,
        own_p_rad_s: float,
        own_q_rad_s: float,
        own_r_rad_s: float,
        dt: float
    ) -> Tuple[float, float]:
        """Pinhole kamera rotasyonel optik akış denklemiyle kendi açısal hızlarımızın (p,q,r)
        ekranda yarattığı görünür piksel yer değiştirmesini hesaplar:
          u_dot_ego = -fx * r + (u * v / fy) * q - fx * (1 + u^2 / fx^2) * r + v * p
        """
        u = target_cx - (self.w / 2.0)
        v = target_cy - (self.h / 2.0)

        # Yaw (r), Pitch (q) ve Roll (p) kaynaklı görüntü düzlemi hızı
        du_dt = -self.fx * (1.0 + (u * u) / (self.fx * self.fx)) * own_r_rad_s + ((u * v) / self.fy) * own_q_rad_s + v * own_p_rad_s
        dv_dt = -self.fy * (1.0 + (v * v) / (self.fy * self.fy)) * own_q_rad_s + ((u * v) / self.fx) * own_r_rad_s - u * own_p_rad_s

        return (float(du_dt * dt), float(dv_dt * dt))

    def refine_and_compute_lead(
        self,
        box: HedefKutusu,
        dt: float = 0.033,
        own_p_rad_s: float = 0.0,
        own_q_rad_s: float = 0.0,
        own_r_rad_s: float = 0.0
    ) -> SubPixelLeadSolution:
        """Hedef kutusunu alt-piksel hassasiyetinde stabilize eder ve dinamik önleme nişangahını üretir."""
        dt = max(1e-3, float(dt))
        tid = box.track_id if box.track_id is not None else 0

        raw_cx = box.merkez_x
        raw_cy = box.merkez_y
        raw_w = box.genislik
        raw_h = box.yukseklik

        ego_dx, ego_dy = self.compute_ego_motion_pixel_shift(
            target_cx=raw_cx,
            target_cy=raw_cy,
            own_p_rad_s=own_p_rad_s,
            own_q_rad_s=own_q_rad_s,
            own_r_rad_s=own_r_rad_s,
            dt=dt
        )

        if tid not in self._states:
            self._states[tid] = np.array([raw_cx, raw_cy, raw_w, raw_h, 0.0, 0.0], dtype=np.float64)
            self._raw_jitter_var[tid] = 4.0
            self._smooth_jitter_var[tid] = 1.0
            state = self._states[tid]
        else:
            prev = self._states[tid]
            # Ego-motion etkisinden arındırılmış gerçek hedef piksel hızı
            true_vx = ((raw_cx - prev[0]) - ego_dx) / dt
            true_vy = ((raw_cy - prev[1]) - ego_dy) / dt

            pred_cx = prev[0] + prev[4] * dt + ego_dx
            pred_cy = prev[1] + prev[5] * dt + ego_dy

            raw_err_sq = (raw_cx - pred_cx) ** 2 + (raw_cy - pred_cy) ** 2
            self._raw_jitter_var[tid] = 0.85 * self._raw_jitter_var[tid] + 0.15 * max(0.5, raw_err_sq)

            # Alt-piksel filtreleme
            new_cx = self.alpha * raw_cx + (1.0 - self.alpha) * pred_cx
            new_cy = self.alpha * raw_cy + (1.0 - self.alpha) * pred_cy
            # Boyut (genişlik/yükseklik) daha sıkı filtrelenir (%5 alan kuralı kararlılığı için)
            new_w = 0.45 * raw_w + 0.55 * prev[2]
            new_h = 0.45 * raw_h + 0.55 * prev[3]
            new_vx = 0.55 * prev[4] + 0.45 * true_vx
            new_vy = 0.55 * prev[5] + 0.45 * true_vy

            smooth_err_sq = (new_cx - pred_cx) ** 2 + (new_cy - pred_cy) ** 2
            self._smooth_jitter_var[tid] = 0.85 * self._smooth_jitter_var[tid] + 0.15 * max(0.05, smooth_err_sq)

            state = np.array([new_cx, new_cy, new_w, new_h, new_vx, new_vy], dtype=np.float64)
            self._states[tid] = state

        cx, cy, bw, bh, vx, vy = state

        # Dinamik Önleme Nişangahı (Lead Reticle)
        lead_dx = float(np.clip(vx * self.lead_horizon_s, -160.0, 160.0))
        lead_dy = float(np.clip(vy * self.lead_horizon_s, -110.0, 110.0))
        lead_x = float(np.clip(cx + lead_dx, 0.0, self.w))
        lead_y = float(np.clip(cy + lead_dy, 0.0, self.h))

        refined_box = HedefKutusu(
            x1=round(float(cx - bw / 2.0), 3),
            y1=round(float(cy - bh / 2.0), 3),
            x2=round(float(cx + bw / 2.0), 3),
            y2=round(float(cy + bh / 2.0), 3),
            conf=box.conf,
            track_id=box.track_id,
            class_id=box.class_id,
            class_name=box.class_name
        )

        area_ratio = refined_box.alan_orani(self.w, self.h)
        ratio_var = max(1.0, self._raw_jitter_var[tid] / max(1e-3, self._smooth_jitter_var[tid]))
        jitter_db = 10.0 * math.log10(ratio_var)

        return SubPixelLeadSolution(
            refined_box=refined_box,
            subpixel_center_xy=(round(float(cx), 3), round(float(cy), 3)),
            lead_reticle_xy=(round(lead_x, 3), round(lead_y, 3)),
            lead_offset_px=(round(lead_dx, 3), round(lead_dy, 3)),
            ego_rotation_delta_px=(round(ego_dx, 3), round(ego_dy, 3)),
            stabilized_area_ratio_pct=round(float(area_ratio * 100.0), 3),
            jitter_reduction_db=round(float(jitter_db), 2),
            is_within_5_percent_rule=bool(area_ratio >= 0.05)
        )
