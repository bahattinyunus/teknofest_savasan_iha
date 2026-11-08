"""
AeroCombat - 6-DoF (Six Degrees of Freedom) Havacılık Uçuş Dinamiği ve Aerodinamik Simülatörü.

Bu modül, TEKNOFEST Savaşan İHA ve askeri hava muharebesi testleri için
doğrusal olmayan (non-linear) 6 serbestlik dereceli uçuş mekaniğini modeller:
- Uluslararası Standart Atmosfer (ISA - International Standard Atmosphere)
- Gövde ekseni (Body-frame) kuvvet ve moment denklemleri (Navier-Stokes türevi katsayılar)
- Yüksek hücum açısı (AoA / alpha) ve kayma açısı (beta) aerodinamik kutupları (Stall/Perdövites)
- Elektrikli itki ve pervane tork/akım modeli
- Euler açıları (Roll, Pitch, Yaw) ve NED (North-East-Down) seyrüsefer kinematikleri
- G-kuvveti (Load factor $n_z$) ve yapısal sınır izleme
"""

import math
from dataclasses import dataclass, field
from typing import Dict, Any, Tuple, Optional
import numpy as np


@dataclass
class AircraftParameters:
    """Hava aracı fiziksel, kütlesel ve aerodinamik tasarım katsayıları."""
    # Kütle ve Eylemsizlik
    mass_kg: float = 3.5                   # İHA toplam kalkış ağırlığı (kg)
    ixx: float = 0.18                      # X ekseni eylemsizlik momenti (kg*m^2)
    iyy: float = 0.22                      # Y ekseni eylemsizlik momenti (kg*m^2)
    izz: float = 0.35                      # Z ekseni eylemsizlik momenti (kg*m^2)
    ixz: float = 0.012                     # XZ çapraz eylemsizlik momenti (kg*m^2)

    # Geometri
    wing_area_s: float = 0.55              # Kanat referans alanı S (m^2)
    wing_span_b: float = 1.60              # Kanat açıklığı b (m)
    mean_aerodynamic_chord_c: float = 0.35 # Ortalama aerodinamik veter c (m)
    aspect_ratio: float = 4.65             # Açıklık oranı AR = b^2 / S

    # Aerodinamik Taşıma (Lift) Katsayıları
    cl_0: float = 0.25                     # Sıfır hücum açısındaki taşıma katsayısı
    cl_alpha: float = 4.8                  # Taşıma eğrisi eğimi (1/rad)
    cl_delta_e: float = 0.40               # İrtifa dümeni (elevator) taşıma etkinliği
    cl_max: float = 1.35                   # Maksimum taşıma katsayısı (stall öncesi)
    alpha_stall_deg: float = 14.5          # Perdövites (stall) kritik hücum açısı (derece)

    # Aerodinamik Sürükleme (Drag) Katsayıları
    cd_0: float = 0.032                    # Parazit sürükleme katsayısı
    oswald_eff_e: float = 0.82             # Oswald kanat verimlilik faktörü
    cd_delta_e: float = 0.015              # Dümen sapması indüklenmiş sürükleme

    # Yan Kuvvet (Sideforce) Katsayıları
    cy_beta: float = -0.32                 # Kayma açısı yan kuvvet katsayısı (1/rad)
    cy_delta_r: float = 0.15               # İstikamet dümeni (rudder) yan kuvvet katsayısı

    # Yunuslama Momenti (Pitching Moment - M)
    cm_0: float = 0.02                     # Sıfır açıda yunuslama momenti
    cm_alpha: float = -0.65                # Statik boyuna kararlılık türevi (negatif = kararlı)
    cm_q: float = -9.5                     # Yunuslama sönüm katsayısı
    cm_delta_e: float = -1.15              # İrtifa dümeni yunuslama momenti yetkisi

    # Yalpalama Momenti (Rolling Moment - L)
    cl_roll_beta: float = -0.12            # Dihedral etkisi (1/rad)
    cl_roll_p: float = -0.48               # Yalpalama sönüm türevi
    cl_roll_r: float = 0.14                # Sapma-yalpalama çapraz kuplajı
    cl_roll_delta_a: float = 0.22          # Kanatçık (aileron) kontrol etkinliği

    # Sapma Momenti (Yawing Moment - N)
    cn_beta: float = 0.14                  # Yönsel statik kararlılık (pozitif = kararlı)
    cn_p: float = -0.04                    # Yalpalama-sapma kuplajı
    cn_r: float = -0.18                    # Sapma sönüm türevi
    cn_delta_r: float = -0.09              # İstikamet dümeni kontrol etkinliği

    # İtki Sistemi
    max_thrust_n: float = 28.0             # Maksimum statik itki kuvveti (Newton)
    motor_time_constant_s: float = 0.08    # Gaz kolu tepki zaman sabiti (sn)
    max_load_factor_g: float = 6.0         # Maksimum müsaade edilen G yükü


@dataclass
class FlightControls6DoF:
    """Uçuş kontrol yüzeyleri ve motor girdileri [-1.0, 1.0] veya [0.0, 1.0]."""
    throttle: float = 0.5                  # Motor gazı [0.0 - 1.0]
    elevator: float = 0.0                  # İrtifa dümeni [-1.0 (aşağı burun) .. +1.0 (yukarı burun)] rad/norm
    aileron: float = 0.0                   # Kanatçık [-1.0 (sol) .. +1.0 (sağ)]
    rudder: float = 0.0                    # İstikamet dümeni [-1.0 (sol) .. +1.0 (sağ)]


@dataclass
class State6DoF:
    """6 Serbestlik Dereceli Tam Durum Vektörü."""
    # NED Konumu (metre)
    pos_n: float = 0.0                     # Kuzey (North)
    pos_e: float = 0.0                     # Doğu (East)
    pos_d: float = -100.0                  # Aşağı (Down, negatif = irtifa)

    # Gövde Hızları (Body Velocities, m/s)
    u: float = 22.0                        # İleri (Forward)
    v: float = 0.0                         # Sağa (Right)
    w: float = 0.0                         # Aşağı (Down)

    # Euler Açıları (Radyan)
    phi: float = 0.0                       # Yalpalama (Roll)
    theta: float = 0.0                     # Yunuslama (Pitch)
    psi: float = 0.0                       # Sapma / Baş açısı (Yaw/Heading)

    # Gövde Açısal Hızları (Body Angular Rates, rad/s)
    p: float = 0.0                         # Roll hızı
    q: float = 0.0                         # Pitch hızı
    r: float = 0.0                         # Yaw hızı

    # Dahili itki durumu
    current_thrust_n: float = 12.0

    @property
    def altitude_m(self) -> float:
        """İrtifa (metre cinsinden -pos_d)."""
        return -self.pos_d

    @property
    def airspeed_mps(self) -> float:
        """Hava sürati (m/s)."""
        return math.sqrt(self.u ** 2 + self.v ** 2 + self.w ** 2)

    @property
    def alpha_rad(self) -> float:
        """Hücum açısı (Angle of Attack, rad)."""
        return math.atan2(self.w, max(0.1, self.u))

    @property
    def beta_rad(self) -> float:
        """Kayma açısı (Sideslip angle, rad)."""
        vt = self.airspeed_mps
        if vt < 0.1:
            return 0.0
        return math.asin(np.clip(self.v / vt, -1.0, 1.0))


class AtmosphereISA:
    """Uluslararası Standart Atmosfer (ISA) Modeli."""

    G0 = 9.80665                           # Yerçekimi ivmesi (m/s^2)
    R_GAS = 287.05287                      # Özgül gaz sabiti (J/(kg*K))
    GAMMA = 1.40                           # İzentropik genleşme katsayısı
    T0 = 288.15                            # Deniz seviyesi sıcaklık (K)
    P0 = 101325.0                          # Deniz seviyesi basınç (Pa)
    RHO0 = 1.225                           # Deniz seviyesi hava yoğunluğu (kg/m^3)
    LAPSE_RATE = 0.0065                    # Troposfer sıcaklık gradyanı (K/m)

    @classmethod
    def get_conditions(cls, altitude_m: float) -> Tuple[float, float, float, float]:
        """Verilen irtifada (rho, pressure, temperature, sound_speed) döner."""
        h = max(0.0, min(11000.0, altitude_m))
        t = cls.T0 - cls.LAPSE_RATE * h
        p = cls.P0 * math.pow(t / cls.T0, (cls.G0 / (cls.LAPSE_RATE * cls.R_GAS)))
        rho = p / (cls.R_GAS * t)
        a = math.sqrt(cls.GAMMA * cls.R_GAS * t)
        return rho, p, t, a


class Aerodynamics6DoF:
    """
    6 Serbestlik Dereceli Non-Linear Uçuş Mekaniği ve Simülasyon Motoru.
    """

    def __init__(self, params: Optional[AircraftParameters] = None, initial_state: Optional[State6DoF] = None):
        self.params = params or AircraftParameters()
        self.state = initial_state or State6DoF()
        self.last_load_factor_g: float = 1.0
        self.is_stalled: bool = False

    def reset(self, initial_state: Optional[State6DoF] = None):
        """Simülatörü belirtilen duruma sıfırlar."""
        self.state = initial_state or State6DoF()
        self.last_load_factor_g = 1.0
        self.is_stalled = False

    def compute_aerodynamic_coefficients(self, alpha: float, beta: float,
                                         controls: FlightControls6DoF,
                                         p: float, q: float, r: float,
                                         airspeed: float) -> Tuple[float, float, float, float, float, float]:
        """
        Kuvvet ve moment katsayılarını hesaplar:
        (CL, CD, CY, Cl_roll, Cm_pitch, Cn_yaw)
        """
        p_ref = self.params
        vt = max(1.0, airspeed)

        # Boyutsuz açısal hızlar
        q_bar = (q * p_ref.mean_aerodynamic_chord_c) / (2.0 * vt)
        p_bar = (p * p_ref.wing_span_b) / (2.0 * vt)
        r_bar = (r * p_ref.wing_span_b) / (2.0 * vt)

        # Perdövites (Stall) modellemesi
        alpha_deg = math.degrees(alpha)
        alpha_stall = p_ref.alpha_stall_deg

        if abs(alpha_deg) < alpha_stall:
            cl = p_ref.cl_0 + p_ref.cl_alpha * alpha + p_ref.cl_delta_e * controls.elevator
            self.is_stalled = False
        else:
            # Post-stall (Stall sonrası taşıma kaybı ve düz plaka davranışı)
            sign = 1.0 if alpha >= 0 else -1.0
            stall_decay = math.cos(math.radians(alpha_deg - sign * alpha_stall))
            cl = sign * p_ref.cl_max * max(0.1, stall_decay) + p_ref.cl_delta_e * controls.elevator * 0.3
            self.is_stalled = True

        # Sürükleme kutbu (Drag polar): CD = CD0 + k * CL^2
        k_induced = 1.0 / (math.pi * p_ref.aspect_ratio * p_ref.oswald_eff_e)
        cd = p_ref.cd_0 + k_induced * (cl ** 2) + p_ref.cd_delta_e * abs(controls.elevator)
        if self.is_stalled:
            cd += 0.25 * math.sin(abs(alpha)) ** 2  # Stall kaynaklı yüksek direnç

        # Yan kuvvet
        cy = p_ref.cy_beta * beta + p_ref.cy_delta_r * controls.rudder

        # Momentler
        # Yunuslama (Pitch)
        cm = (p_ref.cm_0 + p_ref.cm_alpha * alpha +
              p_ref.cm_q * q_bar + p_ref.cm_delta_e * controls.elevator)

        # Yalpalama (Roll)
        cl_roll = (p_ref.cl_roll_beta * beta +
                   p_ref.cl_roll_p * p_bar +
                   p_ref.cl_roll_r * r_bar +
                   p_ref.cl_roll_delta_a * controls.aileron)

        # Sapma (Yaw)
        cn = (p_ref.cn_beta * beta +
              p_ref.cn_p * p_bar +
              p_ref.cn_r * r_bar +
              p_ref.cn_delta_r * controls.rudder)

        return cl, cd, cy, cl_roll, cm, cn

    def step(self, controls: FlightControls6DoF, dt: float = 0.02) -> State6DoF:
        """
        4. Derece Runge-Kutta (RK4) sayısal integrasyonu ile zaman adımı ilerletir.
        """
        dt = max(0.001, min(0.1, dt))

        # RK4 adımları
        k1 = self._derivatives(self.state, controls)
        s_k2 = self._apply_derivative(self.state, k1, dt * 0.5)
        k2 = self._derivatives(s_k2, controls)
        s_k3 = self._apply_derivative(self.state, k2, dt * 0.5)
        k3 = self._derivatives(s_k3, controls)
        s_k4 = self._apply_derivative(self.state, k3, dt)
        k4 = self._derivatives(s_k4, controls)

        # Durumu güncelle
        combined_deriv = {}
        for key in k1:
            combined_deriv[key] = (k1[key] + 2.0 * k2[key] + 2.0 * k3[key] + k4[key]) / 6.0

        self.state = self._apply_derivative(self.state, combined_deriv, dt)

        # Euler açılarını normalize et (-pi..pi)
        self.state.phi = (self.state.phi + math.pi) % (2 * math.pi) - math.pi
        self.state.theta = np.clip(self.state.theta, -math.pi / 2.0 + 0.01, math.pi / 2.0 - 0.01)
        self.state.psi = (self.state.psi + math.pi) % (2 * math.pi) - math.pi

        return self.state

    def _derivatives(self, s: State6DoF, controls: FlightControls6DoF) -> Dict[str, float]:
        """Tüm durum değişkenlerinin zamana göre türevlerini hesaplar."""
        p_ref = self.params
        rho, _, _, _ = AtmosphereISA.get_conditions(s.altitude_m)
        vt = s.airspeed_mps
        q_inf = 0.5 * rho * (vt ** 2)

        alpha = s.alpha_rad
        beta = s.beta_rad

        # Aerodinamik katsayılar
        cl, cd, cy, cl_roll, cm, cn = self.compute_aerodynamic_coefficients(
            alpha=alpha, beta=beta, controls=controls,
            p=s.p, q=s.q, r=s.r, airspeed=vt
        )

        # Boyutsal aerodinamik kuvvetler (Rüzgar ekseni -> Gövde ekseni dönüşümü)
        lift = q_inf * p_ref.wing_area_s * cl
        drag = q_inf * p_ref.wing_area_s * cd
        sideforce = q_inf * p_ref.wing_area_s * cy

        ca = math.cos(alpha)
        sa = math.sin(alpha)
        cb = math.cos(beta)
        sb = math.sin(beta)

        # Rüzgardan gövdeye aerodinamik kuvvet bileşenleri
        fx_aero = -drag * ca + lift * sa
        fy_aero = sideforce
        fz_aero = -drag * sa - lift * ca

        # İtki kuvveti (motor dinamikleri)
        target_thrust = np.clip(controls.throttle, 0.0, 1.0) * p_ref.max_thrust_n
        d_thrust = (target_thrust - s.current_thrust_n) / p_ref.motor_time_constant_s
        thrust_x = s.current_thrust_n

        # Yerçekimi kuvvetleri (NED -> Gövde ekseni)
        g0 = AtmosphereISA.G0
        m = p_ref.mass_kg
        fx_grav = -m * g0 * math.sin(s.theta)
        fy_grav = m * g0 * math.cos(s.theta) * math.sin(s.phi)
        fz_grav = m * g0 * math.cos(s.theta) * math.cos(s.phi)

        # Toplam Gövde Kuvvetleri
        fx = fx_aero + thrust_x + fx_grav
        fy = fy_aero + fy_grav
        fz = fz_aero + fz_grav

        # G-Yükü hesabı (Aerodinamik Z ivmesi)
        self.last_load_factor_g = -fz_aero / (m * g0)

        # Gövde doğrusal ivmeleri (u_dot, v_dot, w_dot)
        u_dot = s.r * s.v - s.q * s.w + (fx / m)
        v_dot = s.p * s.w - s.r * s.u + (fy / m)
        w_dot = s.q * s.u - s.p * s.v + (fz / m)

        # Boyutsal Momentler
        s_b = p_ref.wing_area_s * p_ref.wing_span_b
        s_c = p_ref.wing_area_s * p_ref.mean_aerodynamic_chord_c
        l_tot = q_inf * s_b * cl_roll
        m_tot = q_inf * s_c * cm
        n_tot = q_inf * s_b * cn

        # Açısal ivmeler (p_dot, q_dot, r_dot) - Eylemsizlik tensörü çözümü
        ixx, iyy, izz, ixz = p_ref.ixx, p_ref.iyy, p_ref.izz, p_ref.ixz
        gamma = ixx * izz - ixz ** 2

        p_dot = (izz * l_tot + ixz * n_tot - (izz * (izz - iyy) + ixz ** 2) * s.q * s.r +
                 ixz * (ixx - iyy + izz) * s.p * s.q) / gamma
        q_dot = (m_tot - (ixx - izz) * s.p * s.r - ixz * (s.p ** 2 - s.r ** 2)) / iyy
        r_dot = (ixz * l_tot + ixx * n_tot + (ixx * (ixx - iyy) + ixz ** 2) * s.p * s.q -
                 ixz * (ixx - iyy + izz) * s.q * s.r) / gamma

        # Euler açı türevleri (phi_dot, theta_dot, psi_dot)
        s_theta = math.sin(s.theta)
        c_theta = math.cos(s.theta)
        t_theta = math.tan(s.theta)
        s_phi = math.sin(s.phi)
        c_phi = math.cos(s.phi)

        phi_dot = s.p + (s.q * s_phi + s.r * c_phi) * t_theta
        theta_dot = s.q * c_phi - s.r * s_phi
        psi_dot = (s.q * s_phi + s.r * c_phi) / max(0.001, c_theta)

        # Seyrüsefer Kinematikleri (NED hızları: pos_n_dot, pos_e_dot, pos_d_dot)
        c_psi = math.cos(s.psi)
        s_psi = math.sin(s.psi)

        # Dönüşüm Matrisi R_b_to_ned
        r11 = c_theta * c_psi
        r12 = s_phi * s_theta * c_psi - c_phi * s_psi
        r13 = c_phi * s_theta * c_psi + s_phi * s_psi

        r21 = c_theta * s_psi
        r22 = s_phi * s_theta * s_psi + c_phi * c_psi
        r23 = c_phi * s_theta * s_psi - s_phi * c_psi

        r31 = -math.sin(s.theta)
        r32 = s_phi * c_theta
        r33 = c_phi * c_theta

        pos_n_dot = r11 * s.u + r12 * s.v + r13 * s.w
        pos_e_dot = r21 * s.u + r22 * s.v + r23 * s.w
        pos_d_dot = r31 * s.u + r32 * s.v + r33 * s.w

        return {
            "pos_n": pos_n_dot,
            "pos_e": pos_e_dot,
            "pos_d": pos_d_dot,
            "u": u_dot,
            "v": v_dot,
            "w": w_dot,
            "phi": phi_dot,
            "theta": theta_dot,
            "psi": psi_dot,
            "p": p_dot,
            "q": q_dot,
            "r": r_dot,
            "thrust": d_thrust
        }

    def _apply_derivative(self, s: State6DoF, d: Dict[str, float], dt: float) -> State6DoF:
        """Türevleri duruma ekleyerek yeni bir State6DoF nesnesi döner."""
        return State6DoF(
            pos_n=s.pos_n + d["pos_n"] * dt,
            pos_e=s.pos_e + d["pos_e"] * dt,
            pos_d=s.pos_d + d["pos_d"] * dt,
            u=s.u + d["u"] * dt,
            v=s.v + d["v"] * dt,
            w=s.w + d["w"] * dt,
            phi=s.phi + d["phi"] * dt,
            theta=s.theta + d["theta"] * dt,
            psi=s.psi + d["psi"] * dt,
            p=s.p + d["p"] * dt,
            q=s.q + d["q"] * dt,
            r=s.r + d["r"] * dt,
            current_thrust_n=max(0.0, s.current_thrust_n + d["thrust"] * dt)
        )

    def trim_level_flight(self, target_airspeed_mps: float = 22.0, target_altitude_m: float = 80.0) -> FlightControls6DoF:
        """
        Düz ve ufki uçuş (Straight & Level Flight) için dengeleyici (trim) gaz ve elevatör değerlerini bulur.
        Lift = Weight = m * g
        Thrust = Drag = CD * q_inf * S
        """
        p_ref = self.params
        rho, _, _, _ = AtmosphereISA.get_conditions(target_altitude_m)
        q_inf = 0.5 * rho * (target_airspeed_mps ** 2)
        weight = p_ref.mass_kg * AtmosphereISA.G0

        # Gerekli taşıma katsayısı
        cl_required = weight / max(1.0, q_inf * p_ref.wing_area_s)
        cl_required = min(cl_required, p_ref.cl_max * 0.85)

        # Denge hücum açısı ve elevatör tahmini
        alpha_trim = (cl_required - p_ref.cl_0) / p_ref.cl_alpha
        elevator_trim = -(p_ref.cm_0 + p_ref.cm_alpha * alpha_trim) / max(0.1, abs(p_ref.cm_delta_e))
        elevator_trim = np.clip(elevator_trim, -0.4, 0.4)

        # Gerekli sürükleme ve itki
        k_induced = 1.0 / (math.pi * p_ref.aspect_ratio * p_ref.oswald_eff_e)
        cd_trim = p_ref.cd_0 + k_induced * (cl_required ** 2)
        thrust_required = cd_trim * q_inf * p_ref.wing_area_s
        throttle_trim = np.clip(thrust_required / p_ref.max_thrust_n, 0.1, 0.95)

        return FlightControls6DoF(
            throttle=float(throttle_trim),
            elevator=float(elevator_trim),
            aileron=0.0,
            rudder=0.0
        )
