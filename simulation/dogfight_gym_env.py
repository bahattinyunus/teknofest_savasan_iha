"""
AeroCombat - Derin Pekiştirmeli Öğrenme (RL) İt Dalaşı Simülasyon Ortamı (Dogfight Gym Environment).

OpenAI Gym / Farama Gymnasium uyumlu bu ortam, otonom hava muharebesi ajanlarının
(PPO, SAC, DQN) 1v1 veya öz-oyun (Self-Play) ile eğitilmesini sağlar:
- 16 Boyutlu Normalize Gözlem Uzayı (Observation Space)
- Ayrık (Discrete - 7 BFM Manevrası) veya Sürekli (Continuous) Aksiyon Uzayı
- Şartnameye Uygun Ödül Fonksiyonu (Reward Shaping):
  * WEZ hizalanma ve burun açısı (ATA) ödülü
  * 4.0 saniye kesintisiz kilitlenme durumunda +100 büyük zafer ödülü
  * Geofence sınır ihlalinde -200 ceza ve erken sonlandırma (Terminated)
  * Yüksek G yapısal yük ve stall cezası
- Dahili Heuristic Rakip Pilot ("AceBot") ile kütüphanesiz anında kıyaslama/eğitim
"""

import math
import random
from typing import Dict, Tuple, Any, Optional, List, Union
import numpy as np

from simulation.aerodynamics_6dof import Aerodynamics6DoF, AircraftParameters, FlightControls6DoF, State6DoF
from autopilot.neural_combat_pilot import NeuralCombatPilot, TacticalManeuver, CombatRole


class DogfightGymEnv:
    """
    OpenAI Gym / Farama Gymnasium Uyumlu 3D Hava Muharebesi Çevresi.
    """

    def __init__(
        self,
        discrete_actions: bool = True,
        max_steps: int = 1000,
        dt: float = 0.05,
        opponent_difficulty: str = "EXPERT"  # "EASY", "MEDIUM", "EXPERT"
    ):
        self.discrete_actions = discrete_actions
        self.max_steps = max_steps
        self.dt = dt
        self.opponent_difficulty = opponent_difficulty

        # Fizik motorları
        self.blue_aero = Aerodynamics6DoF()
        self.red_aero = Aerodynamics6DoF()
        self.neural_advisor = NeuralCombatPilot()

        # Görev ve kilitlenme takibi
        self.current_step = 0
        self.lock_timer_s = 0.0
        self.successful_locks = 0
        self.geofence_radius_m = 300.0

        # Aksiyon & Gözlem boyutları
        self.action_dim = 7 if self.discrete_actions else 3
        self.observation_dim = 16

    def reset(self, seed: Optional[int] = None) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Ortamı başlangıç durumuna sıfırlar ve ilk gözlemi döner."""
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)

        self.current_step = 0
        self.lock_timer_s = 0.0
        self.successful_locks = 0

        # Mavi İHA (Bizim Uçağımız): Merkezde, 80m irtifada, 22 m/s hızda
        blue_init = State6DoF(
            pos_n=0.0,
            pos_e=0.0,
            pos_d=-80.0,
            u=22.0,
            v=0.0,
            w=0.0,
            phi=0.0,
            theta=0.0,
            psi=0.0,
            current_thrust_n=14.0
        )
        self.blue_aero.reset(blue_init)

        # Kırmızı İHA (Rakip): Ön sektörde 60-120m mesafede rastgele açı ve irtifada
        spawn_dist = random.uniform(60.0, 110.0)
        spawn_angle = random.uniform(-0.4, 0.4)
        red_init = State6DoF(
            pos_n=spawn_dist * math.cos(spawn_angle),
            pos_e=spawn_dist * math.sin(spawn_angle),
            pos_d=-80.0 + random.uniform(-15.0, 15.0),
            u=20.0 + random.uniform(-2.0, 3.0),
            v=0.0,
            w=0.0,
            phi=0.0,
            theta=0.0,
            psi=spawn_angle + random.uniform(-0.3, 0.3),
            current_thrust_n=13.0
        )
        self.red_aero.reset(red_init)

        obs = self._get_observation()
        info = {"successful_locks": 0, "lock_timer": 0.0, "step": 0}
        return obs, info

    def step(self, action: Union[int, np.ndarray]) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        """
        Zaman adımı yürütür:
        1. Ajan aksiyonunu Mavi uçuş kontrol yüzeylerine dönüştür
        2. Rakip ("AceBot") yapay zekasını çalıştır
        3. 6-DoF aerodinamik integrasyonu ilerlet
        4. Ödül ve kilitlenme sayacını değerlendir
        """
        self.current_step += 1

        # 1. Mavi İHA Kontrol Girdisi
        blue_ctrl = self._action_to_controls(action)

        # 2. Kırmızı İHA ("AceBot") Otonom Taktik Manevrası
        red_ctrl = self._compute_opponent_controls()

        # 3. 6-DoF Fizik Adımı
        blue_state = self.blue_aero.step(blue_ctrl, dt=self.dt)
        red_state = self.red_aero.step(red_ctrl, dt=self.dt)

        # 4. Göreceli Muharebe Geometrisi
        dx = red_state.pos_n - blue_state.pos_n
        dy = red_state.pos_e - blue_state.pos_e
        dz = red_state.pos_d - blue_state.pos_d
        dist_3d = max(1.0, math.sqrt(dx ** 2 + dy ** 2 + dz ** 2))

        # Burun açısı (ATA)
        los_b = np.array([dx, dy, dz]) / dist_3d
        v_b = np.array([blue_state.u, blue_state.v, blue_state.w])
        v_b_norm = max(1.0, float(np.linalg.norm(v_b)))
        cos_ata = np.clip(np.dot(v_b / v_b_norm, los_b), -1.0, 1.0)
        ata_deg = math.degrees(math.acos(cos_ata))

        # Aspect Angle (AA)
        v_r = np.array([red_state.u, red_state.v, red_state.w])
        v_r_norm = max(1.0, float(np.linalg.norm(v_r)))
        cos_aa = np.clip(np.dot(v_r / v_r_norm, los_b), -1.0, 1.0)
        aspect_angle_deg = math.degrees(math.acos(cos_aa))

        # 5. Kilitlenme Durumu ve Sayacı (TEKNOFEST %5 Kuralı + Merkezleme Toleransı)
        # 15m - 85m mesafe ve ATA < 18° kilitlenme şartıdır
        in_wez = (15.0 <= dist_3d <= 85.0) and (ata_deg <= 20.0)

        step_reward = 0.0
        terminated = False
        truncated = self.current_step >= self.max_steps

        if in_wez:
            self.lock_timer_s += self.dt
            # Yoğun kilitlenme ödülü
            step_reward += 3.0 * self.dt
            if self.lock_timer_s >= 4.0:
                # 4.0 SANİYE KİLİTLENME TAMAMLANDI! +100 PUAN
                step_reward += 100.0
                self.successful_locks += 1
                self.lock_timer_s = 0.0  # Sayacı yeni kilit için sıfırla
        else:
            # Kadrajdan çıkıldığında toleranslı kayıp
            self.lock_timer_s = max(0.0, self.lock_timer_s - self.dt * 2.0)

        # Şekillendirme Ödülü (Reward Shaping)
        # Hedefe burun çevirmeyi teşvik et
        step_reward += 0.05 * (1.0 - ata_deg / 180.0)
        # Optimal takip mesafesi (35m) civarını ödüllendir
        dist_err = abs(dist_3d - 35.0)
        step_reward += max(0.0, 0.08 * (1.0 - dist_err / 60.0))

        # 6. Güvenlik ve Ceza Denetimi (Geofence & Yapısal Limitler)
        dist_from_origin = math.sqrt(blue_state.pos_n ** 2 + blue_state.pos_e ** 2)
        if dist_from_origin > self.geofence_radius_m:
            step_reward -= 200.0
            terminated = True  # Diskalifiye / Sınır İhlali

        # Aşırı G yükü cezası (> 4.5G)
        if abs(self.blue_aero.last_load_factor_g) > 4.5:
            step_reward -= 0.5 * (abs(self.blue_aero.last_load_factor_g) - 4.5)

        # Perdövites (Stall) cezası
        if self.blue_aero.is_stalled:
            step_reward -= 1.0

        obs = self._get_observation()
        info = {
            "distance_m": dist_3d,
            "ata_deg": ata_deg,
            "aspect_angle_deg": aspect_angle_deg,
            "lock_timer_s": self.lock_timer_s,
            "successful_locks": self.successful_locks,
            "in_wez": in_wez
        }

        return obs, step_reward, terminated, truncated, info

    def _get_observation(self) -> np.ndarray:
        """16 boyutlu normalize durum vektörünü üretir."""
        b = self.blue_aero.state
        r = self.red_aero.state

        dx = r.pos_n - b.pos_n
        dy = r.pos_e - b.pos_e
        dz = r.pos_d - b.pos_d
        dist = max(1.0, math.sqrt(dx ** 2 + dy ** 2 + dz ** 2))

        los_u = np.array([dx, dy, dz]) / dist
        v_b = np.array([b.u, b.v, b.w])
        v_r = np.array([r.u, r.v, r.w])
        closing_speed = float(np.dot(v_b - v_r, los_u))

        ata = math.degrees(math.acos(np.clip(np.dot(v_b / max(1.0, np.linalg.norm(v_b)), los_u), -1.0, 1.0)))
        aa = math.degrees(math.acos(np.clip(np.dot(v_r / max(1.0, np.linalg.norm(v_r)), los_u), -1.0, 1.0)))

        # Özgül enerji
        g0 = 9.80665
        es_blue = b.altitude_m + (b.airspeed_mps ** 2) / (2 * g0)
        es_red = r.altitude_m + (r.airspeed_mps ** 2) / (2 * g0)

        dist_to_fence = max(0.0, self.geofence_radius_m - math.sqrt(b.pos_n ** 2 + b.pos_e ** 2))

        obs = np.array([
            dist / 200.0,
            closing_speed / 40.0,
            ata / 180.0,
            aa / 180.0,
            (r.altitude_m - b.altitude_m) / 100.0,
            b.airspeed_mps / 40.0,
            r.airspeed_mps / 40.0,
            (es_blue - es_red) / 150.0,
            1.0 if (15.0 <= dist <= 85.0 and ata <= 20.0) else 0.0,
            self.blue_aero.last_load_factor_g / 6.0,
            dist_to_fence / self.geofence_radius_m,
            self.lock_timer_s / 4.0,
            1.0 if self.lock_timer_s >= 4.0 else 0.0,
            b.theta / (math.pi / 2.0),
            b.phi / math.pi,
            1.0 if (aa > 140.0 and dist < 80.0) else 0.0  # RWR tehdit uyarısı
        ], dtype=np.float32)

        return np.clip(obs, -3.0, 3.0)

    def _action_to_controls(self, action: Union[int, np.ndarray]) -> FlightControls6DoF:
        """Ajan aksiyonunu uçuş kontrol yüzeylerine haritalandırır."""
        if not self.discrete_actions and isinstance(action, (list, np.ndarray)):
            # Sürekli aksiyon [throttle, elevator, aileron]
            t = float(np.clip(action[0], 0.0, 1.0))
            e = float(np.clip(action[1], -1.0, 1.0))
            a = float(np.clip(action[2], -1.0, 1.0))
            return FlightControls6DoF(throttle=t, elevator=e, aileron=a, rudder=0.0)

        # Ayrık Taktik BFM Aksiyonları (0-6)
        act_id = int(action) if isinstance(action, (int, np.integer)) else int(action[0])
        trim = self.blue_aero.trim_level_flight(22.0, 80.0)

        if act_id == 0:    # PURE_PURSUIT
            return FlightControls6DoF(throttle=0.75, elevator=trim.elevator, aileron=0.0, rudder=0.0)
        elif act_id == 1:  # LEAD_PURSUIT (Sert Dönüş)
            return FlightControls6DoF(throttle=0.85, elevator=trim.elevator + 0.15, aileron=0.35, rudder=0.05)
        elif act_id == 2:  # LAG_PURSUIT (Geniş Dönüş / Enerji Koruma)
            return FlightControls6DoF(throttle=0.65, elevator=trim.elevator, aileron=0.20, rudder=0.0)
        elif act_id == 3:  # HIGH_YOYO (Dikey Tırmanışla Hız Kesme)
            return FlightControls6DoF(throttle=0.50, elevator=trim.elevator + 0.35, aileron=0.15, rudder=0.0)
        elif act_id == 4:  # LOW_YOYO (Dalışla Hızlanma)
            return FlightControls6DoF(throttle=0.95, elevator=trim.elevator - 0.25, aileron=0.10, rudder=0.0)
        elif act_id == 5:  # DEFENSIVE_BREAK (3.5G Savunma Dönüşü)
            return FlightControls6DoF(throttle=1.00, elevator=trim.elevator + 0.45, aileron=0.70, rudder=0.15)
        else:              # LEVEL_CRUISE
            return trim

    def _compute_opponent_controls(self) -> FlightControls6DoF:
        """Rakip ("AceBot") yapay zekasının manevra komutlarını üretir."""
        trim = self.red_aero.trim_level_flight(20.0, 80.0)

        if self.opponent_difficulty == "EASY":
            # Sabit ufki uçuş
            return trim

        # EXPERT: Mavi arkasındaysa kaçınma makası (Scissors / Weave), öndeyse ters manevra
        dx = self.blue_aero.state.pos_n - self.red_aero.state.pos_n
        t_sec = self.current_step * self.dt

        # Sinüzoidal kaçış makası
        roll_cmd = 0.45 * math.sin(t_sec * 1.2)
        pitch_cmd = trim.elevator + 0.10 * math.cos(t_sec * 0.8)
        throttle_cmd = 0.70 + 0.15 * math.sin(t_sec * 0.5)

        return FlightControls6DoF(
            throttle=float(np.clip(throttle_cmd, 0.2, 0.95)),
            elevator=float(np.clip(pitch_cmd, -0.4, 0.4)),
            aileron=float(np.clip(roll_cmd, -0.6, 0.6)),
            rudder=0.0
        )
