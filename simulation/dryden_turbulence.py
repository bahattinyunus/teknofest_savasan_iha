import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
import numpy as np


class TurbulenceSeverity(Enum):
    """MIL-F-8785C / MIL-HDBK-1797 atmosferik türbülans şiddeti sınıfları."""
    NONE = "NONE"
    LIGHT = "LIGHT"         # sigma_w ~ 0.8 m/s
    MODERATE = "MODERATE"   # sigma_w ~ 2.2 m/s
    SEVERE = "SEVERE"       # sigma_w ~ 4.5 m/s


@dataclass
class GustDisturbanceSample:
    """Belirli bir irtifa ve konumda hesaplanan 3D rüzgar, Dryden türbülans ve wake vortex örneği."""
    steady_wind_ned_mps: Tuple[float, float, float]
    dryden_turbulence_uvw_mps: Tuple[float, float, float]
    dryden_angular_rates_pqr_rad_s: Tuple[float, float, float]
    wake_vortex_induced_vel_ned_mps: Tuple[float, float, float]
    wake_induced_roll_rate_deg_s: float
    total_wind_ned_mps: Tuple[float, float, float]
    is_in_wake_hazard: bool


class DrydenWindTurbulenceModel:
    """MIL-F-8785C / MIL-HDBK-1797 Dryden Sürekli Rüzgar Türbülansı, İrtifa Rüzgar
    Makası (Logarithmic Wind Shear) ve Burnham-Hallock Kuyruk Türbülansı (Wake Vortex) Motoru.

    Özellikler:
      1. Alçak İrtifa (< 300m) MIL-F-8785C ölçek uzunlukları (L_u, L_v, L_w) ve
         türbülans yoğunlukları (sigma_u, sigma_v, sigma_w),
      2. Birinci derece şekillendirme filtreleriyle (Shaping Filters) zaman korelasyonlu
         doğrusal (u_g, v_g, w_g) ve açısal (p_g, q_g, r_g) türbülans bileşenleri,
      3. Öndeki rakip İHA'nın kanat uçlarından yayılan çift girdaplı Burnham-Hallock
         (Wake Vortex) teğetsel hız alanı ve yakın kuyruk takibinde (WEZ < 25m)
         oluşan indüklenmiş yatış momenti (induced roll hazard) hesabı.
    """

    def __init__(
        self,
        severity: TurbulenceSeverity = TurbulenceSeverity.LIGHT,
        wind_speed_20ft_mps: float = 4.5,
        wind_direction_deg: float = 45.0,
        wingspan_b_m: float = 1.6,
        seed: int = 42
    ):
        self.severity = severity
        self.w20 = float(wind_speed_20ft_mps)
        self.wind_dir_rad = math.radians(float(wind_direction_deg))
        self.b = float(wingspan_b_m)
        self.rng = np.random.default_rng(seed)

        # Filtre durum değişkenleri
        self._ug = 0.0
        self._vg = 0.0
        self._wg = 0.0
        self._pg = 0.0
        self._qg = 0.0
        self._rg = 0.0

    def reset(self) -> None:
        self._ug = self._vg = self._wg = 0.0
        self._pg = self._qg = self._rg = 0.0

    def compute_steady_wind_shear_ned(self, altitude_m: float) -> Tuple[float, float, float]:
        """MIL-F-8785C logaritmik sınır tabakası rüzgar makası:
        V_w(h) = W_20 * ln(h / z_0) / ln(6.096 / z_0), z_0 = 0.045 m.
        """
        h = max(2.0, float(altitude_m))
        z0 = 0.045
        shear_ratio = math.log(h / z0) / math.log(6.096 / z0)
        mag = self.w20 * max(0.3, min(2.2, shear_ratio))
        wn = -mag * math.cos(self.wind_dir_rad)
        we = -mag * math.sin(self.wind_dir_rad)
        return (round(wn, 3), round(we, 3), 0.0)

    def compute_wake_vortex_effect(
        self,
        own_pos_ned: Tuple[float, float, float],
        leader_pos_ned: Tuple[float, float, float],
        leader_vel_ned: Tuple[float, float, float],
        leader_mass_kg: float = 3.8,
        leader_span_m: float = 1.6,
        air_density_kg_m3: float = 1.21
    ) -> Tuple[Tuple[float, float, float], float, bool]:
        """Burnham-Hallock Kuyruk Girdabı (Wake Vortex) Modeli.

        Öndeki İHA'nın oluşturduğu sirkülasyon şiddeti:
          Gamma_0 = (M * g) / (rho * V_leader * b_0),  b_0 = (pi / 4) * b_leader
        Kanat ucu girdap merkezlerinden (y = +- b_0 / 2) r uzaklıkta teğetsel hız:
          V_theta(r) = (Gamma_0 / (2 * pi)) * r / (r^2 + r_c^2)
        """
        if self.severity == TurbulenceSeverity.NONE:
            return ((0.0, 0.0, 0.0), 0.0, False)

        p_own = np.array(own_pos_ned, dtype=np.float64)
        p_ldr = np.array(leader_pos_ned, dtype=np.float64)
        v_ldr = np.array(leader_vel_ned, dtype=np.float64)

        v_mag = max(12.0, float(np.linalg.norm(v_ldr)))
        fwd_unit = v_ldr / v_mag

        rel = p_own - p_ldr
        # Öndeki İHA'nın arkasındaki iz mesafesi (trail distance > 0 ise arkadayız)
        trail_dist = -float(np.dot(rel, fwd_unit))
        if trail_dist <= 2.0 or trail_dist > 90.0:
            return ((0.0, 0.0, 0.0), 0.0, False)

        # Yatay ve dikey eksen birim vektörleri
        up_unit = np.array([0.0, 0.0, -1.0], dtype=np.float64)
        right_unit = np.cross(fwd_unit, up_unit)
        r_norm = float(np.linalg.norm(right_unit))
        if r_norm < 1e-6:
            right_unit = np.array([0.0, 1.0, 0.0], dtype=np.float64)
        else:
            right_unit /= r_norm

        y_lat = float(np.dot(rel, right_unit))
        z_vert = float(np.dot(rel, up_unit))

        b0 = (math.pi / 4.0) * leader_span_m
        gamma0 = (leader_mass_kg * 9.80665) / (air_density_kg_m3 * v_mag * b0)
        # Zamanla viskoz sönümlenme
        age_s = trail_dist / v_mag
        gamma_eff = gamma0 * math.exp(-0.25 * age_s)
        rc = 0.05 * leader_span_m  # Girdap çekirdek yarıçapı

        # Sol (-b0/2) ve Sağ (+b0/2) kanat ucu girdaplarından indüklenen dikey hız (downwash)
        dy_left = y_lat + 0.5 * b0
        dy_right = y_lat - 0.5 * b0
        r_left_sq = dy_left ** 2 + z_vert ** 2 + rc ** 2
        r_right_sq = dy_right ** 2 + z_vert ** 2 + rc ** 2

        w_left = -(gamma_eff / (2.0 * math.pi)) * (dy_left / r_left_sq)
        w_right = +(gamma_eff / (2.0 * math.pi)) * (dy_right / r_right_sq)
        w_total_up = w_left + w_right

        # Kanat açıklığı boyunca asimetrik dikey hızdan kaynaklanan yatış hızı (deg/s)
        roll_grad = (w_right - w_left) / max(0.5, self.b)
        induced_roll_deg_s = float(np.clip(math.degrees(roll_grad) * 1.8, -45.0, 45.0))

        radial_miss = math.hypot(y_lat, z_vert)
        in_hazard = (radial_miss < leader_span_m * 1.5) and (trail_dist < 45.0)

        # NED koordinatlarında indüklenmiş hız (Down = -Up)
        w_ned = (0.0, 0.0, round(float(-w_total_up), 3))
        return (w_ned, round(induced_roll_deg_s, 2), bool(in_hazard))

    def step(
        self,
        altitude_m: float,
        airspeed_mps: float,
        dt: float = 0.05,
        own_pos_ned: Tuple[float, float, float] = (0.0, 0.0, -80.0),
        leader_pos_ned: Optional[Tuple[float, float, float]] = None,
        leader_vel_ned: Optional[Tuple[float, float, float]] = None
    ) -> GustDisturbanceSample:
        """Bir zaman adımında Dryden spektral şekillendirme filtrelerini ve kuyruk türbülansını ilerletir."""
        dt = max(1e-3, float(dt))
        h = max(5.0, float(altitude_m))
        vt = max(12.0, float(airspeed_mps))

        steady_ned = self.compute_steady_wind_shear_ned(h)

        if self.severity == TurbulenceSeverity.NONE:
            return GustDisturbanceSample(
                steady_wind_ned_mps=steady_ned,
                dryden_turbulence_uvw_mps=(0.0, 0.0, 0.0),
                dryden_angular_rates_pqr_rad_s=(0.0, 0.0, 0.0),
                wake_vortex_induced_vel_ned_mps=(0.0, 0.0, 0.0),
                wake_induced_roll_rate_deg_s=0.0,
                total_wind_ned_mps=steady_ned,
                is_in_wake_hazard=False
            )

        # Şiddet çarpanı
        sev_mult = {
            TurbulenceSeverity.LIGHT: 1.0,
            TurbulenceSeverity.MODERATE: 2.2,
            TurbulenceSeverity.SEVERE: 4.0
        }.get(self.severity, 1.0)

        # MIL-F-8785C alçak irtifa ölçek uzunlukları ve sigma değerleri
        lw = h
        lu = lv = h / ((0.177 + 0.000823 * h) ** 1.2)
        sigma_w = 0.1 * self.w20 * sev_mult
        sigma_u = sigma_v = sigma_w / ((0.177 + 0.000823 * h) ** 0.4)

        # Ayrık zamanlı Markov-Dryden güncellemesi
        au = math.exp(-(vt / max(5.0, lu)) * dt)
        av = math.exp(-(vt / max(5.0, lv)) * dt)
        aw = math.exp(-(vt / max(5.0, lw)) * dt)

        nu, nv, nw = self.rng.normal(0.0, 1.0, size=3)
        ug_new = au * self._ug + sigma_u * math.sqrt(max(0.0, 1.0 - au * au)) * nu
        vg_new = av * self._vg + sigma_v * math.sqrt(max(0.0, 1.0 - av * av)) * nv
        wg_new = aw * self._wg + sigma_w * math.sqrt(max(0.0, 1.0 - aw * aw)) * nw

        # Açısal türbülans hızları (p_g, q_g, r_g)
        dwg_dt = (wg_new - self._wg) / dt
        dvg_dt = (vg_new - self._vg) / dt
        ap = math.exp(-(math.pi * vt / (4.0 * self.b)) * dt)
        self._pg = ap * self._pg + (sigma_w / max(2.0, math.sqrt(lw * self.b))) * math.sqrt(max(0.0, 1.0 - ap * ap)) * float(self.rng.normal())
        self._qg = float(np.clip(dwg_dt / vt, -0.6, 0.6))
        self._rg = float(np.clip(-dvg_dt / vt, -0.6, 0.6))

        self._ug, self._vg, self._wg = float(ug_new), float(vg_new), float(wg_new)

        wake_vel = (0.0, 0.0, 0.0)
        wake_roll = 0.0
        wake_hazard = False
        if leader_pos_ned is not None and leader_vel_ned is not None:
            wake_vel, wake_roll, wake_hazard = self.compute_wake_vortex_effect(
                own_pos_ned=own_pos_ned,
                leader_pos_ned=leader_pos_ned,
                leader_vel_ned=leader_vel_ned
            )

        tot_n = steady_ned[0] + self._ug + wake_vel[0]
        tot_e = steady_ned[1] + self._vg + wake_vel[1]
        tot_d = steady_ned[2] + self._wg + wake_vel[2]

        return GustDisturbanceSample(
            steady_wind_ned_mps=steady_ned,
            dryden_turbulence_uvw_mps=(round(self._ug, 3), round(self._vg, 3), round(self._wg, 3)),
            dryden_angular_rates_pqr_rad_s=(round(self._pg, 4), round(self._qg, 4), round(self._rg, 4)),
            wake_vortex_induced_vel_ned_mps=wake_vel,
            wake_induced_roll_rate_deg_s=wake_roll,
            total_wind_ned_mps=(round(tot_n, 3), round(tot_e, 3), round(tot_d, 3)),
            is_in_wake_hazard=wake_hazard
        )
