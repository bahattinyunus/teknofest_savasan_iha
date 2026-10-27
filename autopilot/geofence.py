import math
from typing import List, Tuple, Dict, Any, Optional
from core.models import HSSBolgesi
from core.logger import logger
from core.event_bus import bus, EVENT_GEOFENCE_ALERT


class GeofenceMonitor:
    """Yarışma uçuş alanı (Geofence), Hava Savunma Sistemleri (HSS) ve irtifa sınır kontrolcüsü.
    
    Yarışma sahası dışına çıkmayı ve diskalifiye olmayı önler.
    Sanal sınıra yaklaşıldığında ikaz verir, sınır aşıldığında RTL tetikler.
    HSS tehdit hacimlerini (uçuşa yasak silindirik bölgeler) denetler.
    """

    def __init__(
        self,
        polygon_coords: List[List[float]],
        min_alt_m: float = 30.0,
        max_alt_m: float = 150.0,
        warning_dist_m: float = 25.0
    ):
        self.polygon = polygon_coords  # [[lat, lon], [lat, lon], ...]
        self.min_alt_m = min_alt_m
        self.max_alt_m = max_alt_m
        self.warning_dist_m = warning_dist_m
        self.hss_bolgeleri: List[HSSBolgesi] = []

    def set_hss_bolgeleri(self, hss_list: List[HSSBolgesi]):
        """Hakem sunucusundan alınan HSS tehdit bölgelerini atar."""
        self.hss_bolgeleri = hss_list
        logger.info(f"{len(hss_list)} adet HSS (Hava Savunma Sistemi) tehdit hacmi tanımlandı.")

    def is_inside_polygon(self, lat: float, lon: float) -> bool:
        """Ray-casting algoritması ile noktanın poligon içinde olup olmadığını belirler."""
        if len(self.polygon) < 3:
            return True  # Poligon tanımlı değilse sınır yok say

        inside = False
        n = len(self.polygon)
        p1_lat, p1_lon = self.polygon[0]

        for i in range(1, n + 1):
            p2_lat, p2_lon = self.polygon[i % n]
            if min(p1_lon, p2_lon) < lon <= max(p1_lon, p2_lon):
                # Yatay ışın kesişim testi
                if lat <= max(p1_lat, p2_lat):
                    if p1_lon != p2_lon:
                        lat_inters = (lon - p1_lon) * (p2_lat - p1_lat) / (p2_lon - p1_lon) + p1_lat
                    if p1_lat == p2_lat or lat <= lat_inters:
                        inside = not inside
            p1_lat, p1_lon = p2_lat, p2_lon

        return inside

    def check_distance_to_boundary(self, lat: float, lon: float) -> float:
        """Noktanın en yakın poligon kenarına olan yaklaşık metre mesafesini hesaplar."""
        if len(self.polygon) < 3:
            return 999.0

        min_dist = float('inf')
        lat_m = 111139.0
        lon_m = 111139.0 * math.cos(math.radians(lat))

        n = len(self.polygon)
        for i in range(n):
            p1 = self.polygon[i]
            p2 = self.polygon[(i + 1) % n]
            
            dx = (p2[1] - p1[1]) * lon_m
            dy = (p2[0] - p1[0]) * lat_m
            px = (lon - p1[1]) * lon_m
            py = (lat - p1[0]) * lat_m

            seg_len_sq = dx*dx + dy*dy
            if seg_len_sq == 0:
                dist = math.hypot(px, py)
            else:
                t = max(0.0, min(1.0, (px * dx + py * dy) / seg_len_sq))
                proj_x = t * dx
                proj_y = t * dy
                dist = math.hypot(px - proj_x, py - proj_y)

            if dist < min_dist:
                min_dist = dist

        return min_dist

    def check_hss_violation(self, lat: float, lon: float, alt: float) -> Tuple[bool, Optional[HSSBolgesi]]:
        """HSS tehdit hacminin (silindirik kubbe) ihlal edilip edilmediğini denetler."""
        lat_m = 111139.0
        lon_m = 111139.0 * math.cos(math.radians(lat))

        for hss in self.hss_bolgeleri:
            # İrtifa aralığında mı?
            if hss.alt_irtifa_m <= alt <= hss.ust_irtifa_m:
                # Yatay mesafe
                dx = (lon - hss.merkez_boylam) * lon_m
                dy = (lat - hss.merkez_enlem) * lat_m
                dist = math.hypot(dx, dy)
                if dist <= hss.yaricap_m:
                    return True, hss

        return False, None

    def validate_position(self, lat: float, lon: float, alt: float) -> Tuple[bool, str]:
        """Konumun güvenli bölgede olup olmadığını denetler."""
        # 1. İrtifa Kontrolü
        if alt < self.min_alt_m:
            msg = f"DÜŞÜK İRTİFA İHLALİ! İrtifa: {alt:.1f}m < Min: {self.min_alt_m}m"
            bus.emit(EVENT_GEOFENCE_ALERT, mesaj=msg, ihlal=True)
            return False, msg
        if alt > self.max_alt_m:
            msg = f"YÜKSEK İRTİFA İHLALİ! İrtifa: {alt:.1f}m > Maks: {self.max_alt_m}m"
            bus.emit(EVENT_GEOFENCE_ALERT, mesaj=msg, ihlal=True)
            return False, msg

        # 2. HSS (Hava Savunma Sistemi) İhlali Kontrolü
        hss_violated, hss_threat = self.check_hss_violation(lat, lon, alt)
        if hss_violated and hss_threat is not None:
            msg = f"HSS İHLALİ! Yasaklı HSS Bölgesi #{hss_threat.hss_id} içine girildi!"
            bus.emit(EVENT_GEOFENCE_ALERT, mesaj=msg, ihlal=True)
            return False, msg

        # 3. Alan Poligonu Kontrolü
        inside = self.is_inside_polygon(lat, lon)
        dist = self.check_distance_to_boundary(lat, lon)

        if not inside:
            msg = f"GEOFENCE İHLALİ! Uçak yarışma sahası dışına çıktı!"
            bus.emit(EVENT_GEOFENCE_ALERT, mesaj=msg, ihlal=True)
            return False, msg

        if dist < self.warning_dist_m:
            msg = f"GEOFENCE YAKLAŞMA UYARISI: Sınıra {dist:.1f}m kaldı!"
            bus.emit(EVENT_GEOFENCE_ALERT, mesaj=msg, ihlal=False)
            return True, msg

        return True, "GÜVENLİ BÖLGE"
