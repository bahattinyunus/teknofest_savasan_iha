import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import numpy as np


@dataclass
class MPPIControlCommand:
    """MPPI stokastik optimal kontrolcüsünün ürettiği 4-Saniye Kilit Odaklı uçuş komutu."""
    roll_cmd_deg: float
    pitch_cmd_deg: float
    airspeed_cmd_mps: float
    predicted_lock_probability: float
    expected_boresight_error_deg: float
    expected_range_m: float
    optimal_cost: float
    planned_trajectory_ned: List[Tuple[float, float, float]] = field(default_factory=list)


class MPPILockGuidanceController:
    """4.0 Saniye Kesintisiz Kilitlenme İçin Model Predictive Path Integral (MPPI) Güdümcüsü.

    N adet (varsayılan 48) stokastik kontrol yörüngesini H adım (3.0 saniye) ileriye
    simüle eder. Her yörüngeyi:
      1. Kamera Boresight (Nişangah) merkezleme hatası,
      2. %5 Ekran Alanı şartına karşılık gelen optimal WEZ menzili (28m - 55m),
      3. Hedef kuyruk konisi (Tail Aspect) hizalanması,
      4. İrtifa tabanı (Hard Deck) ve kontrol eforu
    kriterlerine göre puanlar ve Boltzmann ağırlıklı optimal komutu hesaplar.
    """

    def __init__(
        self,
        num_rollouts: int = 48,
        horizon_steps: int = 15,
        dt: float = 0.2,
        temperature_lambda: float = 12.0,
        optimal_range_m: float = 36.0,
        min_safe_alt_m: float = 32.0,
        max_roll_deg: float = 55.0,
        max_pitch_deg: float = 25.0,
        min_speed_mps: float = 15.0,
        max_speed_mps: float = 32.0,
        seed: int = 42
    ):
        self.num_rollouts = max(8, int(num_rollouts))
        self.horizon_steps = max(4, int(horizon_steps))
        self.dt = float(dt)
        self.temperature_lambda = max(0.5, float(temperature_lambda))
        self.optimal_range_m = float(optimal_range_m)
        self.min_safe_alt_m = float(min_safe_alt_m)
        self.max_roll_deg = float(max_roll_deg)
        self.max_pitch_deg = float(max_pitch_deg)
        self.min_speed_mps = float(min_speed_mps)
        self.max_speed_mps = float(max_speed_mps)
        self.rng = np.random.default_rng(seed)

        # Warm-start nominal kontrol dizisi: [H, 3] -> (roll_deg, pitch_deg, speed_mps)
        self.u_nominal = np.zeros((self.horizon_steps, 3), dtype=np.float64)
        self.u_nominal[:, 2] = 22.0

    def reset(self) -> None:
        self.u_nominal[:, 0] = 0.0
        self.u_nominal[:, 1] = 0.0
        self.u_nominal[:, 2] = 22.0

    def compute_optimal_command(
        self,
        own_pos_ned: Tuple[float, float, float],
        own_vel_ned: Tuple[float, float, float],
        target_pos_ned: Tuple[float, float, float],
        target_vel_ned: Tuple[float, float, float],
        target_acc_ned: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    ) -> MPPIControlCommand:
        """MPPI örnekleme ve ağırlıklı yörünge integrali ile optimal uçuş komutunu üretir."""
        own_p = np.array(own_pos_ned, dtype=np.float64)
        own_v = np.array(own_vel_ned, dtype=np.float64)
        tgt_p = np.array(target_pos_ned, dtype=np.float64)
        tgt_v = np.array(target_vel_ned, dtype=np.float64)
        tgt_a = np.array(target_acc_ned, dtype=np.float64)

        own_speed0 = max(12.0, float(np.linalg.norm(own_v)))
        own_heading0 = math.atan2(float(own_v[1]), float(own_v[0]))

        # 1. Hedefin H adım boyunca öngörülen 3D yörüngesini çıkar
        tgt_traj_p = np.zeros((self.horizon_steps, 3), dtype=np.float64)
        tgt_traj_v = np.zeros((self.horizon_steps, 3), dtype=np.float64)
        cur_tp = tgt_p.copy()
        cur_tv = tgt_v.copy()
        for k in range(self.horizon_steps):
            cur_tv = cur_tv + tgt_a * self.dt
            cur_tp = cur_tp + cur_tv * self.dt
            tgt_traj_p[k] = cur_tp
            tgt_traj_v[k] = cur_tv

        # 2. Stokastik Pertürbasyon Üretimi [N, H, 3]
        noise_std = np.array([14.0, 6.0, 2.5], dtype=np.float64)
        eps = self.rng.normal(0.0, 1.0, size=(self.num_rollouts, self.horizon_steps, 3)) * noise_std
        # İlk rollout her zaman gürültüsüz nominal yörünge olsun
        eps[0] = 0.0

        u_samples = self.u_nominal[None, :, :] + eps
        u_samples[:, :, 0] = np.clip(u_samples[:, :, 0], -self.max_roll_deg, self.max_roll_deg)
        u_samples[:, :, 1] = np.clip(u_samples[:, :, 1], -self.max_pitch_deg, self.max_pitch_deg)
        u_samples[:, :, 2] = np.clip(u_samples[:, :, 2], self.min_speed_mps, self.max_speed_mps)

        # 3. Vektörize İleri Kinematik Rollout Simülasyonu [N paralel yörünge]
        p_n = np.full(self.num_rollouts, own_p[0], dtype=np.float64)
        p_e = np.full(self.num_rollouts, own_p[1], dtype=np.float64)
        p_d = np.full(self.num_rollouts, own_p[2], dtype=np.float64)
        psi = np.full(self.num_rollouts, own_heading0, dtype=np.float64)
        spd = np.full(self.num_rollouts, own_speed0, dtype=np.float64)

        total_costs = np.zeros(self.num_rollouts, dtype=np.float64)
        g = 9.80665

        for k in range(self.horizon_steps):
            roll_rad = np.radians(u_samples[:, k, 0])
            pitch_rad = np.radians(u_samples[:, k, 1])
            cmd_spd = u_samples[:, k, 2]

            # Hız birinci derece gecikme ve koordineli dönüş dinamiği
            spd = spd + 0.45 * (cmd_spd - spd)
            omega = (g * np.tan(roll_rad)) / np.maximum(12.0, spd)
            psi = psi + omega * self.dt

            vn = spd * np.cos(pitch_rad) * np.cos(psi)
            ve = spd * np.cos(pitch_rad) * np.sin(psi)
            vd = -spd * np.sin(pitch_rad)

            p_n = p_n + vn * self.dt
            p_e = p_e + ve * self.dt
            p_d = p_d + vd * self.dt

            # Hedef bağıl vektörü (LOS)
            los_n = tgt_traj_p[k, 0] - p_n
            los_e = tgt_traj_p[k, 1] - p_e
            los_d = tgt_traj_p[k, 2] - p_d
            dist = np.sqrt(los_n ** 2 + los_e ** 2 + los_d ** 2) + 1e-6

            # Boresight (ATA) açısı: cos(ATA) = (V_own . LOS) / (|V_own| |LOS|)
            v_mag = np.sqrt(vn ** 2 + ve ** 2 + vd ** 2) + 1e-6
            dot_v_los = (vn * los_n + ve * los_e + vd * los_d) / (v_mag * dist)
            dot_v_los = np.clip(dot_v_los, -1.0, 1.0)
            ata_rad = np.arccos(dot_v_los)

            # Menzil maliyeti (%5 alan kuralı için ~36m tatlı nokta, 15m altı çarpışma cezası)
            range_err = (dist - self.optimal_range_m) / 20.0
            collision_penalty = np.where(dist < 14.0, 150.0 * ((14.0 - dist) / 14.0) ** 2, 0.0)

            # İrtifa güvenlik tabanı (Hard-deck penalty: -p_d < min_safe_alt_m)
            alt_m = -p_d
            floor_penalty = np.where(alt_m < self.min_safe_alt_m, 120.0 * (self.min_safe_alt_m - alt_m), 0.0)

            # Kontrol yumuşaklığı maliyeti
            effort_cost = 0.05 * ((u_samples[:, k, 0] / self.max_roll_deg) ** 2 + (u_samples[:, k, 1] / self.max_pitch_deg) ** 2)

            step_cost = (
                35.0 * (ata_rad ** 2)
                + 6.0 * (range_err ** 2)
                + collision_penalty
                + floor_penalty
                + effort_cost
            )
            total_costs += step_cost

        # 4. Path Integral Boltzmann Ağırlıklandırması
        min_cost = float(np.min(total_costs))
        exp_weights = np.exp(-(total_costs - min_cost) / self.temperature_lambda)
        weight_sum = float(np.sum(exp_weights)) + 1e-12
        weights = exp_weights / weight_sum

        # Optimal kontrol dizisini güncelle
        self.u_nominal = np.tensordot(weights, u_samples, axes=(0, 0))

        best_u0 = self.u_nominal[0].copy()

        # Bir sonraki çağrı için kontrol dizisini 1 adım kaydır (Warm-start shift)
        self.u_nominal[:-1] = self.u_nominal[1:]

        # Optimal yörüngenin izini ve beklenen kilit olasılığını hesapla
        planned_traj: List[Tuple[float, float, float]] = []
        sim_p = own_p.copy()
        sim_psi = own_heading0
        sim_spd = own_speed0
        ata_accum = 0.0
        dist_accum = 0.0

        for k in range(self.horizon_steps):
            r_rad = math.radians(float(self.u_nominal[k, 0]))
            p_rad = math.radians(float(self.u_nominal[k, 1]))
            c_spd = float(self.u_nominal[k, 2])
            sim_spd = sim_spd + 0.45 * (c_spd - sim_spd)
            sim_psi += (g * math.tan(r_rad) / max(12.0, sim_spd)) * self.dt
            v_step = np.array([
                sim_spd * math.cos(p_rad) * math.cos(sim_psi),
                sim_spd * math.cos(p_rad) * math.sin(sim_psi),
                -sim_spd * math.sin(p_rad)
            ])
            sim_p = sim_p + v_step * self.dt
            planned_traj.append((round(float(sim_p[0]), 2), round(float(sim_p[1]), 2), round(float(sim_p[2]), 2)))

            los_vec = tgt_traj_p[k] - sim_p
            d_k = float(np.linalg.norm(los_vec)) + 1e-6
            cos_ata = float(np.dot(v_step, los_vec) / (np.linalg.norm(v_step) * d_k + 1e-6))
            ata_deg_k = math.degrees(math.acos(max(-1.0, min(1.0, cos_ata))))
            ata_accum += ata_deg_k
            dist_accum += d_k

        mean_ata_deg = ata_accum / self.horizon_steps
        mean_range_m = dist_accum / self.horizon_steps

        # Kilitlenme başarı olasılığı skoru (0.0 - 1.0)
        angle_factor = math.exp(-((mean_ata_deg / 18.0) ** 2))
        range_factor = math.exp(-(((mean_range_m - self.optimal_range_m) / 30.0) ** 2))
        lock_prob = float(max(0.01, min(0.99, angle_factor * range_factor)))

        return MPPIControlCommand(
            roll_cmd_deg=round(float(best_u0[0]), 2),
            pitch_cmd_deg=round(float(best_u0[1]), 2),
            airspeed_cmd_mps=round(float(best_u0[2]), 2),
            predicted_lock_probability=round(lock_prob, 4),
            expected_boresight_error_deg=round(mean_ata_deg, 2),
            expected_range_m=round(mean_range_m, 2),
            optimal_cost=round(min_cost, 2),
            planned_trajectory_ned=planned_traj
        )
