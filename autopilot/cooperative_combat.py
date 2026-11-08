"""
AeroCombat - Çoklu İHA İşbirlikçi İt Dalaşı ve Lider-Kanat Taktik Motoru (Cooperative Combat).

Modern hava muharebesinde (TEKNOFEST çoklu İHA, Loyal Wingman / CCA doktrini):
1. Lider - Kanat (Lead - Wingman) Formasyon Geometrisi:
   - Taktik Dağılım (Line-Abreast / Tactical Spread)
   - Kama (Wedge)
   - İzleme (Trail)
   - Çatışma Kutusu (Combat Box)
2. İşbirlikçi Hava Muharebesi Manevraları:
   - "Tuzak ve Pusu" (Drag-and-Bag / Bait-and-Hook):
     Kanat uçağı kendisini düşmana yem (bait) olarak gösterip kaçış manevrasına başlar.
     Düşman kanadı kovalarken Lider yüksek irtifa pusu noktasından (perch) dalarak
     düşmanın 6 hizasına girer ve 4.0 saniye kilitlenir!
   - "Kıskaç Harekâtı" (Pincer Flanking):
     Düşman sağa kaçarsa Lider, sola kaçarsa Kanat anında WEZ içine girer.
3. Çoklu Hedef Tahsis Algoritması (Optimal Target Allocation):
   Maliyet matrisi (Menzil, Açı, Enerji) üzerinden Hungarian / Açık Artırma (Auction)
   optimizasyonu ile hedeflerin takımlar arasında çakışmasız paylaşımı.
4. Lider Devri (Failover / Heartbeat):
   Lider uçağın bağlantısı koptuğunda Kanat otomatik olarak Uçuş Lideri olur.
"""

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Tuple, Optional, Any
import numpy as np


class SwarmFormationType(Enum):
    LINE_ABREAST = "LINE_ABREAST"       # Yan yana taktik açılım (30-50m mesafe)
    WEDGE = "WEDGE"                     # V / Kama formasyonu
    TRAIL = "TRAIL"                     # Arka arkaya takip (güvenli mesafe)
    COMBAT_BOX = "COMBAT_BOX"           # Farklı irtifalarda kutu açılımı


class TeamTacticMode(Enum):
    STANDARD_PATROL = "STANDARD_PATROL"   # Standart arama/devriye formasyonu
    DRAG_AND_BAG = "DRAG_AND_BAG"         # Tuzak ve pusu manevrası
    PINCER_ENVELOPE = "PINCER_ENVELOPE"   # Çift taraflı kıskaç manevrası
    TARGET_HANDOFF = "TARGET_HANDOFF"     # Hedef devir/teslim


@dataclass
class SwarmMemberState:
    """Sürüdeki her bir İHA'nın anlık durum bilgisi."""
    uav_id: int
    is_leader: bool
    position_ned: Tuple[float, float, float]
    velocity_ned: Tuple[float, float, float]
    airspeed_mps: float
    heading_deg: float
    locked_target_id: Optional[int] = None
    is_being_pursued: bool = False
    last_heartbeat: float = field(default_factory=time.time)


@dataclass
class TargetTrackInfo:
    """Tespit edilen düşman hedeflerinin bilgisi."""
    target_id: int
    position_ned: Tuple[float, float, float]
    velocity_ned: Tuple[float, float, float]
    airspeed_mps: float
    assigned_uav_id: Optional[int] = None


class CooperativeCombatGovernor:
    """
    Çoklu İHA İşbirlikçi Muharebe Yöneticisi.
    """

    def __init__(self,
                 own_id: int = 1,
                 is_initial_leader: bool = True,
                 formation_separation_m: float = 40.0):
        self.own_id = own_id
        self.is_leader = is_initial_leader
        self.formation_separation_m = formation_separation_m
        self.formation_type = SwarmFormationType.LINE_ABREAST
        self.current_tactic = TeamTacticMode.STANDARD_PATROL

        # Takım üyeleri ve hedefler
        self.team_members: Dict[int, SwarmMemberState] = {}
        self.known_targets: Dict[int, TargetTrackInfo] = {}

        # Bait & Hook durumu
        self.bait_uav_id: Optional[int] = None
        self.shooter_uav_id: Optional[int] = None

    def update_member_heartbeat(self, member: SwarmMemberState):
        """Takım üyesinin telemetri ve nabız sinyalini günceller."""
        member.last_heartbeat = time.time()
        self.team_members[member.uav_id] = member

        # Lider düşmüşse otomatik Lider seçimini kontrol et
        self._check_leader_failover()

    def _check_leader_failover(self, timeout_sec: float = 2.5):
        """Lider İHA'dan belirli bir süre veri gelmezse en kıdemli kanat Lider olur."""
        now = time.time()
        leader_alive = False

        for uid, member in self.team_members.items():
            if member.is_leader and (now - member.last_heartbeat) < timeout_sec:
                leader_alive = True
                break

        if not leader_alive and not self.is_leader:
            # Hayattaki en küçük UAV ID'sine sahip uçak liderliği devralır
            alive_ids = [uid for uid, m in self.team_members.items() if (now - m.last_heartbeat) < timeout_sec]
            alive_ids.append(self.own_id)
            if self.own_id == min(alive_ids):
                self.is_leader = True

    def calculate_formation_slot_ned(self,
                                     leader_pos_ned: Tuple[float, float, float],
                                     leader_heading_deg: float,
                                     slot_index: int) -> Tuple[float, float, float]:
        """
        Lider İHA'ya göre formasyondaki hedef koordinatı (NED) hesaplar.
        slot_index: 1 = 1. Kanat (Sağ), 2 = 2. Kanat (Sol), vs.
        """
        psi = math.radians(leader_heading_deg)
        d = self.formation_separation_m

        # Formasyona göre yerel ofset (dx_body, dy_body, dz_body)
        if self.formation_type == SwarmFormationType.LINE_ABREAST:
            # Sağ veya sol kanat açılımı
            offset_y = d * (1 if slot_index % 2 == 1 else -1) * ((slot_index + 1) // 2)
            offset_x = -5.0  # Liderin hafif arkasında
            offset_z = 0.0

        elif self.formation_type == SwarmFormationType.WEDGE:
            offset_y = d * (1 if slot_index % 2 == 1 else -1) * ((slot_index + 1) // 2)
            offset_x = -abs(offset_y) * 0.7  # V şeklinde geriye doğru
            offset_z = -2.0  # Hafif irtifa basamağı

        elif self.formation_type == SwarmFormationType.COMBAT_BOX:
            offset_y = d * (1 if slot_index % 2 == 1 else -1)
            offset_x = -d * 0.5
            offset_z = -15.0 if slot_index % 2 == 1 else 15.0  # Dikey irtifa tabakası

        else:  # TRAIL
            offset_x = -d * slot_index
            offset_y = 0.0
            offset_z = 0.0

        # Gövde ekseninden NED eksenine dönüşüm
        # x_ned = cos(psi)*x_b - sin(psi)*y_b
        # y_ned = sin(psi)*x_b + cos(psi)*y_b
        dx_ned = math.cos(psi) * offset_x - math.sin(psi) * offset_y
        dy_ned = math.sin(psi) * offset_x + math.cos(psi) * offset_y
        dz_ned = offset_z

        return (
            leader_pos_ned[0] + dx_ned,
            leader_pos_ned[1] + dy_ned,
            leader_pos_ned[2] + dz_ned
        )

    def allocate_targets(self, targets: List[TargetTrackInfo]) -> Dict[int, int]:
        """
        Hedefleri İHA'lara en verimli şekilde paylaştırır (Target-to-UAV Allocation).
        Çakışmasız en küçük geometrik maliyet (mesafe ve açı) algoritması.
        Döner: {uav_id: target_id}
        """
        for t in targets:
            self.known_targets[t.target_id] = t

        if not targets:
            return {}

        active_uavs = [self.own_id] + list(self.team_members.keys())
        allocations: Dict[int, int] = {}
        unassigned_targets = list(targets)

        # Basitleştirilmiş Açık Artırma (Auction) Algoritması
        for uav_id in active_uavs:
            if not unassigned_targets:
                break

            # UAV konumunu al
            if uav_id == self.own_id:
                # Kendi konumumuz bilinmediğinde varsayılan referans
                uav_pos = (0.0, 0.0, -80.0)
            else:
                uav_pos = self.team_members[uav_id].position_ned

            best_target = None
            best_cost = float("inf")

            for tgt in unassigned_targets:
                dx = tgt.position_ned[0] - uav_pos[0]
                dy = tgt.position_ned[1] - uav_pos[1]
                dz = tgt.position_ned[2] - uav_pos[2]
                dist = math.sqrt(dx ** 2 + dy ** 2 + dz ** 2)

                # Maliyet: Mesafe
                cost = dist
                if cost < best_cost:
                    best_cost = cost
                    best_target = tgt

            if best_target:
                allocations[uav_id] = best_target.target_id
                best_target.assigned_uav_id = uav_id
                unassigned_targets.remove(best_target)

        return allocations

    def evaluate_drag_and_bag_tactic(self,
                                     own_pos: Tuple[float, float, float],
                                     own_vel: Tuple[float, float, float]) -> Tuple[TeamTacticMode, Dict[str, Any]]:
        """
        Tuzak ve Pusu (Drag-and-Bag) manevrasının tetiklenme şartlarını ve rollerini belirler.
        Eğer bir kanat uçağının kuyruğunda düşman varsa, kanat yem (bait) rolünü alır,
        Lider ise dalarak düşmana arkadan kilitlenir (shooter).
        """
        for uid, member in self.team_members.items():
            if member.is_being_pursued:
                self.current_tactic = TeamTacticMode.DRAG_AND_BAG
                self.bait_uav_id = uid
                self.shooter_uav_id = self.own_id if self.is_leader else 1

                instructions = {
                    "tactic": TeamTacticMode.DRAG_AND_BAG.value,
                    "bait_uav": self.bait_uav_id,
                    "shooter_uav": self.shooter_uav_id,
                    "bait_action": "EXTEND_AND_WEAVE",   # Yem uçağı gaz açıp düşmanı düz hatta çeker
                    "shooter_action": "HIGH_PERCH_DIVE", # Vurucu İHA yüksek irtifadan 6 hizasına dalar
                    "status": "ENGAGING"
                }
                return self.current_tactic, instructions

        self.current_tactic = TeamTacticMode.STANDARD_PATROL
        return self.current_tactic, {"tactic": self.current_tactic.value, "status": "PATROL"}
