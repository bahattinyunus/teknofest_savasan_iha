"""
AeroCombat - John Boyd Enerji-Manevra (Energy-Maneuverability - E-M) Teorisi ve Uçuş Zarfı Yöneticisi

Hava muharebesinde (dogfight) uçağın sadece geometrik konumu değil, kinetik ve potansiyel enerjisinin
(Specific Excess Power - P_s ve Energy Height - H_e) hedefe üstünlüğü kritik önem taşır.
Bu modül, John Boyd'un E-M teorisine dayalı olarak optimum köşe hızını (corner velocity - V_c),
anlık ve sürdürülebilir dönüş hızlarını, 1-Circle / 2-Circle angajman taktiklerini ve
otonom perdövites (stall) önleme kararlarını hesaplar.
"""

import math
from typing import Tuple, Optional, Dict, Any
from core.models import EnergyState
from core.logger import logger


class EnergyManeuverabilityGovernor:
    """
    Savaşan İHA için E-M Teorisi ve Enerji Yönetim Motoru.
    
    Uçuş dinamikleri parametreleri:
      - m: İHA kalkış ağırlığı (kg)
      - S: Kanat alanı (m^2)
      - C_D0: Sıfır-taşıma sürükleme katsayısı
      - k: İndüklenmiş sürükleme faktörü (k = 1 / (pi * e * AR))
      - T_max: Maksimum statik itki (Newton)
      - n_max: Yapısal azami g-kuvveti limiti (örn. 4.5G)
      - C_L_max: Maksimum taşıma katsayısı (stall öncesi)
      - V_stall: Stall hızı (m/s)
    """

    GRAVITY: float = 9.80665  # m/s^2
    AIR_DENSITY_SEA_LEVEL: float = 1.225  # kg/m^3

    def __init__(
        self,
        mass_kg: float = 4.5,
        wing_area_m2: float = 0.52,
        cd0: float = 0.028,
        induced_drag_k: float = 0.045,
        max_thrust_n: float = 38.0,
        max_load_factor_g: float = 4.5,
        cl_max: float = 1.25,
        stall_speed_mps: float = 13.0,
        air_density: float = 1.225
    ):
        self.mass = max(0.5, mass_kg)
        self.wing_area = max(0.05, wing_area_m2)
        self.cd0 = max(0.005, cd0)
        self.k = max(0.01, induced_drag_k)
        self.max_thrust = max(1.0, max_thrust_n)
        self.max_load_factor = max(1.5, max_load_factor_g)
        self.cl_max = max(0.5, cl_max)
        self.stall_speed = max(5.0, stall_speed_mps)
        self.rho = max(0.5, air_density)
        self.weight = self.mass * self.GRAVITY

        # Önceden hesaplanan kritik köşe hızı (Corner Velocity V_c)
        self.corner_velocity = self.calculate_corner_velocity()

    def get_air_density(self, altitude_m: float) -> float:
        """İrtifaya bağlı ISA (International Standard Atmosphere) hava yoğunluğu hesabı."""
        alt = max(0.0, altitude_m)
        temp_k = 288.15 - 0.0065 * alt
        if temp_k <= 0:
            return self.rho
        pressure_pa = 101325.0 * math.pow((temp_k / 288.15), 5.2561)
        density = pressure_pa / (287.05 * temp_k)
        return max(0.5, density)

    def calculate_specific_energy(self, altitude_m: float, airspeed_mps: float) -> float:
        """
        Özgül Enerji Yüksekliği (Specific Energy / Energy Height - H_e):
        H_e = h + (V^2 / 2g) [metre]
        
        Uçağın toplam mekanik enerjisinin (kinetik + potansiyel) ağırlığına bölümüdür.
        """
        alt = max(0.0, altitude_m)
        v = max(0.1, airspeed_mps)
        he = alt + (v * v) / (2.0 * self.GRAVITY)
        return float(he)

    def calculate_drag(self, airspeed_mps: float, load_factor_g: float = 1.0, altitude_m: float = 50.0) -> float:
        """
        Parazit ve indüklenmiş sürükleme kuvveti hesabı (Newton):
        D = D_0 + D_i = 0.5 * rho * V^2 * S * C_D0 + (2 * k * (n * W)^2) / (rho * V^2 * S)
        """
        rho = self.get_air_density(altitude_m)
        v = max(1.0, airspeed_mps)
        q = 0.5 * rho * v * v  # Dinamik basınç
        d0 = q * self.wing_area * self.cd0

        lift_needed = abs(load_factor_g) * self.weight
        di = (self.k * (lift_needed ** 2)) / max(0.1, q * self.wing_area)
        return float(d0 + di)

    def calculate_specific_excess_power(
        self,
        altitude_m: float,
        airspeed_mps: float,
        throttle_ratio: float = 1.0,
        load_factor_g: float = 1.0
    ) -> float:
        """
        Özgül Fazla Güç (Specific Excess Power - P_s):
        P_s = (T - D) / W * V [m/s]
        
        P_s > 0 : İHA hızlanabilir veya tırmanabilir (enerji biriktirir).
        P_s = 0 : Sürdürülebilir dönüş ve seyir sınırı.
        P_s < 0 : İHA enerji kaybeder (hız veya irtifa tüketir).
        """
        v = max(1.0, airspeed_mps)
        thrust = max(0.0, min(1.0, throttle_ratio)) * self.max_thrust
        drag = self.calculate_drag(airspeed_mps=v, load_factor_g=load_factor_g, altitude_m=altitude_m)

        ps = ((thrust - drag) / self.weight) * v
        return float(ps)

    def calculate_corner_velocity(self, load_factor_limit: Optional[float] = None) -> float:
        """
        Köşe Hızı (Corner Speed / Maneuver Velocity - V_c):
        V_c = sqrt( (2 * n_max * W) / (rho * S * C_L_max) )
        
        Bu hızda aerodinamik olarak üretilebilecek azami taşıma tam olarak yapısal g-limitine
        denk gelir. Bu noktada İHA, en yüksek anlık dönüş hızına (dot{psi}_max) ve
        en dar dönüş yarıçapına (R_min) ulaşır.
        """
        n_lim = load_factor_limit if load_factor_limit is not None else self.max_load_factor
        numerator = 2.0 * n_lim * self.weight
        denominator = self.rho * self.wing_area * self.cl_max
        if denominator <= 0:
            return 25.0
        vc = math.sqrt(numerator / denominator)
        return float(vc)

    def calculate_turn_performance(
        self,
        airspeed_mps: float,
        load_factor_g: float
    ) -> Tuple[float, float]:
        """
        Verilen hız ve yük faktöründe dönüş performansı hesabı:
        Dönüş Hızı: omega = (g * sqrt(n^2 - 1)) / V  [rad/s -> deg/s]
        Dönüş Yarıçapı: R = V^2 / (g * sqrt(n^2 - 1)) [metre]
        """
        v = max(2.0, airspeed_mps)
        n = max(1.001, abs(load_factor_g))
        radial_g = math.sqrt(max(0.0001, n * n - 1.0))

        turn_rate_rad_s = (self.GRAVITY * radial_g) / v
        turn_rate_deg_s = math.degrees(turn_rate_rad_s)

        turn_radius_m = (v * v) / (self.GRAVITY * radial_g)
        return float(turn_rate_deg_s), float(turn_radius_m)

    def calculate_sustained_turn_rate(self, airspeed_mps: float, altitude_m: float = 50.0) -> float:
        """
        Sürdürülebilir Dönüş Hızı (Sustained Turn Rate - P_s = 0):
        Maksimum itkide sürüklemenin itkiye eşit olduğu en yüksek g faktörü ve dönüş hızıdır.
        """
        v = max(self.stall_speed, airspeed_mps)
        rho = self.get_air_density(altitude_m)
        q = 0.5 * rho * v * v
        d0 = q * self.wing_area * self.cd0

        excess_thrust_for_lift = self.max_thrust - d0
        if excess_thrust_for_lift <= 0:
            return 0.0

        # T_max - D_0 = (k * (n * W)^2) / (q * S)
        max_lift_sq = (excess_thrust_for_lift * q * self.wing_area) / self.k
        if max_lift_sq <= 0:
            return 0.0

        max_sustained_lift = math.sqrt(max_lift_sq)
        n_sustained = max_sustained_lift / self.weight
        n_effective = min(self.max_load_factor, n_sustained)

        if n_effective <= 1.001:
            return 0.0

        turn_rate_deg, _ = self.calculate_turn_performance(v, n_effective)
        return float(turn_rate_deg)

    def evaluate_combat_energy(
        self,
        own_alt_m: float,
        own_airspeed_mps: float,
        target_alt_m: Optional[float] = None,
        target_airspeed_mps: Optional[float] = None,
        own_throttle: float = 1.0,
        current_g: float = 1.0
    ) -> EnergyState:
        """
        Kapsamlı hava muharebesi enerji durumu analizi ve taktiksel tavsiye üretimi.
        """
        he_own = self.calculate_specific_energy(own_alt_m, own_airspeed_mps)
        ps_own = self.calculate_specific_excess_power(
            altitude_m=own_alt_m,
            airspeed_mps=own_airspeed_mps,
            throttle_ratio=own_throttle,
            load_factor_g=current_g
        )

        vc = self.calculate_corner_velocity()
        inst_turn_rate, min_radius = self.calculate_turn_performance(
            airspeed_mps=vc,
            load_factor_g=self.max_load_factor
        )
        sust_turn_rate = self.calculate_sustained_turn_rate(
            airspeed_mps=own_airspeed_mps,
            altitude_m=own_alt_m
        )

        # Hedef enerji durumu ve avantaj hesabı
        energy_advantage = 0.0
        if target_alt_m is not None and target_airspeed_mps is not None:
            he_target = self.calculate_specific_energy(target_alt_m, target_airspeed_mps)
            energy_advantage = he_own - he_target

        # Perdövites (Stall) veya kritik düşük enerji koruması
        stall_danger = (own_airspeed_mps < self.stall_speed * 1.15) or (he_own < 35.0)

        # Taktiksel Angajman Stratejisi Belirleme
        if stall_danger:
            tactic = "STALL_RECOVERY_PULL_DOWN_BOOST"
        elif energy_advantage >= 40.0:
            # Belirgin enerji avantajımız var: Dikey manevra veya 2-Circle (Rate Fight).
            # Rakip dönüşte hız kaybederken biz yüksek P_s ile enerjimizi koruyup arkasına otururuz.
            tactic = "RATE_FIGHT_2_CIRCLE"
        elif energy_advantage <= -25.0:
            # Enerji dezavantajındayız: Dönüş yarışına girilmez (kanatları yatırıp hız kanamak ölümcüldür).
            # Burun açısını hızla hedefe yönlendirip tek dönüşte kilit almaya çalışılır (1-Circle Radius Fight).
            tactic = "RADIUS_FIGHT_1_CIRCLE"
        else:
            # Enerji denk: Köşe hızına (Corner Velocity V_c) oturup optimum dönüş açısını yakala
            tactic = "CORNER_VELOCITY_INTERCEPT"

        return EnergyState(
            ozgurluk_enerjisi_He_m=round(he_own, 2),
            ozgurluk_fazla_gucu_Ps_mps=round(ps_own, 2),
            manevra_kose_hizi_Vc_mps=round(vc, 2),
            anlik_donus_hizi_dps=round(inst_turn_rate, 2),
            surdurulebilir_donus_hizi_dps=round(sust_turn_rate, 2),
            asgari_donus_yaricapi_m=round(min_radius, 2),
            enerji_avantaji_m=round(energy_advantage, 2),
            onerilen_taktik=tactic,
            perdovites_koruma_aktif=stall_danger
        )
