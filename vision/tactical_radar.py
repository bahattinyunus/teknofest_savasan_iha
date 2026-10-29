import cv2
import math
import numpy as np
from typing import List, Optional
from core.models import TelemetriPaketi, RakipIHABilgisi, HSSBolgesi, KilitDurumu


class TacticalRadarMinimap:
    """Askeri standartlarda 2D Taktik Hava Durumu Göstergesi (Air Situation Display - ASD / Radar).
    
    Özellikler:
    - Kendi İHA'mız merkezde, yönelim vektörüyle birlikte.
    - Rakip İHA'lar radar çemberleri üzerinde göreceli konum ve rotalarıyla.
    - Kilitlenme durumu (Sarı/Yeşil renk kodlaması).
    - HSS (Hava Savunma Sistemi) tehdit daireleri.
    - Geofence sınır çizgileri.
    """

    def __init__(self, size: int = 240, max_range_m: float = 200.0):
        self.size = size
        self.max_range_m = max_range_m
        self.center = (size // 2, size // 2)
        self.pixels_per_meter = (size / 2.0) / max_range_m

        # Renkler (BGR)
        self.COLOR_BG = (15, 20, 25)
        self.COLOR_GRID = (40, 50, 60)
        self.COLOR_OWN = (0, 255, 128)      # Yeşil / Cyan kendi İHA
        self.COLOR_RIVAL = (0, 80, 255)     # Kırmızı/Turuncu rakip İHA
        self.COLOR_LOCKED = (0, 255, 0)     # Parlak yeşil kilitlenilen
        self.COLOR_HSS = (0, 0, 180)        # Kırmızı tehdit dairesi
        self.COLOR_TEXT = (180, 190, 200)

    def render_radar(
        self,
        own_tel: TelemetriPaketi,
        rivals: List[RakipIHABilgisi],
        hss_list: Optional[List[HSSBolgesi]] = None,
        lock_status: KilitDurumu = KilitDurumu.IDLE
    ) -> np.ndarray:
        """Taktik radar görselini üretir."""
        img = np.full((self.size, self.size, 3), self.COLOR_BG, dtype=np.uint8)
        cx, cy = self.center

        # 1. Menzil Çemberleri (50m, 100m, 150m)
        for r_m in [50, 100, 150]:
            px = int(r_m * self.pixels_per_meter)
            cv2.circle(img, (cx, cy), px, self.COLOR_GRID, 1, cv2.LINE_AA)
            cv2.putText(img, f"{r_m}m", (cx + px - 18, cy - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.3, self.COLOR_GRID, 1)

        # Merkez artı
        cv2.line(img, (cx - 8, cy), (cx + 8, cy), self.COLOR_GRID, 1)
        cv2.line(img, (cx, cy - 8), (cx, cy + 8), self.COLOR_GRID, 1)

        # 2. HSS (Hava Savunma Sistemi) Tehdit Bölgeleri
        if hss_list:
            lat_m = 111139.0
            lon_m = 111139.0 * math.cos(math.radians(own_tel.IHA_enlem))
            for hss in hss_list:
                dx = (hss.merkez_boylam - own_tel.IHA_boylam) * lon_m
                dy = (hss.merkez_enlem - own_tel.IHA_enlem) * lat_m
                
                hss_px = int(cx + dx * self.pixels_per_meter)
                hss_py = int(cy - dy * self.pixels_per_meter)
                hss_r = max(4, int(hss.yaricap_m * self.pixels_per_meter))

                if 0 <= hss_px < self.size and 0 <= hss_py < self.size:
                    cv2.circle(img, (hss_px, hss_py), hss_r, self.COLOR_HSS, 1, cv2.LINE_AA)
                    cv2.putText(img, f"HSS#{hss.hss_id}", (hss_px - 14, hss_py - hss_r - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.3, self.COLOR_HSS, 1)

        # 3. Rakip İHA'lar
        lat_m = 111139.0
        lon_m = 111139.0 * math.cos(math.radians(own_tel.IHA_enlem))

        for r in rivals:
            dx = (r.IHA_boylam - own_tel.IHA_boylam) * lon_m
            dy = (r.IHA_enlem - own_tel.IHA_enlem) * lat_m
            
            px = int(cx + dx * self.pixels_per_meter)
            py = int(cy - dy * self.pixels_per_meter)

            # Radar sınırları içindeyse çiz
            if 0 <= px < self.size and 0 <= py < self.size:
                r_color = self.COLOR_LOCKED if lock_status == KilitDurumu.LOCKED else self.COLOR_RIVAL
                cv2.circle(img, (px, py), 4, r_color, -1, cv2.LINE_AA)

                # Rakip yönelim oku
                hdg_rad = math.radians(r.IHA_yonelme)
                arrow_len = 10
                ax = int(px + arrow_len * math.sin(hdg_rad))
                ay = int(py - arrow_len * math.cos(hdg_rad))
                cv2.line(img, (px, py), (ax, ay), r_color, 1, cv2.LINE_AA)

                # Bilgi etiketi (Takım No ve İrtifa Farkı)
                d_alt = int(r.IHA_irtifa - own_tel.IHA_irtifa)
                lbl = f"T{r.takim_numarasi} ({'+' if d_alt >= 0 else ''}{d_alt}m)"
                cv2.putText(img, lbl, (px + 6, py + 3), cv2.FONT_HERSHEY_SIMPLEX, 0.35, r_color, 1)

        # 4. Kendi İHA'mız (Merkezde)
        cv2.circle(img, (cx, cy), 4, self.COLOR_OWN, -1, cv2.LINE_AA)
        own_rad = math.radians(own_tel.IHA_yonelme)
        v_len = 14
        vx = int(cx + v_len * math.sin(own_rad))
        vy = int(cy - v_len * math.cos(own_rad))
        cv2.line(img, (cx, cy), (vx, vy), self.COLOR_OWN, 2, cv2.LINE_AA)

        # Çerçeve ve Başlık
        cv2.rectangle(img, (0, 0), (self.size - 1, self.size - 1), (50, 60, 70), 1)
        cv2.putText(img, "TACTICAL RADAR (ASD)", (8, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.35, self.COLOR_TEXT, 1)

        return img

    def overlay_on_hud(self, hud_frame: np.ndarray, radar_img: np.ndarray, x_offset: int = 20, y_offset: int = 50) -> np.ndarray:
        """Radar görüntüsünü HUD video karesinin sağ/sol köşesine bindirir."""
        h, w = hud_frame.shape[:2]
        rh, rw = radar_img.shape[:2]

        x2 = min(w, x_offset + rw)
        y2 = min(h, y_offset + rh)
        crop_rw = x2 - x_offset
        crop_rh = y2 - y_offset

        if crop_rw > 0 and crop_rh > 0:
            # Yarı saydam bindirme
            roi = hud_frame[y_offset:y2, x_offset:x2]
            radar_crop = radar_img[:crop_rh, :crop_rw]
            cv2.addWeighted(roi, 0.25, radar_crop, 0.75, 0, roi)

        return hud_frame
