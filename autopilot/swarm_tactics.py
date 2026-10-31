import math
from enum import Enum
from typing import Dict, Any, List, Optional, Tuple
from core.models import TelemetriPaketi, RakipIHABilgisi
from core.logger import logger


class SwarmFormation(Enum):
    LINE_ABREAST = "LINE_ABREAST"       # Yan yana tarama formasyonu (Arama modu)
    FIGHTING_WING = "FIGHTING_WING"     # Lider-Kanatçı esnek takip (45 derece ofset)
    PINCER_BRACKET = "PINCER_BRACKET"   # Çift taraflı kıskaç manevrası
    BAIT_AMBUSH = "BAIT_AMBUSH"         # Tuzak & Pusu taktiği


class SwarmRole(Enum):
    LEADER = "LEADER"                   # Lider İHA
    WINGMAN = "WINGMAN"                 # Kanatçı İHA
    BAIT = "BAIT"                       # Yem / Hedef çeken İHA
    HUNTER = "HUNTER"                   # Avcı / Arkadan kilitlenen İHA


class SwarmTacticsController:
    """Çoklu İHA İş Birlikli Hava Muharebesi ve Sürü Taktikleri Yöneticisi (Multi-UAV Swarm Tactics).
    
    Taktikler:
    1. Fighting Wing Formasyonu: Kanatçı, liderin 45° arkasında ve 30-50m mesafede uçar.
    2. Bait & Ambush (Tuzak ve Pusu): Birinci İHA yem rolü üstlenerek rakibi peşine takar;
       ikinci İHA rakibin arkasına sessizce sızarak 4 saniyelik garantili kilitlenme yapar.
    3. Pincer / Bracket: İki uçak hedefi sağlı sollu 60° açıyla kıskaca alarak kaçış açısını sıfırlar.
    """

    def __init__(
        self,
        formation: SwarmFormation = SwarmFormation.FIGHTING_WING,
        role: SwarmRole = SwarmRole.LEADER,
        separation_distance_m: float = 40.0
    ):
        self.formation = formation
        self.role = role
        self.separation_distance_m = separation_distance_m

    def compute_wingman_offset_position(
        self,
        leader_lat: float,
        leader_lon: float,
        leader_alt: float,
        leader_heading_deg: float,
        side: str = "right"
    ) -> Tuple[float, float, float]:
        """Liderin konum ve yönelimine göre Kanatçının bulunması gereken ideal 3D GPS noktasını hesaplar."""
        # Fighting wing: Liderin 45° gerisi ve sağ/sol tarafı
        offset_angle = 135.0 if side == "right" else 225.0
        bearing_from_leader = (leader_heading_deg + offset_angle) % 360.0

        # Koordinat ötelemesi (yaklaşık metre hesabı)
        rad = math.radians(bearing_from_leader)
        dx_east = self.separation_distance_m * math.sin(rad)
        dy_north = self.separation_distance_m * math.cos(rad)

        lat_m = 111139.0
        lon_m = 111139.0 * math.cos(math.radians(leader_lat))

        target_lat = leader_lat + (dy_north / lat_m)
        target_lon = leader_lon + (dx_east / lon_m)
        target_alt = leader_alt + (5.0 if side == "right" else -5.0)  # Hafif irtifa ayrımı

        return target_lat, target_lon, target_alt

    def compute_pincer_attack_vectors(
        self,
        target_rival: RakipIHABilgisi,
        leader_pos: Tuple[float, float, float],
        wingman_pos: Tuple[float, float, float]
    ) -> Tuple[float, float]:
        """Kıskaç (Pincer) taktiğinde Lider ve Kanatçı için hedefe yönelik saldırı açılarını (Heading) üretir."""
        # Lider hedefe sol taraftan (-30° ofset), Kanatçı sağ taraftan (+30° ofset) yaklaşır
        lat_m = 111139.0
        lon_m = 111139.0 * math.cos(math.radians(target_rival.IHA_enlem))

        # Hedefe olan genel görüş açısı
        d_lat_l = (target_rival.IHA_enlem - leader_pos[0]) * lat_m
        d_lon_l = (target_rival.IHA_boylam - leader_pos[1]) * lon_m
        base_bearing_leader = (math.degrees(math.atan2(d_lon_l, d_lat_l)) + 360.0) % 360.0

        d_lat_w = (target_rival.IHA_enlem - wingman_pos[0]) * lat_m
        d_lon_w = (target_rival.IHA_boylam - wingman_pos[1]) * lon_m
        base_bearing_wingman = (math.degrees(math.atan2(d_lon_w, d_lat_w)) + 360.0) % 360.0

        leader_heading_cmd = (base_bearing_leader - 25.0 + 360.0) % 360.0
        wingman_heading_cmd = (base_bearing_wingman + 25.0) % 360.0

        return leader_heading_cmd, wingman_heading_cmd

    def evaluate_bait_and_ambush(
        self,
        own_tel: TelemetriPaketi,
        partner_tel: TelemetriPaketi,
        rival: RakipIHABilgisi
    ) -> Dict[str, Any]:
        """Tuzak & Pusu durum değerlendirmesi: Rakip hangi takım uçağımızın peşindeyse diğeri avcı olur."""
        lat_m = 111139.0
        lon_m = 111139.0 * math.cos(math.radians(rival.IHA_enlem))

        # Rakibin yönelim açısı (Heading)
        rival_hdg = rival.IHA_yonelme

        # Rakip -> Kendi İHA'mıza olan açı
        d_lat_own = (own_tel.IHA_enlem - rival.IHA_enlem) * lat_m
        d_lon_own = (own_tel.IHA_boylam - rival.IHA_boylam) * lon_m
        bearing_to_own = (math.degrees(math.atan2(d_lon_own, d_lat_own)) + 360.0) % 360.0
        angle_diff_own = abs((bearing_to_own - rival_hdg + 180.0) % 360.0 - 180.0)

        # Rakip -> Takım arkadaşına olan açı
        d_lat_p = (partner_tel.IHA_enlem - rival.IHA_enlem) * lat_m
        d_lon_p = (partner_tel.IHA_boylam - rival.IHA_boylam) * lon_m
        bearing_to_partner = (math.degrees(math.atan2(d_lon_p, d_lat_p)) + 360.0) % 360.0
        angle_diff_p = abs((bearing_to_partner - rival_hdg + 180.0) % 360.0 - 180.0)

        # Rakip kime daha çok bakıyor/yöneliyorsa o uçak YEM'dir, diğeri AVCI'dır
        if angle_diff_own < angle_diff_p:
            my_role = SwarmRole.BAIT
            partner_role = SwarmRole.HUNTER
            action = "Rakip seni kovalıyor! Yem rolündesin, uçağı düz ve kaçış hattında tut; takım arkadaşın arkadan kilitlenecek!"
        else:
            my_role = SwarmRole.HUNTER
            partner_role = SwarmRole.BAIT
            action = "Rakip takım arkadaşının peşinde! Avcı rolündesin, tam arkasına intikal ederek 4.0s kilitlenme başlat!"

        return {
            "my_role": my_role.value,
            "partner_role": partner_role.value,
            "target_rival_id": rival.takim_numarasi,
            "tactical_instruction": action
        }
