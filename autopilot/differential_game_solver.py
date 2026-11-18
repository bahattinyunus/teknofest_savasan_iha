import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
import numpy as np


class PursuerAction(Enum):
    """Mavi İHA (Avcı) diferansiyel oyun taktik aksiyon kümesi."""
    LEAD_INTERCEPT = "LEAD_INTERCEPT"         # Hedefin gelecekteki konumuna önleme dönüşü
    PURE_PURSUIT_WEZ = "PURE_PURSUIT_WEZ"     # WEZ içinde kamera nişangah merkezleme
    HIGH_YOYO_ENERGY = "HIGH_YOYO_ENERGY"     # Overshoot önleyici dikey enerji takası
    LOW_YOYO_DASH = "LOW_YOYO_DASH"           # Menzil kapatıcı dalışlı hızlanma
    CUTOFF_INSIDE_TURN = "CUTOFF_INSIDE_TURN" # Rakibin dönüş çemberinin içinden kestirme


class EvaderAction(Enum):
    """Kırmızı İHA (Hedef/Kaçan) en kötü durum (Worst-Case) kaçış kümesi."""
    BREAK_TURN_LEFT = "BREAK_TURN_LEFT"
    BREAK_TURN_RIGHT = "BREAK_TURN_RIGHT"
    SCISSORS_REVERSAL = "SCISSORS_REVERSAL"
    MAX_THRUST_EXTEND = "MAX_THRUST_EXTEND"
    DIVING_SPIRAL = "DIVING_SPIRAL"


@dataclass
class IsaacsSaddlePointSolution:
    """Rufus Isaacs Homicidal Chauffeur / Hava Muharebesi Eyer Noktası Çözümü."""
    optimal_pursuer_action: PursuerAction
    expected_evader_response: EvaderAction
    saddle_point_value: float
    capture_barrier_margin_m: float
    is_inside_capture_zone: bool
    time_to_capture_s: float
    commanded_roll_deg: float
    commanded_pitch_deg: float
    commanded_speed_mps: float
    payoff_matrix: Dict[str, Dict[str, float]] = field(default_factory=dict)


class DifferentialGameSolver:
    """Rufus Isaacs Diferansiyel Oyun Teorisi (Homicidal Chauffeur & 2-Oyuncili Sıfır Toplamlı)
    Minimax Eyer Noktası (Saddle-Point) Hava Muharebesi Çözücüsü.

    Hava muharebesini Avcı (Pursuer - Mavi İHA) ve Kaçan (Evader - Kırmızı İHA) arasında
    iki oyunculu sıfır toplamlı bir diferansiyel oyun olarak modeller:
      J* = max_{u in U_pursuer} min_{v in V_evader} Payoff(x_blue, x_red, u, v)
    Avcı, rakibin en iyi kaçış manevrasına (worst-case break turn) karşı dahi 4.0 saniyelik
    WEZ yakalama bölgesini (Capture Zone) garanti eden Minimax optimal komutu seçer.
    """

    def __init__(
        self,
        pursuer_min_turn_radius_m: float = 24.0,
        evader_min_turn_radius_m: float = 22.0,
        wez_optimal_range_m: float = 36.0,
        wez_max_range_m: float = 95.0,
        horizon_s: float = 1.6
    ):
        self.r_min_p = float(pursuer_min_turn_radius_m)
        self.r_min_e = float(evader_min_turn_radius_m)
        self.wez_optimal_range_m = float(wez_optimal_range_m)
        self.wez_max_range_m = float(wez_max_range_m)
        self.horizon_s = float(horizon_s)

    def compute_isaacs_barrier(
        self,
        own_pos_ned: Tuple[float, float, float],
        own_vel_ned: Tuple[float, float, float],
        target_pos_ned: Tuple[float, float, float],
        target_vel_ned: Tuple[float, float, float]
    ) -> Tuple[bool, float, float]:
        """Homicidal Chauffeur yakalama bariyerini (Capture Barrier) analitik olarak değerlendirir.

        Döndürülen değerler:
          (is_inside_capture_zone, capture_barrier_margin_m, time_to_capture_s)
        """
        p_b = np.array(own_pos_ned, dtype=np.float64)
        v_b = np.array(own_vel_ned, dtype=np.float64)
        p_r = np.array(target_pos_ned, dtype=np.float64)
        v_r = np.array(target_vel_ned, dtype=np.float64)

        rel_p = p_r - p_b
        dist = float(np.linalg.norm(rel_p)) + 1e-6
        spd_b = max(12.0, float(np.linalg.norm(v_b)))
        spd_r = max(10.0, float(np.linalg.norm(v_r)))

        # Hız oranı gamma = V_evader / V_pursuer
        gamma = spd_r / spd_b
        los_unit = rel_p / dist
        closing_vel = float(np.dot(v_b - v_r, los_unit))

        # Isaacs kritik yakalama yarıçapı: R_crit = R_min_p * (1 - gamma^2 + 0.35)
        critical_capture_radius = max(18.0, self.wez_max_range_m * max(0.45, 1.15 - 0.35 * gamma))
        barrier_margin_m = critical_capture_radius - dist
        is_capturable = (dist <= critical_capture_radius) and (dist >= 12.0)

        if closing_vel > 0.5:
            ttc = max(0.0, (dist - self.wez_optimal_range_m) / closing_vel)
        else:
            ttc = dist / max(2.0, spd_b * 0.25)

        return (bool(is_capturable), round(float(barrier_margin_m), 2), round(float(max(0.0, ttc)), 2))

    @staticmethod
    def _propagate_kinematics(
        pos_ned: np.ndarray,
        vel_ned: np.ndarray,
        roll_deg: float,
        pitch_deg: float,
        speed_cmd: float,
        dt: float
    ) -> Tuple[np.ndarray, np.ndarray]:
        g = 9.80665
        spd0 = max(12.0, float(np.linalg.norm(vel_ned)))
        spd = spd0 + 0.5 * (speed_cmd - spd0)
        psi0 = math.atan2(float(vel_ned[1]), float(vel_ned[0]))
        omega = (g * math.tan(math.radians(roll_deg))) / max(12.0, spd)
        psi1 = psi0 + omega * dt
        pitch_rad = math.radians(pitch_deg)

        v1 = np.array([
            spd * math.cos(pitch_rad) * math.cos(psi1),
            spd * math.cos(pitch_rad) * math.sin(psi1),
            -spd * math.sin(pitch_rad)
        ], dtype=np.float64)
        p1 = pos_ned + 0.5 * (vel_ned + v1) * dt
        return p1, v1

    def solve_saddle_point(
        self,
        own_pos_ned: Tuple[float, float, float],
        own_vel_ned: Tuple[float, float, float],
        target_pos_ned: Tuple[float, float, float],
        target_vel_ned: Tuple[float, float, float]
    ) -> IsaacsSaddlePointSolution:
        """5x5 Avcı-Kaçan sıfır toplamlı ödül matrisini kurar ve Minimax eyer noktasını çözer."""
        p_b0 = np.array(own_pos_ned, dtype=np.float64)
        v_b0 = np.array(own_vel_ned, dtype=np.float64)
        p_r0 = np.array(target_pos_ned, dtype=np.float64)
        v_r0 = np.array(target_vel_ned, dtype=np.float64)

        spd_b0 = max(15.0, float(np.linalg.norm(v_b0)))
        spd_r0 = max(14.0, float(np.linalg.norm(v_r0)))

        # Hedefe olan yatay ve dikey açı hatasını hesapla
        rel0 = p_r0 - p_b0
        dist0 = float(np.linalg.norm(rel0)) + 1e-6
        psi_b0 = math.atan2(float(v_b0[1]), float(v_b0[0]))
        los_yaw = math.atan2(float(rel0[1]), float(rel0[0]))
        yaw_err_deg = math.degrees((los_yaw - psi_b0 + math.pi) % (2.0 * math.pi) - math.pi)
        alt_diff_m = float(-p_r0[2] - (-p_b0[2]))
        base_pitch = max(-20.0, min(20.0, math.degrees(math.atan2(alt_diff_m, max(10.0, dist0)))))

        # Avcı aday manevra kontrolleri (roll_deg, pitch_deg, speed_mps)
        lead_roll = max(-55.0, min(55.0, yaw_err_deg * 1.45))
        pure_roll = max(-45.0, min(45.0, yaw_err_deg * 1.05))
        inside_roll = max(-58.0, min(58.0, yaw_err_deg * 1.75 + (15.0 if yaw_err_deg >= 0 else -15.0)))

        pursuer_controls: Dict[PursuerAction, Tuple[float, float, float]] = {
            PursuerAction.LEAD_INTERCEPT: (lead_roll, base_pitch, min(30.0, spd_b0 + 2.0)),
            PursuerAction.PURE_PURSUIT_WEZ: (pure_roll, base_pitch, spd_r0 + 0.5),
            PursuerAction.HIGH_YOYO_ENERGY: (pure_roll * 0.7, min(25.0, base_pitch + 14.0), max(16.0, spd_b0 - 3.5)),
            PursuerAction.LOW_YOYO_DASH: (lead_roll, max(-22.0, base_pitch - 10.0), min(32.0, spd_b0 + 4.5)),
            PursuerAction.CUTOFF_INSIDE_TURN: (inside_roll, base_pitch, spd_b0),
        }

        evader_controls: Dict[EvaderAction, Tuple[float, float, float]] = {
            EvaderAction.BREAK_TURN_LEFT: (-55.0, 4.0, spd_r0),
            EvaderAction.BREAK_TURN_RIGHT: (55.0, 4.0, spd_r0),
            EvaderAction.SCISSORS_REVERSAL: (-45.0 if yaw_err_deg > 0 else 45.0, 6.0, max(15.0, spd_r0 - 2.0)),
            EvaderAction.MAX_THRUST_EXTEND: (0.0, 0.0, min(30.0, spd_r0 + 4.0)),
            EvaderAction.DIVING_SPIRAL: (48.0, -14.0, min(31.0, spd_r0 + 3.0)),
        }

        payoff_table: Dict[str, Dict[str, float]] = {}
        worst_case_scores: Dict[PursuerAction, Tuple[float, EvaderAction]] = {}

        for p_act, p_ctrl in pursuer_controls.items():
            payoff_table[p_act.value] = {}
            p_b1, v_b1 = self._propagate_kinematics(p_b0, v_b0, p_ctrl[0], p_ctrl[1], p_ctrl[2], self.horizon_s)

            min_score = 1e9
            worst_evader = EvaderAction.MAX_THRUST_EXTEND

            for e_act, e_ctrl in evader_controls.items():
                p_r1, v_r1 = self._propagate_kinematics(p_r0, v_r0, e_ctrl[0], e_ctrl[1], e_ctrl[2], self.horizon_s)

                los1 = p_r1 - p_b1
                d1 = float(np.linalg.norm(los1)) + 1e-6
                vb1_norm = float(np.linalg.norm(v_b1)) + 1e-6
                vr1_norm = float(np.linalg.norm(v_r1)) + 1e-6

                cos_ata = float(np.clip(np.dot(v_b1, los1) / (vb1_norm * d1), -1.0, 1.0))
                ata_deg = math.degrees(math.acos(cos_ata))

                cos_aa = float(np.clip(np.dot(v_r1, los1) / (vr1_norm * d1), -1.0, 1.0))
                tail_align_deg = math.degrees(math.acos(cos_aa))

                # Sıfır toplamlı oyun ödülü: Yüksek = Mavi (Avcı) lehine, Düşük = Kırmızı (Kaçan) lehine
                angle_payoff = 60.0 * (1.0 - ata_deg / 90.0)
                range_payoff = 40.0 * math.exp(-((d1 - self.wez_optimal_range_m) / 28.0) ** 2)
                tail_payoff = 20.0 * (1.0 - tail_align_deg / 180.0)
                overshoot_penalty = -45.0 if d1 < 13.0 else 0.0

                score = round(float(angle_payoff + range_payoff + tail_payoff + overshoot_penalty), 2)
                payoff_table[p_act.value][e_act.value] = score

                if score < min_score:
                    min_score = score
                    worst_evader = e_act

            worst_case_scores[p_act] = (min_score, worst_evader)

        # Maximin (Avcı en kötü durumu maksimize eder)
        best_p_act = max(worst_case_scores.keys(), key=lambda k: worst_case_scores[k][0])
        saddle_val, best_e_resp = worst_case_scores[best_p_act]
        opt_ctrl = pursuer_controls[best_p_act]

        is_cap, margin_m, ttc_s = self.compute_isaacs_barrier(
            own_pos_ned=own_pos_ned,
            own_vel_ned=own_vel_ned,
            target_pos_ned=target_pos_ned,
            target_vel_ned=target_vel_ned
        )

        return IsaacsSaddlePointSolution(
            optimal_pursuer_action=best_p_act,
            expected_evader_response=best_e_resp,
            saddle_point_value=round(float(saddle_val), 2),
            capture_barrier_margin_m=margin_m,
            is_inside_capture_zone=is_cap,
            time_to_capture_s=ttc_s,
            commanded_roll_deg=round(float(opt_ctrl[0]), 2),
            commanded_pitch_deg=round(float(opt_ctrl[1]), 2),
            commanded_speed_mps=round(float(opt_ctrl[2]), 2),
            payoff_matrix=payoff_table
        )
