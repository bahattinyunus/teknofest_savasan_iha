"""
AeroCombat - Nöral ve Taktiksel İt Dalaşı Pilot Karar Motoru (Neural Combat Pilot).

DARPA ACE (Air Combat Evolution) ve AlphaDogfight programlarından esinlenerek
geliştirilmiş bu modül, hava-hava it dalaşı geometrisini (3D relative combat geometry),
özgül enerji seviyelerini (Boyd E-M Energy-Maneuverability) ve Silah İstihdam Bölgesini
(WEZ - Weapons Employment Zone) değerlendirerek gerçek zamanlı optimal manevra üretir:

1. Çok Boyutlu Muharebe Durum Tensörü (Combat State Tensor)
   - ATA (Antenna Train Angle - Burun Açısal Hatası)
   - AA (Aspect Angle - Hedefin Kuyruk Açısı)
   - Kapanma Hızı (Closure Rate V_c = -dR/dt)
   - Göreli Enerji Üstünlüğü (Specific Energy Delta dEs)
   - WEZ (Weapons Employment Zone) Kilit Olasılığı

2. Taktiksel Fayda (Utility) Fonksiyonları ve Çok Kriterli Karar Verme
3. Otonom Manevra Seçicisi:
   - Lead Pursuit (Öncü Takip - WEZ'e hızlı giriş)
   - Pure Pursuit (Saf Takip - Doğrudan burun yönlendirmesi)
   - Lag Pursuit (Gecikmeli Takip - Enerji koruma ve overshoot önleme)
   - High Yo-Yo (Aşırı hız/overshoot durumunda irtifaya tırmanıp enerjiyi koruyarak arkaya sarkma)
   - Low Yo-Yo (Kapanma hızını artırmak ve menzili kapatmak için dalış)
   - Defensive Break & Scissors (Kuyruk tehdidi algılandığında sert kaçış ve enerji tuzağı)
"""

import math
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Any, Tuple, Optional
import numpy as np


class CombatRole(Enum):
    OFFENSIVE = "OFFENSIVE"       # Taarruz: Hedef bizim önümüzde, kilitlenme pozisyonu arıyoruz
    DEFENSIVE = "DEFENSIVE"       # Savunma: Hedef arkamızda, kilitlenmek üzere; kaçış şart
    NEUTRAL = "NEUTRAL"           # Nötr: Kafa kafaya (Head-on) veya yan geçiş
    ENERGY_CONSERVATION = "ENERGY_CONSERVATION"  # Enerji Tazeleme: Hız/İrtifa kritik


class TacticalManeuver(Enum):
    PURE_PURSUIT = "PURE_PURSUIT"
    LEAD_PURSUIT = "LEAD_PURSUIT"
    LAG_PURSUIT = "LAG_PURSUIT"
    HIGH_YOYO = "HIGH_YOYO"
    LOW_YOYO = "LOW_YOYO"
    DEFENSIVE_BREAK = "DEFENSIVE_BREAK"
    BARREL_ROLL = "BARREL_ROLL"
    ENERGY_CLIMB = "ENERGY_CLIMB"


@dataclass
class CombatStateTensor:
    """Hava muharebesi durum tensörü ve geometrik metrikleri."""
    range_m: float                         # Hedefe olan mesafe (metre)
    closure_rate_mps: float                # Kapanma hızı (m/s, pozitif = yaklaşıyor)
    ata_deg: float                         # Antenna Train Angle (Bizim burnumuz ile hedef arası açı, 0-180°)
    aspect_angle_deg: float                # Aspect Angle (Hedefin kuyruğu ile görüş hattı açısı, 0-180°)
    relative_altitude_m: float             # Hedef irtifası - Bizim irtifamız (metre)
    own_airspeed_mps: float                # Kendi hava süratimiz (m/s)
    target_airspeed_mps: float             # Hedef hava sürati (m/s)
    energy_advantage_m: float              # Özgül enerji farkı: Es_own - Es_target
    wez_score: float                       # Weapons Employment Zone skoru [0.0 - 1.0]
    geofence_margin_m: float               # En yakın geofence sınırına olan emniyet marjı


@dataclass
class ManeuverCommand:
    """Taktik pilotun otopilota ilettiği nihai uçuş komutları."""
    maneuver_name: TacticalManeuver
    role: CombatRole
    target_heading_deg: float              # Hedef baş açısı [0 - 360°)
    target_pitch_deg: float                # Hedef yunuslama açısı [-30° .. +30°]
    target_roll_deg: float                 # Hedef yatış/roll açısı [-65° .. +65°]
    target_airspeed_mps: float             # İstenen hava sürati
    throttle_cmd: float                    # Gaz kolu [0.0 - 1.0]
    g_load_target: float                   # Hedeflenen manevra G-yükü
    explanation: str                       # Taktiksel gerekçe


class NeuralCombatPilot:
    """
    Askeri / Nöral İt Dalaşı Karar Ajanı.
    """

    def __init__(self,
                 corner_speed_mps: float = 24.0,
                 max_roll_deg: float = 65.0,
                 max_pitch_deg: float = 28.0,
                 min_airspeed_mps: float = 14.0,
                 max_airspeed_mps: float = 38.0):
        self.corner_speed_mps = corner_speed_mps
        self.max_roll_deg = max_roll_deg
        self.max_pitch_deg = max_pitch_deg
        self.min_airspeed_mps = min_airspeed_mps
        self.max_airspeed_mps = max_airspeed_mps

        # Önceki durum geçmişi (kapanma hızı türevi için)
        self._prev_range: Optional[float] = None
        self._prev_time: Optional[float] = None
        self.last_maneuver: TacticalManeuver = TacticalManeuver.PURE_PURSUIT

    def compute_state_tensor(self,
                             own_pos_ned: Tuple[float, float, float],
                             own_vel_ned: Tuple[float, float, float],
                             target_pos_ned: Tuple[float, float, float],
                             target_vel_ned: Tuple[float, float, float],
                             geofence_dist_m: float = 100.0,
                             timestamp: float = 0.0) -> CombatStateTensor:
        """
        Kendi İHA'mız ve Hedef İHA durumlarından hava-hava muharebe durum tensörünü hesaplar.
        """
        # Konum ve Mesafe Vektörleri
        r_n = target_pos_ned[0] - own_pos_ned[0]
        r_e = target_pos_ned[1] - own_pos_ned[1]
        r_d = target_pos_ned[2] - own_pos_ned[2]
        dist_3d = max(0.5, math.sqrt(r_n ** 2 + r_e ** 2 + r_d ** 2))

        # Hız büyüklükleri ve LOS (Görüş Hattı) birim vektörü
        los_u = np.array([r_n, r_e, r_d]) / dist_3d

        own_v = np.array(own_vel_ned)
        tgt_v = np.array(target_vel_ned)
        own_speed = max(1.0, float(np.linalg.norm(own_v)))
        tgt_speed = max(1.0, float(np.linalg.norm(tgt_v)))

        # Kapanma Hızı (Closure rate V_c = - dR/dt = - (v_target - v_own) . u_LOS = (v_own - v_tgt) . u_LOS)
        v_rel = own_v - tgt_v
        closure_rate = float(np.dot(v_rel, los_u))

        # Antenna Train Angle (ATA): Bizim hız vektörümüz ile LOS arasındaki açı
        cos_ata = np.clip(np.dot(own_v / own_speed, los_u), -1.0, 1.0)
        ata_deg = math.degrees(math.acos(cos_ata))

        # Aspect Angle (AA): Hedefin hız vektörü ile Görüş Hattı (LOS) arasındaki açı
        # Hedef bizden uzaklaşıyorsa (kuyruğu bize dönük): cos_aa = 1.0 -> AA = 0° (Tail Chase)
        # Hedef bize doğru geliyorsa (burnu bize dönük): cos_aa = -1.0 -> AA = 180° (Head-on)
        cos_aa = np.clip(np.dot(tgt_v / tgt_speed, los_u), -1.0, 1.0)
        aspect_angle_deg = math.degrees(math.acos(cos_aa))

        # Bağıl İrtifa (NED: d negatif yukarıdır)
        own_alt = -own_pos_ned[2]
        tgt_alt = -target_pos_ned[2]
        rel_alt = tgt_alt - own_alt

        # Özgül Enerji (Specific Energy Es = h + V^2 / (2g))
        g0 = 9.80665
        es_own = own_alt + (own_speed ** 2) / (2.0 * g0)
        es_tgt = tgt_alt + (tgt_speed ** 2) / (2.0 * g0)
        energy_advantage = es_own - es_tgt

        # Weapons Employment Zone (WEZ) Kilitlenme Skoru
        # Şartname kuralı: Hedef merkezde olmalı (düşük ATA), hedef arkasında olmalı (düşük AA), menzil 15-90m
        range_score = math.exp(-((dist_3d - 35.0) ** 2) / (2.0 * (25.0 ** 2)))
        angle_score = math.cos(math.radians(min(90.0, ata_deg))) * math.cos(math.radians(min(90.0, aspect_angle_deg * 0.5)))
        wez_score = float(np.clip(range_score * max(0.0, angle_score), 0.0, 1.0))

        return CombatStateTensor(
            range_m=dist_3d,
            closure_rate_mps=closure_rate,
            ata_deg=ata_deg,
            aspect_angle_deg=aspect_angle_deg,
            relative_altitude_m=rel_alt,
            own_airspeed_mps=own_speed,
            target_airspeed_mps=tgt_speed,
            energy_advantage_m=energy_advantage,
            wez_score=wez_score,
            geofence_margin_m=geofence_dist_m
        )

    def evaluate_role(self, state: CombatStateTensor) -> CombatRole:
        """Mevcut muharebe rolünü (Taarruz, Savunma, Nötr, Enerji) sınıflandırır."""
        # 1. Enerji acil durumu
        if state.own_airspeed_mps < self.min_airspeed_mps + 2.0:
            return CombatRole.ENERGY_CONSERVATION

        # 2. Savunma durumu: Hedef arkamızda (ATA > 110° veya AA > 140°) ve yakın
        if (state.ata_deg > 110.0 or state.aspect_angle_deg > 140.0) and state.range_m < 80.0:
            return CombatRole.DEFENSIVE

        # 3. Taarruz durumu: Hedef ön sektörümüzde
        if state.ata_deg < 65.0 and state.aspect_angle_deg < 110.0:
            return CombatRole.OFFENSIVE

        return CombatRole.NEUTRAL

    def select_maneuver(self,
                        state: CombatStateTensor,
                        own_pos_ned: Tuple[float, float, float],
                        target_pos_ned: Tuple[float, float, float],
                        target_vel_ned: Tuple[float, float, float]) -> ManeuverCommand:
        """
        Durum tensörünü değerlendirerek optimal taktik manevrayı ve uçuş komutlarını seçer.
        """
        role = self.evaluate_role(state)

        # Görüş açısı ve hedef istikameti
        dx = target_pos_ned[0] - own_pos_ned[0]
        dy = target_pos_ned[1] - own_pos_ned[1]
        los_heading_deg = (math.degrees(math.atan2(dy, dx)) + 360.0) % 360.0

        # Varsayılan değerler
        cmd_heading = los_heading_deg
        cmd_pitch = 0.0
        cmd_roll = 0.0
        cmd_throttle = 0.65
        cmd_speed = self.corner_speed_mps
        g_load = 1.0
        maneuver = TacticalManeuver.PURE_PURSUIT
        explanation = "Standart takip"

        # GEOFENCE EMNİYETİ: Eğer sınır ihlali riski varsa öncelikli olarak merkeze dön
        if state.geofence_margin_m < 30.0:
            cmd_roll = 45.0
            cmd_pitch = 5.0
            cmd_throttle = 0.70
            explanation = "Geofence sınır emniyeti: Sahanın merkezine kaçış"
            return ManeuverCommand(
                maneuver_name=TacticalManeuver.DEFENSIVE_BREAK,
                role=role,
                target_heading_deg=cmd_heading,
                target_pitch_deg=cmd_pitch,
                target_roll_deg=cmd_roll,
                target_airspeed_mps=cmd_speed,
                throttle_cmd=cmd_throttle,
                g_load_target=2.0,
                explanation=explanation
            )

        if role == CombatRole.DEFENSIVE:
            # SAVUNMA: Düşmanın silah ekseninden (WEZ) ani çıkış için Break Turn & Scissors
            maneuver = TacticalManeuver.DEFENSIVE_BREAK
            # Dik dönüş: En yüksek anlık dönüş hızı (Corner speed) ve maksimum Roll
            cmd_roll = -self.max_roll_deg if dx > 0 else self.max_roll_deg
            cmd_pitch = -8.0  # Hafif dalışla hızı ve G-marjını koru
            cmd_heading = (los_heading_deg + 90.0) % 360.0
            cmd_throttle = 1.0
            cmd_speed = self.corner_speed_mps * 1.15
            g_load = 3.5
            explanation = "Kritik Savunma: Hedef WEZ ekseninden 3.5G Break Turn ile kaçış"

        elif role == CombatRole.ENERGY_CONSERVATION:
            # ENERJİ TAZELEME: Hücum açısını düşür, dalış yaparak stall'dan çık
            maneuver = TacticalManeuver.ENERGY_CLIMB if state.own_airspeed_mps > self.corner_speed_mps else TacticalManeuver.LOW_YOYO
            cmd_roll = 0.0
            cmd_pitch = -12.0 if state.own_airspeed_mps < self.min_airspeed_mps + 1.0 else 8.0
            cmd_throttle = 1.0
            cmd_speed = self.corner_speed_mps
            g_load = 1.0
            explanation = "Düşük Hız / Stall Tehlikesi: İrtifa takası ile hız kazanımı"

        elif role == CombatRole.OFFENSIVE:
            # TAARRUZ: WEZ geometrisini optimize et
            # Durum 1: Çok yakınız ve aşırı kapanma hızı var -> Tehlike: Overshoot!
            if state.range_m < 25.0 and state.closure_rate_mps > 8.0:
                maneuver = TacticalManeuver.HIGH_YOYO
                cmd_pitch = 22.0  # Kinetik enerjiyi potansiyel enerjiye çevirerek tırman
                cmd_roll = 25.0
                cmd_throttle = 0.45
                cmd_speed = self.corner_speed_mps * 0.9
                g_load = 2.5
                explanation = "High Yo-Yo: Hedefin önüne taşmayı (overshoot) önlemek için dikey tırmanış"

            # Durum 2: Hedef kaçıyor, menzil açılıyor -> Low Yo-Yo ile hızlan ve menzili kapat
            elif state.range_m > 60.0 and state.closure_rate_mps < 1.0:
                maneuver = TacticalManeuver.LOW_YOYO
                cmd_pitch = -15.0  # Dalış yaparak potansiyel enerjiyi hıza dönüştür
                cmd_roll = 15.0
                cmd_throttle = 1.0
                cmd_speed = self.max_airspeed_mps * 0.95
                g_load = 1.8
                explanation = "Low Yo-Yo: Menzili hızla kapatmak ve hedefin 6 hizasına girmek için dalış"

            # Durum 3: Hedef dönüşte -> Lead Pursuit ile hedefin dönüş merkezinin önüne yönel
            elif state.ata_deg > 18.0:
                maneuver = TacticalManeuver.LEAD_PURSUIT
                # Hedef hız vektörü yönünde önleme açısı (Lead angle) ekle
                tgt_head = (math.degrees(math.atan2(target_vel_ned[1], target_vel_ned[0])) + 360.0) % 360.0
                lead_offset = np.clip(state.ata_deg * 0.6, -25.0, 25.0)
                cmd_heading = (los_heading_deg + lead_offset) % 360.0
                cmd_roll = np.clip(lead_offset * 2.0, -self.max_roll_deg, self.max_roll_deg)
                cmd_pitch = np.clip(state.relative_altitude_m * 0.2, -15.0, 15.0)
                cmd_throttle = 0.85
                cmd_speed = self.corner_speed_mps
                g_load = 2.2
                explanation = "Lead Pursuit: Hedefin dönüş eğrisi içine önleme açısıyla yönelme"

            # Durum 4: Mükemmel hizalanma -> Pure Pursuit (Kilitlenme sayacını doldur!)
            else:
                maneuver = TacticalManeuver.PURE_PURSUIT
                cmd_heading = los_heading_deg
                cmd_pitch = np.clip(state.relative_altitude_m * 0.15, -10.0, 10.0)
                cmd_roll = 0.0
                cmd_throttle = np.clip(0.6 + (state.range_m - 35.0) * 0.015, 0.4, 0.95)
                cmd_speed = state.target_airspeed_mps
                g_load = 1.0
                explanation = "Pure Pursuit: Tam eksende 4.0s kilitlenme tutma fazı"

        else:
            # NÖTR (Head-on veya geçiş)
            maneuver = TacticalManeuver.LAG_PURSUIT
            # Enerji avantajını koruyarak hedefin arkasına dön
            cmd_heading = los_heading_deg
            cmd_pitch = 8.0
            cmd_roll = 35.0
            cmd_throttle = 0.80
            cmd_speed = self.corner_speed_mps
            explanation = "Nötr Karşılama: Lag pursuit ile hedefin dönüş kuyruğuna yerleşme"

        self.last_maneuver = maneuver
        return ManeuverCommand(
            maneuver_name=maneuver,
            role=role,
            target_heading_deg=cmd_heading,
            target_pitch_deg=cmd_pitch,
            target_roll_deg=cmd_roll,
            target_airspeed_mps=cmd_speed,
            throttle_cmd=cmd_throttle,
            g_load_target=g_load,
            explanation=explanation
        )
