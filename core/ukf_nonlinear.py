import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import numpy as np


@dataclass
class UKFTargetState:
    """7-Durumlu [N, E, D, V_horiz, psi_rad, omega_rad_s, V_z] UKF 3D hedef kestirimi."""
    pos_ned_m: Tuple[float, float, float]
    vel_ned_mps: Tuple[float, float, float]
    horizontal_speed_mps: float
    heading_deg: float
    turn_rate_deg_s: float
    vertical_speed_mps: float
    predicted_pos_ned_m: Tuple[float, float, float]
    covariance_trace: float


class UnscentedKalmanFilter3D:
    """Doğrusal Olmayan (Non-Linear) Koordineli Dönüş (CTRV) Modeli İçin
    Sigma-Noktalı Unscented Kalman Filter (UKF - Julier & Uhlmann Scaled Unscented Transform).

    Durum Vektörü (n = 7):
      x = [p_n, p_e, p_d, v_h, psi, omega, v_d]^T
    Ölçüm Vektörü (m = 4):
      z = [azimuth_rad, elevation_rad, range_m, altitude_d_m]^T
      (Kamera doğrultu açıları + optik menzil + hakem telemetrisi füzyonu)
    Jakobiyen doğrusallaştırma hatası olmadan 2n+1 = 15 Sigma Noktasını doğrudan
    non-linear kinematik ve küresel kamera gözlem denklemlerinden geçirir.
    """

    def __init__(
        self,
        alpha: float = 0.25,
        beta: float = 2.0,
        kappa: float = 0.0,
        angle_noise_rad: float = 0.025,
        range_noise_m: float = 2.2
    ):
        self.n = 7
        self.m = 4
        self.alpha = float(alpha)
        self.beta = float(beta)
        self.kappa = float(kappa)

        self.lam = (self.alpha ** 2) * (self.n + self.kappa) - self.n
        self.num_sigma = 2 * self.n + 1

        # Ağırlık vektörleri (Wm: ortalama, Wc: kovaryans)
        self.Wm = np.full(self.num_sigma, 1.0 / (2.0 * (self.n + self.lam)), dtype=np.float64)
        self.Wc = self.Wm.copy()
        self.Wm[0] = self.lam / (self.n + self.lam)
        self.Wc[0] = self.Wm[0] + (1.0 - self.alpha ** 2 + self.beta)

        self.x = np.array([40.0, 0.0, -80.0, 20.0, 0.0, 0.0, 0.0], dtype=np.float64)
        self.P = np.diag([16.0, 16.0, 16.0, 9.0, 0.25, 0.10, 4.0]).astype(np.float64)

        self.R = np.diag([
            angle_noise_rad ** 2,
            angle_noise_rad ** 2,
            range_noise_m ** 2,
            (range_noise_m * 0.8) ** 2
        ]).astype(np.float64)
        self._initialized = False

    def initialize(
        self,
        pos_ned_m: Tuple[float, float, float],
        vel_ned_mps: Tuple[float, float, float] = (20.0, 0.0, 0.0),
        turn_rate_rad_s: float = 0.0
    ) -> None:
        vh = math.hypot(vel_ned_mps[0], vel_ned_mps[1])
        psi = math.atan2(vel_ned_mps[1], vel_ned_mps[0])
        self.x = np.array([
            pos_ned_m[0],
            pos_ned_m[1],
            pos_ned_m[2],
            max(5.0, vh),
            psi,
            turn_rate_rad_s,
            vel_ned_mps[2]
        ], dtype=np.float64)
        self.P = np.diag([9.0, 9.0, 9.0, 4.0, 0.15, 0.08, 2.0]).astype(np.float64)
        self._initialized = True

    def _generate_sigma_points(self, x: np.ndarray, P: np.ndarray) -> np.ndarray:
        """Cholesky ayrıştırması ile 2n+1 = 15 Sigma Noktası üretir."""
        sigma_pts = np.zeros((self.num_sigma, self.n), dtype=np.float64)
        sigma_pts[0] = x
        scale = self.n + self.lam
        P_sym = 0.5 * (P + P.T) + np.eye(self.n) * 1e-6
        try:
            L = np.linalg.cholesky(scale * P_sym)
        except np.linalg.LinAlgError:
            eigvals, eigvecs = np.linalg.eigh(scale * P_sym)
            eigvals = np.maximum(eigvals, 1e-6)
            L = eigvecs @ np.diag(np.sqrt(eigvals))

        for i in range(self.n):
            col = L[:, i]
            sigma_pts[i + 1] = x + col
            sigma_pts[self.n + i + 1] = x - col
        return sigma_pts

    @staticmethod
    def _f_ctrv(state: np.ndarray, dt: float) -> np.ndarray:
        """Non-linear CTRV (Constant Turn Rate and Velocity) durum geçiş fonksiyonu."""
        pn, pe, pd, vh, psi, omega, vd = state
        vh = max(5.0, min(50.0, float(vh)))
        omega = max(-1.5, min(1.5, float(omega)))

        if abs(omega) < 1e-4:
            pn_new = pn + vh * math.cos(psi) * dt
            pe_new = pe + vh * math.sin(psi) * dt
        else:
            pn_new = pn + (vh / omega) * (math.sin(psi + omega * dt) - math.sin(psi))
            pe_new = pe + (vh / omega) * (-math.cos(psi + omega * dt) + math.cos(psi))

        pd_new = pd + vd * dt
        psi_new = (psi + omega * dt + math.pi) % (2.0 * math.pi) - math.pi
        return np.array([pn_new, pe_new, pd_new, vh, psi_new, omega, vd], dtype=np.float64)

    @staticmethod
    def _h_spherical(state: np.ndarray, own_pos_ned: np.ndarray) -> np.ndarray:
        """Durum uzayından küresel kamera doğrultu + menzil gözlem uzayına dönüşüm."""
        dn = state[0] - own_pos_ned[0]
        de = state[1] - own_pos_ned[1]
        dd = state[2] - own_pos_ned[2]

        horiz_dist = math.hypot(dn, de) + 1e-6
        dist_3d = math.sqrt(dn * dn + de * de + dd * dd) + 1e-6

        az = math.atan2(de, dn)
        el = math.atan2(-dd, horiz_dist)
        return np.array([az, el, dist_3d, state[2]], dtype=np.float64)

    def step(
        self,
        measured_pos_ned_m: Tuple[float, float, float],
        own_pos_ned_m: Tuple[float, float, float] = (0.0, 0.0, -80.0),
        dt: float = 0.05,
        prediction_horizon_s: float = 1.5
    ) -> UKFTargetState:
        """UKF Sigma-Noktası yayılımı (Predict) ve küresel ölçüm güncellemesi (Update)."""
        dt = max(1e-3, float(dt))
        own_p = np.array(own_pos_ned_m, dtype=np.float64)
        meas_p = np.array(measured_pos_ned_m, dtype=np.float64)

        if not self._initialized:
            self.initialize(measured_pos_ned_m)

        # 1. Sigma noktalarını üret ve non-linear CTRV modelinden geçir
        sigmas = self._generate_sigma_points(self.x, self.P)
        sigmas_pred = np.array([self._f_ctrv(s, dt) for s in sigmas], dtype=np.float64)

        # Açısal değişken psi (indeks 4) için dairesel ortalama (circular mean)
        x_pred = np.tensordot(self.Wm, sigmas_pred, axes=(0, 0))
        sin_sum = float(np.sum(self.Wm * np.sin(sigmas_pred[:, 4])))
        cos_sum = float(np.sum(self.Wm * np.cos(sigmas_pred[:, 4])))
        x_pred[4] = math.atan2(sin_sum, cos_sum)

        Q = np.diag([
            (0.6 * dt) ** 2,
            (0.6 * dt) ** 2,
            (0.5 * dt) ** 2,
            (1.2 * dt) ** 2,
            (0.15 * dt) ** 2,
            (0.25 * dt) ** 2,
            (0.8 * dt) ** 2
        ]).astype(np.float64)

        P_pred = Q.copy()
        for i in range(self.num_sigma):
            dx = sigmas_pred[i] - x_pred
            dx[4] = (dx[4] + math.pi) % (2.0 * math.pi) - math.pi
            P_pred += self.Wc[i] * np.outer(dx, dx)

        # 2. Ölçüm Sigma Noktaları (Küresel Azimut, Elevasyon, Menzil, İrtifa)
        z_sigmas = np.array([self._h_spherical(s, own_p) for s in sigmas_pred], dtype=np.float64)
        z_pred = np.tensordot(self.Wm, z_sigmas, axes=(0, 0))
        z_sin = float(np.sum(self.Wm * np.sin(z_sigmas[:, 0])))
        z_cos = float(np.sum(self.Wm * np.cos(z_sigmas[:, 0])))
        z_pred[0] = math.atan2(z_sin, z_cos)

        S = self.R.copy()
        P_xz = np.zeros((self.n, self.m), dtype=np.float64)
        for i in range(self.num_sigma):
            dz = z_sigmas[i] - z_pred
            dz[0] = (dz[0] + math.pi) % (2.0 * math.pi) - math.pi
            dx = sigmas_pred[i] - x_pred
            dx[4] = (dx[4] + math.pi) % (2.0 * math.pi) - math.pi
            S += self.Wc[i] * np.outer(dz, dz)
            P_xz += self.Wc[i] * np.outer(dx, dz)

        # Gerçek ölçüm vektörünü küresel uzaya dönüştür
        z_actual = self._h_spherical(
            np.array([meas_p[0], meas_p[1], meas_p[2], 0, 0, 0, 0], dtype=np.float64),
            own_p
        )
        y_innov = z_actual - z_pred
        y_innov[0] = (y_innov[0] + math.pi) % (2.0 * math.pi) - math.pi

        try:
            S_inv = np.linalg.inv(S)
        except np.linalg.LinAlgError:
            S_inv = np.eye(self.m)

        K = P_xz @ S_inv
        self.x = x_pred + K @ y_innov
        self.x[3] = max(5.0, min(50.0, float(self.x[3])))
        self.x[4] = (float(self.x[4]) + math.pi) % (2.0 * math.pi) - math.pi
        self.x[5] = max(-1.5, min(1.5, float(self.x[5])))
        self.P = P_pred - K @ S @ K.T

        # Çıktı durum vektörünü oluştur
        pn, pe, pd, vh, psi, omega, vd = self.x
        vn = vh * math.cos(psi)
        ve = vh * math.sin(psi)

        future_s = self._f_ctrv(self.x, prediction_horizon_s)
        cov_trace = float(np.trace(self.P[0:3, 0:3]))

        return UKFTargetState(
            pos_ned_m=(round(float(pn), 2), round(float(pe), 2), round(float(pd), 2)),
            vel_ned_mps=(round(float(vn), 2), round(float(ve), 2), round(float(vd), 2)),
            horizontal_speed_mps=round(float(vh), 2),
            heading_deg=round((math.degrees(float(psi)) + 360.0) % 360.0, 2),
            turn_rate_deg_s=round(math.degrees(float(omega)), 2),
            vertical_speed_mps=round(float(vd), 2),
            predicted_pos_ned_m=(
                round(float(future_s[0]), 2),
                round(float(future_s[1]), 2),
                round(float(future_s[2]), 2)
            ),
            covariance_trace=round(max(0.0, cov_trace), 3)
        )
