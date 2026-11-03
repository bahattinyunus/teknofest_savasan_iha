"""
Otonom Uçuş Görev Planlayıcısı ve Taktiksel Devriye / Arama Rota Üreticisi (Mission Planner).
Geofence sınırları içinde radar ve kamera tarama alanını maksimize eden taktiksel arama desenleri
(Zikzak / Creeping Line, Sekiz / Figure-8, Dairesel / Orbit) ve dinamik seyrüsefer dizilimi üretir.
"""

import math
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict, Any
from core.logger import logger


class SearchPattern(Enum):
    """Taktiksel Arama ve Devriye Deseni Türleri."""
    CREEPING_LINE = "CREEPING_LINE"     # Zikzak çim biçme arama deseni (Geniş alan taraması)
    FIGURE_8 = "FIGURE_8"               # Sekiz deseni (Sürekli hız ve sürekli görüş taraması)
    ORBIT_LOITER = "ORBIT_LOITER"       # Dairesel devriye
    EXPANDING_SQUARE = "EXPANDING_SQUARE" # Kayıp hedef bölgesinde merkezden dışa genişleyen kare


@dataclass
class Waypoint:
    """Tek bir seyrüsefer hedef noktası."""
    lat: float
    lon: float
    alt_m: float = 80.0
    speed_mps: float = 20.0
    id: int = 0
    name: str = "WP"
    is_intercept: bool = False


class TacticalMissionPlanner:
    """
    Yarışma görev alanı içinde taktiksel seyrüsefer ve otonom hedef arama yolları üreten planlayıcı.
    """
    def __init__(
        self,
        default_altitude_m: float = 80.0,
        default_speed_mps: float = 20.0,
        acceptance_radius_m: float = 25.0
    ):
        self.default_alt = default_altitude_m
        self.default_speed = default_speed_mps
        self.acceptance_radius = acceptance_radius_m
        
        self.waypoints: List[Waypoint] = []
        self.current_wp_idx: int = 0
        self.active_pattern: SearchPattern = SearchPattern.ORBIT_LOITER
        self._saved_patrol_waypoints: List[Waypoint] = []
        self._saved_idx: int = 0

    def generate_creeping_line(
        self,
        polygon_coords: List[List[float]],
        spacing_m: float = 80.0,
        altitude_m: Optional[float] = None,
        speed_mps: Optional[float] = None
    ) -> List[Waypoint]:
        """
        Verilen poligon içinde zikzak (Creeping Line / Lawnmower) arama deseni oluşturur.
        """
        alt = altitude_m or self.default_alt
        spd = speed_mps or self.default_speed

        if not polygon_coords or len(polygon_coords) < 3:
            logger.warning("[MissionPlanner] Yetersiz poligon koordinatı, tek nokta üretiliyor.")
            return [Waypoint(lat=41.100, lon=28.900, alt_m=alt, speed_mps=spd, id=1)]

        lats = [p[0] for p in polygon_coords]
        lons = [p[1] for p in polygon_coords]
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)

        # Enlem aralığını metreye çevir
        total_lat_m = (max_lat - min_lat) * 111139.0
        num_legs = max(2, int(total_lat_m / max(20.0, spacing_m)))
        lat_step = (max_lat - min_lat) / num_legs

        # Poligon kenarlarından %15 güvenlik payı bırak
        margin_lon = (max_lon - min_lon) * 0.15
        west_lon = min_lon + margin_lon
        east_lon = max_lon - margin_lon

        waypoints: List[Waypoint] = []
        wp_id = 1
        for i in range(num_legs + 1):
            curr_lat = min_lat + i * lat_step
            # Bir sağa bir sola zikzak
            if i % 2 == 0:
                waypoints.append(Waypoint(lat=round(curr_lat, 6), lon=round(west_lon, 6), alt_m=alt, speed_mps=spd, id=wp_id, name=f"SWEEP_{wp_id}"))
                wp_id += 1
                waypoints.append(Waypoint(lat=round(curr_lat, 6), lon=round(east_lon, 6), alt_m=alt, speed_mps=spd, id=wp_id, name=f"SWEEP_{wp_id}"))
                wp_id += 1
            else:
                waypoints.append(Waypoint(lat=round(curr_lat, 6), lon=round(east_lon, 6), alt_m=alt, speed_mps=spd, id=wp_id, name=f"SWEEP_{wp_id}"))
                wp_id += 1
                waypoints.append(Waypoint(lat=round(curr_lat, 6), lon=round(west_lon, 6), alt_m=alt, speed_mps=spd, id=wp_id, name=f"SWEEP_{wp_id}"))
                wp_id += 1

        self.waypoints = waypoints
        self.current_wp_idx = 0
        self.active_pattern = SearchPattern.CREEPING_LINE
        logger.info(f"[MissionPlanner] Creeping Line deseni oluşturuldu ({len(waypoints)} waypoint).")
        return waypoints

    def generate_figure_8(
        self,
        center_lat: float,
        center_lon: float,
        radius_m: float = 120.0,
        axis_heading_deg: float = 0.0,
        points_per_loop: int = 8,
        altitude_m: Optional[float] = None,
        speed_mps: Optional[float] = None
    ) -> List[Waypoint]:
        """
        Belirtilen merkez etrafında iki teğet daireden oluşan Sekiz (Figure-8) devriye rotası üretir.
        Uçağın sürekli sabit kanat dönüşü yaparak radarını taramasını sağlar.
        """
        alt = altitude_m or self.default_alt
        spd = speed_mps or self.default_speed
        
        waypoints: List[Waypoint] = []
        meters_per_lat = 111139.0
        meters_per_lon = 111139.0 * math.cos(math.radians(center_lat))
        
        # 1. Halka (Kuzey/İleri Halka): Merkez + Radius ofset
        axis_rad = math.radians(axis_heading_deg)
        c1_north = radius_m * math.cos(axis_rad)
        c1_east  = radius_m * math.sin(axis_rad)
        
        wp_id = 1
        for i in range(points_per_loop):
            ang = 2.0 * math.pi * (i / points_per_loop)
            dn = c1_north + radius_m * math.cos(ang)
            de = c1_east  + radius_m * math.sin(ang)
            wp_lat = center_lat + (dn / meters_per_lat)
            wp_lon = center_lon + (de / meters_per_lon)
            waypoints.append(Waypoint(lat=round(wp_lat, 6), lon=round(wp_lon, 6), alt_m=alt, speed_mps=spd, id=wp_id, name=f"FIG8_L1_{wp_id}"))
            wp_id += 1

        # 2. Halka (Güney/Geri Halka): Ters yönde dönüş
        c2_north = -radius_m * math.cos(axis_rad)
        c2_east  = -radius_m * math.sin(axis_rad)
        for i in range(points_per_loop):
            ang = -2.0 * math.pi * (i / points_per_loop)
            dn = c2_north + radius_m * math.cos(ang)
            de = c2_east  + radius_m * math.sin(ang)
            wp_lat = center_lat + (dn / meters_per_lat)
            wp_lon = center_lon + (de / meters_per_lon)
            waypoints.append(Waypoint(lat=round(wp_lat, 6), lon=round(wp_lon, 6), alt_m=alt, speed_mps=spd, id=wp_id, name=f"FIG8_L2_{wp_id}"))
            wp_id += 1

        self.waypoints = waypoints
        self.current_wp_idx = 0
        self.active_pattern = SearchPattern.FIGURE_8
        logger.info(f"[MissionPlanner] Figure-8 devriye deseni üretildi ({len(waypoints)} waypoint).")
        return waypoints

    def generate_orbit(
        self,
        center_lat: float,
        center_lon: float,
        radius_m: float = 120.0,
        num_points: int = 12,
        altitude_m: Optional[float] = None,
        speed_mps: Optional[float] = None
    ) -> List[Waypoint]:
        """Merkez nokta etrafında düzenli çokgen dairesel loiter rotası üretir."""
        alt = altitude_m or self.default_alt
        spd = speed_mps or self.default_speed

        waypoints: List[Waypoint] = []
        meters_per_lat = 111139.0
        meters_per_lon = 111139.0 * math.cos(math.radians(center_lat))

        for i in range(num_points):
            angle_rad = 2.0 * math.pi * (i / num_points)
            dn = radius_m * math.cos(angle_rad)
            de = radius_m * math.sin(angle_rad)
            wp_lat = center_lat + (dn / meters_per_lat)
            wp_lon = center_lon + (de / meters_per_lon)
            waypoints.append(Waypoint(
                lat=round(wp_lat, 6),
                lon=round(wp_lon, 6),
                alt_m=alt,
                speed_mps=spd,
                id=i + 1,
                name=f"ORBIT_{i + 1}"
            ))

        self.waypoints = waypoints
        self.current_wp_idx = 0
        self.active_pattern = SearchPattern.ORBIT_LOITER
        return waypoints

    def insert_tactical_intercept(
        self,
        target_lat: float,
        target_lon: float,
        target_alt_m: float,
        speed_mps: Optional[float] = None
    ) -> Waypoint:
        """
        Hedef tespit edildiğinde mevcut devriye rotasını dondurur ve acil önleme waypoint'i ekler.
        """
        if not self._saved_patrol_waypoints:
            self._saved_patrol_waypoints = list(self.waypoints)
            self._saved_idx = self.current_wp_idx

        intercept_wp = Waypoint(
            lat=target_lat,
            lon=target_lon,
            alt_m=target_alt_m,
            speed_mps=speed_mps or (self.default_speed + 4.0),
            id=999,
            name="INTERCEPT_TARGET",
            is_intercept=True
        )
        self.waypoints = [intercept_wp]
        self.current_wp_idx = 0
        logger.info(f"[MissionPlanner] Taktiksel Önleme Waypoint'i uygulandı -> {target_lat:.5f}, {target_lon:.5f}")
        return intercept_wp

    def resume_patrol(self) -> Optional[Waypoint]:
        """Hedef kaybedildiğinde veya kilitlenme tamamlandığında önceki devriye rotasına geri döner."""
        if self._saved_patrol_waypoints:
            self.waypoints = list(self._saved_patrol_waypoints)
            self.current_wp_idx = min(self._saved_idx, len(self.waypoints) - 1)
            self._saved_patrol_waypoints = []
            logger.info(f"[MissionPlanner] Devriye rotasına geri dönüldü (WP #{self.current_wp_idx + 1}).")
            return self.get_current_waypoint()
        return None

    def update(
        self,
        current_lat: float,
        current_lon: float,
        current_alt_m: float
    ) -> Optional[Waypoint]:
        """
        Uçağın anlık konumuna göre mevcut waypoint'e ulaşıldı mı denetler ve sıradakine ilerler.
        """
        if not self.waypoints:
            return None

        curr_wp = self.waypoints[self.current_wp_idx]
        
        # 3D Mesafe Hesabı
        d_lat_m = (curr_wp.lat - current_lat) * 111139.0
        d_lon_m = (curr_wp.lon - current_lon) * (111139.0 * math.cos(math.radians(current_lat)))
        d_alt_m = curr_wp.alt_m - current_alt_m
        dist_3d_m = math.sqrt(d_lat_m ** 2 + d_lon_m ** 2 + d_alt_m ** 2)

        if dist_3d_m <= self.acceptance_radius:
            # Sıradaki waypoint'e geç (Döngüsel)
            self.current_wp_idx = (self.current_wp_idx + 1) % len(self.waypoints)
            logger.debug(f"[MissionPlanner] Waypoint tamamlandı -> Yeni hedef: WP #{self.current_wp_idx + 1}")

        return self.waypoints[self.current_wp_idx]

    def get_current_waypoint(self) -> Optional[Waypoint]:
        if not self.waypoints:
            return None
        return self.waypoints[self.current_wp_idx]
