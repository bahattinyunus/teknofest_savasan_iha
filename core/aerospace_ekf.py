"""
AeroCombat - 15-Durumlu Havacılık Genişletilmiş Kalman Filtresi (15-State Aerospace EKF)

Hava muharebesi sırasında yüksek g-yükleri, ani virajlar ve GNSS karıştırması/kesintisi
altında İHA'nın 6-Serbestlik Dereceli (6-DOF) konum, hız, yönelim (Euler/Kuaterniyon)
ve sensör yanlılıklarını (bias) optimum seviyede kestiren havacılık standardı EKF motoru.

Durum Vektörü x (15 eleman):
  [0:3]   p_N, p_E, p_D        - NED Konum (metre)
  [3:6]   v_N, v_E, v_D        - NED Hız (m/s)
  [6:10]  q0, q1, q2, q3       - Yönelim Kuaterniyonu (Birim kuaterniyon)
  [10:13] b_ax, b_ay, b_az     - İvmeölçer Yanlılıkları (m/s^2)
  [13:16] b_gx, b_gy, b_gz     - Jiroskop Yanlılıkları (rad/s)
"""

import math
from typing import Tuple, List, Optional
import numpy as np

from core.models import EKFState6DOF
from core.logger import logger


class AerospaceEKF:
    """
    15-Durumlu Genişletilmiş Kalman Filtresi (6-DOF Strapdown INS/GNSS/Baro/VO Füzyonu).
    """

    GRAVITY: float = 9.80665

    def __init__(
        self,
        q_pos: float = 0.05,
        q_vel: float = 0.15,
        q_att: float = 0.005,
        q_acc_bias: float = 0.001,
        q_gyro_bias: float = 0.0001
    ):
        # Durum Boyutu: 16 (Kuaterniyon ile 16 eleman, ancak 15 bağımsız derece)
        self.state_dim = 16
        self.x = np.zeros(self.state_dim, dtype=np.float64)
        # Başlangıç kuaterniyonu: [1, 0, 0, 0] (Kimlik rotasyonu)
        self.x[6] = 1.0

        # Durum Kovaryans Matrisi P (16x16)
        self.P = np.eye(self.state_dim, dtype=np.float64) * 0.1
        self.P[0:3, 0:3] *= 5.0      # Konum belirsizliği
        self.P[3:6, 3:6] *= 1.0      # Hız belirsizliği
        self.P[6:10, 6:10] *= 0.05   # Açı belirsizliği
        self.P[10:13, 10:13] *= 0.1  # İvme bias belirsizliği
        self.P[13:16, 13:16] *= 0.01 # Jiroskop bias belirsizliği

        # Süreç Gürültüsü Q (16x16)
        self.Q = np.eye(self.state_dim, dtype=np.float64)
        self.Q[0:3, 0:3] *= q_pos ** 2
        self.Q[3:6, 3:6] *= q_vel ** 2
        self.Q[6:10, 6:10] *= q_att ** 2
        self.Q[10:13, 10:13] *= q_acc_bias ** 2
        self.Q[13:16, 13:16] *= q_gyro_bias ** 2

        # Sensör Ölçüm Varyansları
        self.r_gnss_pos = 2.5 ** 2      # GNSS yatay konum varyansı (m^2)
        self.r_gnss_vel = 0.35 ** 2     # GNSS hız varyansı ((m/s)^2)
        self.r_baro = 1.2 ** 2          # Barometre dikey irtifa varyansı (m^2)
        self.r_mag_yaw = (math.radians(2.5)) ** 2  # Manyetometre yön varyansı (rad^2)
        self.r_vo_vel = 0.45 ** 2       # Görsel odometri hız varyansı ((m/s)^2)

        self.last_timestamp: float = 0.0
        self.is_initialized: bool = False

    @staticmethod
    def quat_to_rot_matrix(q: np.ndarray) -> np.ndarray:
        """Kuaterniyondan gövde -> navigasyon (NED) rotasyon matrisini R_b^n üretir."""
        q0, q1, q2, q3 = q[0], q[1], q[2], q[3]
        return np.array([
            [q0*q0 + q1*q1 - q2*q2 - q3*q3, 2.0*(q1*q2 - q0*q3),         2.0*(q1*q3 + q0*q2)],
            [2.0*(q1*q2 + q0*q3),         q0*q0 - q1*q1 + q2*q2 - q3*q3, 2.0*(q2*q3 - q0*q1)],
            [2.0*(q1*q3 - q0*q2),         2.0*(q2*q3 + q0*q1),         q0*q0 - q1*q1 - q2*q2 + q3*q3]
        ], dtype=np.float64)

    @staticmethod
    def quat_to_euler(q: np.ndarray) -> Tuple[float, float, float]:
        """Kuaterniyonu Euler açılarına (Roll, Pitch, Yaw) çevirir (derece cinsinden)."""
        q0, q1, q2, q3 = q[0], q[1], q[2], q[3]

        # Roll (phi)
        sinr_cosp = 2.0 * (q0 * q1 + q2 * q3)
        cosr_cosp = 1.0 - 2.0 * (q1 * q1 + q2 * q2)
        roll = math.atan2(sinr_cosp, cosr_cosp)

        # Pitch (theta)
        sinp = 2.0 * (q0 * q2 - q3 * q1)
        if abs(sinp) >= 1.0:
            pitch = math.copysign(math.pi / 2.0, sinp)
        else:
            pitch = math.asin(sinp)

        # Yaw (psi)
        siny_cosp = 2.0 * (q0 * q3 + q1 * q2)
        cosy_cosp = 1.0 - 2.0 * (q2 * q2 + q3 * q3)
        yaw = math.atan2(siny_cosp, cosy_cosp)

        # 0-360 aralığına normalize et
        yaw_deg = math.degrees(yaw) % 360.0
        return math.degrees(roll), math.degrees(pitch), yaw_deg

    @staticmethod
    def euler_to_quat(roll_deg: float, pitch_deg: float, yaw_deg: float) -> np.ndarray:
        """Roll, Pitch, Yaw açılarından birim kuaterniyon [q0, q1, q2, q3] üretir."""
        r = math.radians(roll_deg) * 0.5
        p = math.radians(pitch_deg) * 0.5
        y = math.radians(yaw_deg) * 0.5

        cr = math.cos(r)
        sr = math.sin(r)
        cp = math.cos(p)
        sp = math.sin(p)
        cy = math.cos(y)
        sy = math.sin(y)

        q0 = cr * cp * cy + sr * sp * sy
        q1 = sr * cp * cy - cr * sp * sy
        q2 = cr * sp * cy + sr * cp * sy
        q3 = cr * cp * sy - sr * sp * cy
        return np.array([q0, q1, q2, q3], dtype=np.float64)

    def initialize_state(
        self,
        pos_ned: Tuple[float, float, float] = (0.0, 0.0, -50.0),
        vel_ned: Tuple[float, float, float] = (20.0, 0.0, 0.0),
        euler_deg: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        timestamp_s: float = 0.0
    ) -> None:
        """Başlangıç durumunu tanımlar."""
        self.x[0:3] = pos_ned
        self.x[3:6] = vel_ned
        self.x[6:10] = self.euler_to_quat(*euler_deg)
        self.x[10:13] = [0.0, 0.0, 0.0]  # Accel bias
        self.x[13:16] = [0.0, 0.0, 0.0]  # Gyro bias
        self.last_timestamp = timestamp_s
        self.is_initialized = True

    def predict(
        self,
        accel_body_mps2: Tuple[float, float, float],
        gyro_body_rads: Tuple[float, float, float],
        dt: float
    ) -> None:
        """
        EKF Zaman İlerlemesi (Prediction / Strapdown Mechanization).
        100 Hz IMU verisi ile durum ve kovaryansı geleceğe öteler.
        """
        if dt <= 0.0:
            return

        dt = min(0.1, dt)

        # 1. Sensör verisini yanlılıklardan (bias) arındır
        acc_raw = np.array(accel_body_mps2, dtype=np.float64)
        gyro_raw = np.array(gyro_body_rads, dtype=np.float64)

        acc_corr = acc_raw - self.x[10:13]
        gyro_corr = gyro_raw - self.x[13:16]

        # 2. Yönelim Kuaterniyonu İlerlemesi
        q = self.x[6:10]
        wx, wy, wz = gyro_corr[0], gyro_corr[1], gyro_corr[2]
        omega_mat = 0.5 * np.array([
            [0.0, -wx, -wy, -wz],
            [wx,  0.0,  wz, -wy],
            [wy, -wz,  0.0,  wx],
            [wz,  wy, -wx,  0.0]
        ], dtype=np.float64)

        q_new = q + np.dot(omega_mat, q) * dt
        q_norm = np.linalg.norm(q_new)
        if q_norm > 1e-8:
            q_new = q_new / q_norm
        self.x[6:10] = q_new

        # 3. İvmenin NED Çerçevesine Dönüştürülmesi
        r_bn = self.quat_to_rot_matrix(q_new)
        acc_ned = np.dot(r_bn, acc_corr)
        acc_ned[2] += self.GRAVITY  # Yerçekimi telafisi (NED +Z aşağı)

        # 4. Hız ve Konum Entegrasyonu
        self.x[0:3] += self.x[3:6] * dt + 0.5 * acc_ned * (dt ** 2)
        self.x[3:6] += acc_ned * dt

        # 5. Durum Geçiş Matrisi Yaklaşımı F ve Kovaryans Güncellemesi
        F = np.eye(self.state_dim, dtype=np.float64)
        F[0:3, 3:6] = np.eye(3) * dt
        # Basitleştirilmiş kovaryans ilerlemesi: P = F * P * F^T + Q
        self.P = np.dot(np.dot(F, self.P), F.T) + self.Q * dt

    def update_gnss(
        self,
        pos_ned_m: Tuple[float, float, float],
        vel_ned_mps: Tuple[float, float, float],
        gating_threshold: float = 18.0
    ) -> bool:
        """
        GNSS Konum ve Hız Ölçüm Güncellemesi (6 Ölçüm Durumu).
        Chi-Square / Mahalanobis İnovasyon Kapılaması (Gating) ile karıştırma ve sıçramaları eler.
        """
        z = np.array(list(pos_ned_m) + list(vel_ned_mps), dtype=np.float64)

        # Gözlem Matrisi H (6x16)
        H = np.zeros((6, self.state_dim), dtype=np.float64)
        H[0:3, 0:3] = np.eye(3)
        H[3:6, 3:6] = np.eye(3)

        # Ölçüm Kovaryansı R (6x6)
        R = np.eye(6, dtype=np.float64)
        R[0:3, 0:3] *= self.r_gnss_pos
        R[3:6, 3:6] *= self.r_gnss_vel

        # İnovasyon
        y = z - np.dot(H, self.x)

        # İnovasyon Kovaryansı S = H * P * H^T + R
        S = np.dot(np.dot(H, self.P), H.T) + R

        # Mahalanobis Kapılaması
        try:
            inv_S = np.linalg.inv(S)
            d2 = float(np.dot(np.dot(y.T, inv_S), y))
            if d2 > gating_threshold:
                # GNSS verisi fizik dışı veya aldatılmış (spoofing) olabilir; reddet
                return False
        except np.linalg.LinAlgError:
            return False

        # Kalman Kazancı K = P * H^T * inv(S)
        K = np.dot(np.dot(self.P, H.T), inv_S)

        # Durum Düzeltmesi
        self.x += np.dot(K, y)

        # Kuaterniyonu tekrar normalize et
        q_norm = np.linalg.norm(self.x[6:10])
        if q_norm > 1e-8:
            self.x[6:10] /= q_norm

        # Kovaryans Güncellemesi: P = (I - K * H) * P
        I_KH = np.eye(self.state_dim) - np.dot(K, H)
        self.P = np.dot(I_KH, self.P)
        return True

    def update_barometer(self, altitude_down_m: float) -> bool:
        """Barometrik dikey konum (NED Down ekseni) güncellemesi."""
        z = float(altitude_down_m)
        H = np.zeros((1, self.state_dim), dtype=np.float64)
        H[0, 2] = 1.0  # p_D durumu

        y = z - self.x[2]
        s = float(self.P[2, 2] + self.r_baro)
        if s <= 0:
            return False

        k = self.P[:, 2] / s
        self.x += k * y
        self.P -= np.outer(k, self.P[2, :])
        return True

    def update_visual_odometry(self, vel_ned_mps: Tuple[float, float, float]) -> bool:
        """GNSS kesintisi durumunda Görsel Odometri (VO) hız güncellemesi."""
        z = np.array(vel_ned_mps, dtype=np.float64)
        H = np.zeros((3, self.state_dim), dtype=np.float64)
        H[0:3, 3:6] = np.eye(3)

        R = np.eye(3, dtype=np.float64) * self.r_vo_vel
        y = z - self.x[3:6]
        S = self.P[3:6, 3:6] + R

        try:
            inv_S = np.linalg.inv(S)
        except np.linalg.LinAlgError:
            return False

        K = np.dot(self.P[:, 3:6], inv_S)
        self.x += np.dot(K, y)
        self.P -= np.dot(np.dot(K, H), self.P)
        return True

    def get_state(self, timestamp_s: float = 0.0) -> EKFState6DOF:
        """Kestirilen 15-durumlu filtre çıktısını yapısal nesne olarak döndürür."""
        roll, pitch, yaw = self.quat_to_euler(self.x[6:10])
        cov_diag = [float(self.P[i, i]) for i in range(self.state_dim)]

        return EKFState6DOF(
            pos_ned_m=[float(self.x[0]), float(self.x[1]), float(self.x[2])],
            vel_ned_mps=[float(self.x[3]), float(self.x[4]), float(self.x[5])],
            quat=[float(self.x[6]), float(self.x[7]), float(self.x[8]), float(self.x[9])],
            euler_deg=[float(roll), float(pitch), float(yaw)],
            accel_bias=[float(self.x[10]), float(self.x[11]), float(self.x[12])],
            gyro_bias=[float(self.x[13]), float(self.x[14]), float(self.x[15])],
            covariance_diag=cov_diag,
            timestamp_s=timestamp_s
        )
