import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
import numpy as np


class FlightModelMode(Enum):
    """IMM çoklu model durum tanımlayıcıları."""
    CONSTANT_VELOCITY = "CV"            # Sabit Hızlı Doğrusal Uçuş (Düz Seyir)
    COORDINATED_TURN_LEFT = "CT_LEFT"   # Koordineli Sola Yatışlı Dönüş (It Dalaşı)
    COORDINATED_TURN_RIGHT = "CT_RIGHT" # Koordineli Sağa Yatışlı Dönüş (It Dalaşı)
    CONSTANT_ACCELERATION = "CA"        # Sabit İvmeli (Ani Tırmanış / Dalış / Kaçış)


@dataclass
class IMMTargetEstimate:
    """IMM filtresinden çıkan birleştirilmiş 3D hedef durum ve manevra kestirimi."""
    target_id: int
    pos_ned_m: Tuple[float, float, float]
    vel_ned_mps: Tuple[float, float, float]
    acc_ned_mps2: Tuple[float, float, float]
    model_probabilities: Dict[str, float]
    dominant_mode: FlightModelMode
    estimated_turn_rate_rad_s: float
    estimated_g_load: float
    predicted_pos_ned_m: Tuple[float, float, float]
    position_uncertainty_m: float


class _SubModelKalman:
    """IMM içindeki tekil 9-Durumlu [x, y, z, vx, vy, vz, ax, ay, az] Kalman alt filtresi."""

    def __init__(self, mode: FlightModelMode, turn_rate_rad_s: float = 0.0, process_noise: float = 1.5):
        self.mode = mode
        self.omega = turn_rate_rad_s
        self.q_std = process_noise
        self.x = np.zeros(9, dtype=np.float64)
        self.P = np.eye(9, dtype=np.float64) * 25.0

    def get_transition_matrix(self, dt: float) -> np.ndarray:
        F = np.eye(9, dtype=np.float64)
        if self.mode == FlightModelMode.CONSTANT_VELOCITY:
            F[0, 3] = dt
            F[1, 4] = dt
            F[2, 5] = dt
            # İvme sönümlenir
            F[6, 6] = 0.2
            F[7, 7] = 0.2
            F[8, 8] = 0.2
        elif self.mode in (FlightModelMode.COORDINATED_TURN_LEFT, FlightModelMode.COORDINATED_TURN_RIGHT):
            w = self.omega
            if abs(w) < 1e-4:
                F[0, 3] = dt
                F[1, 4] = dt
            else:
                sin_wt = math.sin(w * dt)
                cos_wt = math.cos(w * dt)
                F[0, 3] = sin_wt / w
                F[0, 4] = -(1.0 - cos_wt) / w
                F[1, 3] = (1.0 - cos_wt) / w
                F[1, 4] = sin_wt / w
                F[3, 3] = cos_wt
                F[3, 4] = -sin_wt
                F[4, 3] = sin_wt
                F[4, 4] = cos_wt
            F[2, 5] = dt
            # Merkezcil ivme temsili: a_n = -w * v_e, a_e = +w * v_n
            F[6, 4] = -w
            F[7, 3] = +w
            F[6, 6] = 0.0
            F[7, 7] = 0.0
        elif self.mode == FlightModelMode.CONSTANT_ACCELERATION:
            dt2 = 0.5 * dt * dt
            F[0, 3] = dt
            F[1, 4] = dt
            F[2, 5] = dt
            F[0, 6] = dt2
            F[1, 7] = dt2
            F[2, 8] = dt2
            F[3, 6] = dt
            F[4, 7] = dt
            F[5, 8] = dt
        return F

    def predict(self, dt: float) -> None:
        F = self.get_transition_matrix(dt)
        self.x = F @ self.x
        Q = np.eye(9, dtype=np.float64) * (self.q_std * dt) ** 2
        Q[3:6, 3:6] *= 4.0
        Q[6:9, 6:9] *= 9.0
        self.P = F @ self.P @ F.T + Q

    def update(self, z_pos: np.ndarray, R: np.ndarray) -> float:
        """3D konum ölçümü [N, E, D] ile günceller ve olabilirlik (likelihood) döndürür."""
        H = np.zeros((3, 9), dtype=np.float64)
        H[0, 0] = 1.0
        H[1, 1] = 1.0
        H[2, 2] = 1.0

        y = z_pos - (H @ self.x)
        S = H @ self.P @ H.T + R
        try:
            S_inv = np.linalg.inv(S)
            det_S = max(1e-12, float(np.linalg.det(S)))
        except np.linalg.LinAlgError:
            S_inv = np.eye(3)
            det_S = 1.0

        mahalanobis_sq = float(y.T @ S_inv @ y)
        # Çok değişkenli Gauss olabilirliği
        norm_factor = 1.0 / math.sqrt(((2.0 * math.pi) ** 3) * det_S)
        likelihood = max(1e-15, norm_factor * math.exp(-0.5 * min(50.0, mahalanobis_sq)))

        K = self.P @ H.T @ S_inv
        self.x = self.x + (K @ y)
        I_KH = np.eye(9) - (K @ H)
        self.P = I_KH @ self.P
        return likelihood


class InteractingMultipleModelFilter:
    """Hedef İHA'lar için Etkileşimli Çoklu Model (IMM) 3D Manevra Takipçisi.

    4 paralel kinematik modeli (CV, CT-Left, CT-Right, CA) Markov geçiş olasılık
    matrisi üzerinden kaynaştırarak sert BFM/it dalaşı manevralarında sıfır gecikmeli
    durum ve gelecek yörünge tahmini üretir.
    """

    def __init__(
        self,
        target_id: int = 1,
        turn_rate_deg_s: float = 28.0,
        measurement_noise_m: float = 2.0
    ):
        self.target_id = target_id
        omega_rad = math.radians(abs(turn_rate_deg_s))
        self.measurement_noise_m = measurement_noise_m

        self.models: List[_SubModelKalman] = [
            _SubModelKalman(FlightModelMode.CONSTANT_VELOCITY, 0.0, process_noise=0.4),
            _SubModelKalman(FlightModelMode.COORDINATED_TURN_LEFT, -omega_rad, process_noise=0.6),
            _SubModelKalman(FlightModelMode.COORDINATED_TURN_RIGHT, +omega_rad, process_noise=0.6),
            _SubModelKalman(FlightModelMode.CONSTANT_ACCELERATION, 0.0, process_noise=1.2),
        ]
        self.num_models = len(self.models)

        # Model olasılık vektörü (başlangıçta düz uçuş ağırlıklı)
        self.mu = np.array([0.55, 0.15, 0.15, 0.15], dtype=np.float64)

        # Markov model geçiş olasılık matrisi (p_ij: model i'den j'ye geçiş)
        self.PI = np.array([
            [0.82, 0.06, 0.06, 0.06],
            [0.10, 0.78, 0.04, 0.08],
            [0.10, 0.04, 0.78, 0.08],
            [0.12, 0.09, 0.09, 0.70],
        ], dtype=np.float64)

        self.x_merged = np.zeros(9, dtype=np.float64)
        self.P_merged = np.eye(9, dtype=np.float64) * 25.0
        self._initialized = False

    def initialize(
        self,
        pos_ned_m: Tuple[float, float, float],
        vel_ned_mps: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    ) -> None:
        init_x = np.zeros(9, dtype=np.float64)
        init_x[0:3] = pos_ned_m
        init_x[3:6] = vel_ned_mps
        for m in self.models:
            m.x = init_x.copy()
            m.P = np.eye(9, dtype=np.float64) * 10.0
        self.x_merged = init_x.copy()
        self._initialized = True

    def step(
        self,
        measured_pos_ned_m: Tuple[float, float, float],
        dt: float = 0.05,
        prediction_horizon_s: float = 1.5
    ) -> IMMTargetEstimate:
        """Tek bir ölçüm adımında IMM Karıştırma -> Tahmin -> Güncelleme -> Birleştirme döngüsü."""
        dt = max(1e-3, float(dt))
        z = np.array(measured_pos_ned_m, dtype=np.float64)

        if not self._initialized:
            self.initialize(measured_pos_ned_m)

        # 1. Etkileşim / Karıştırma (Interaction / Mixing)
        c_bar = self.PI.T @ self.mu
        c_bar = np.maximum(c_bar, 1e-12)

        mu_ij = np.zeros((self.num_models, self.num_models), dtype=np.float64)
        for i in range(self.num_models):
            for j in range(self.num_models):
                mu_ij[i, j] = (self.PI[i, j] * self.mu[i]) / c_bar[j]

        mixed_x = []
        mixed_P = []
        for j in range(self.num_models):
            xj = np.zeros(9, dtype=np.float64)
            for i in range(self.num_models):
                xj += mu_ij[i, j] * self.models[i].x
            Pj = np.zeros((9, 9), dtype=np.float64)
            for i in range(self.num_models):
                diff = (self.models[i].x - xj).reshape(-1, 1)
                Pj += mu_ij[i, j] * (self.models[i].P + diff @ diff.T)
            mixed_x.append(xj)
            mixed_P.append(Pj)

        for j in range(self.num_models):
            self.models[j].x = mixed_x[j]
            self.models[j].P = mixed_P[j]

        # 2. Alt Modellerin Tahmin ve Ölçüm Güncellemesi
        R = np.eye(3, dtype=np.float64) * (self.measurement_noise_m ** 2)
        likelihoods = np.zeros(self.num_models, dtype=np.float64)

        for j, model in enumerate(self.models):
            model.predict(dt)
            likelihoods[j] = model.update(z, R)

        # 3. Model Olasılıklarının Güncellenmesi
        weighted_likelihoods = c_bar * likelihoods
        total_prob = float(np.sum(weighted_likelihoods))
        if total_prob > 1e-15:
            self.mu = weighted_likelihoods / total_prob
        else:
            self.mu = np.ones(self.num_models) / self.num_models

        # 4. Durum ve Kovaryans Birleştirme (Combination)
        self.x_merged = np.zeros(9, dtype=np.float64)
        for j in range(self.num_models):
            self.x_merged += self.mu[j] * self.models[j].x

        self.P_merged = np.zeros((9, 9), dtype=np.float64)
        for j in range(self.num_models):
            diff = (self.models[j].x - self.x_merged).reshape(-1, 1)
            self.P_merged += self.mu[j] * (self.models[j].P + diff @ diff.T)

        # 5. Gelecek Konum ve Manevra Analizi
        dominant_idx = int(np.argmax(self.mu))
        dominant_mode = self.models[dominant_idx].mode

        pos = tuple(float(v) for v in self.x_merged[0:3])
        vel = tuple(float(v) for v in self.x_merged[3:6])
        acc = tuple(float(v) for v in self.x_merged[6:9])

        # Yatay düzlem açısal dönüş hızı (omega = (vx*ay - vy*ax) / (vx^2 + vy^2))
        v_horiz_sq = vel[0] ** 2 + vel[1] ** 2
        if v_horiz_sq > 4.0:
            est_turn_rate = (vel[0] * acc[1] - vel[1] * acc[0]) / v_horiz_sq
        else:
            est_turn_rate = float(self.models[dominant_idx].omega * self.mu[dominant_idx])

        # Toplam ivmeden G yükü kestirimi
        acc_mag = math.sqrt(acc[0] ** 2 + acc[1] ** 2 + acc[2] ** 2)
        est_g = 1.0 + (acc_mag / 9.80665)

        pred_pos = self.predict_future_position(prediction_horizon_s)
        pos_unc = float(math.sqrt(max(0.0, np.trace(self.P_merged[0:3, 0:3]) / 3.0)))

        prob_dict = {
            self.models[j].mode.value: round(float(self.mu[j]), 4)
            for j in range(self.num_models)
        }

        return IMMTargetEstimate(
            target_id=self.target_id,
            pos_ned_m=pos,
            vel_ned_mps=vel,
            acc_ned_mps2=acc,
            model_probabilities=prob_dict,
            dominant_mode=dominant_mode,
            estimated_turn_rate_rad_s=round(float(est_turn_rate), 4),
            estimated_g_load=round(float(est_g), 2),
            predicted_pos_ned_m=pred_pos,
            position_uncertainty_m=round(pos_unc, 3)
        )

    def predict_future_position(self, horizon_s: float) -> Tuple[float, float, float]:
        """Olasılık ağırlıklı çoklu model geçiş matrisleriyle T saniye sonraki 3D konumu kestirir."""
        pred_x = np.zeros(3, dtype=np.float64)
        for j, model in enumerate(self.models):
            F_h = model.get_transition_matrix(horizon_s)
            future_state = F_h @ model.x
            pred_x += self.mu[j] * future_state[0:3]
        return (float(pred_x[0]), float(pred_x[1]), float(pred_x[2]))
