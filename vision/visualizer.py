import cv2
import math
import numpy as np
from typing import List, Optional
from core.models import HedefKutusu, KilitDurumu, TelemetriPaketi


class HUDVisualizer:
    """Askeri standartlarda Head-Up Display (HUD) ve Kilitlenme Görselleştirici."""

    def __init__(self):
        # Renk Sabitleri (BGR formatında)
        self.COLOR_GREEN = (0, 255, 0)
        self.COLOR_CYAN = (255, 255, 0)
        self.COLOR_YELLOW = (0, 215, 255)
        self.COLOR_ORANGE = (0, 140, 255)
        self.COLOR_RED = (0, 0, 255)
        self.COLOR_WHITE = (255, 255, 255)
        self.COLOR_DARK_GREY = (40, 40, 40)

    def draw_hud(
        self,
        frame: np.ndarray,
        boxes: List[HedefKutusu],
        lock_status: KilitDurumu,
        lock_duration: float,
        target_box: Optional[HedefKutusu] = None,
        telemetry: Optional[TelemetriPaketi] = None,
        fps: float = 0.0,
        req_lock_time: float = 4.0,
        min_area_ratio: float = 0.05
    ) -> np.ndarray:
        """Video karesi üzerine tüm HUD ve kilitlenme katmanlarını çizer."""
        out = frame.copy()
        h, w = out.shape[:2]
        center_x, center_y = int(w / 2), int(h / 2)

        # 1. Merkez Nişangah ve Kilit Dairesi
        lock_radius = int(min(w, h) * 0.18)
        self._draw_reticle(out, center_x, center_y, lock_radius, lock_status)

        # 2. Yapay Ufuk Çizgisi (Telemetriden geliyorsa)
        if telemetry is not None:
            self._draw_artificial_horizon(out, center_x, center_y, telemetry.IHA_yatis, telemetry.IHA_dikilme)

        # 3. Tespit ve Takip Kutuları
        for box in boxes:
            is_active = (target_box is not None and box.track_id == target_box.track_id)
            self._draw_target_box(out, box, is_active, lock_status, w, h, min_area_ratio)

        # 4. Kilitlenme İlerleme Çubuğu ve Geri Sayım
        if lock_status in [KilitDurumu.LOCKING, KilitDurumu.LOCKED, KilitDurumu.LOST]:
            self._draw_lock_progress(out, center_x, center_y, lock_duration, req_lock_time, lock_status)

        # 5. Üst Bilgi Barı (Telemetri, Durum, FPS)
        self._draw_top_bar(out, telemetry, fps, lock_status, w)

        return out

    def _draw_reticle(self, img: np.ndarray, cx: int, cy: int, radius: int, status: KilitDurumu):
        """Ekran ortasındaki hedef arama / kilitlenme çemberi."""
        color = self.COLOR_CYAN
        if status == KilitDurumu.LOCKING:
            color = self.COLOR_YELLOW
        elif status == KilitDurumu.LOCKED:
            color = self.COLOR_GREEN

        # Kilit alanı dairesi (kesikli efekt)
        cv2.circle(img, (cx, cy), radius, color, 1, cv2.LINE_AA)
        
        # Merkez artı işareti
        size = 14
        cv2.line(img, (cx - size, cy), (cx + size, cy), color, 1, cv2.LINE_AA)
        cv2.line(img, (cx, cy - size), (cx, cy + size), color, 1, cv2.LINE_AA)
        
        # Çevre kılavuz çentikleri
        for angle in [0, 90, 180, 270]:
            rad = math.radians(angle)
            x1 = int(cx + (radius - 8) * math.cos(rad))
            y1 = int(cy + (radius - 8) * math.sin(rad))
            x2 = int(cx + (radius + 8) * math.cos(rad))
            y2 = int(cy + (radius + 8) * math.sin(rad))
            cv2.line(img, (x1, y1), (x2, y2), color, 2, cv2.LINE_AA)

    def _draw_artificial_horizon(self, img: np.ndarray, cx: int, cy: int, roll: float, pitch: float):
        """HUD yapay ufuk çizgisi ve meyil açısı."""
        rad = math.radians(-roll)
        pitch_offset = int(pitch * 3.0)  # Pitch piksel katsayısı
        
        length = 120
        dx = int(length * math.cos(rad))
        dy = int(length * math.sin(rad))
        
        center_py = cy + pitch_offset
        p1 = (cx - dx, center_py - dy)
        p2 = (cx + dx, center_py + dy)
        
        # Ufuk çizgisi
        cv2.line(img, p1, p2, (180, 180, 180), 1, cv2.LINE_AA)

    def _draw_target_box(
        self,
        img: np.ndarray,
        box: HedefKutusu,
        is_active: bool,
        status: KilitDurumu,
        img_w: int,
        img_h: int,
        min_area_ratio: float
    ):
        """Hedef İHA etrafındaki köşe parantezli çerçeve."""
        x1, y1, x2, y2 = int(box.x1), int(box.y1), int(box.x2), int(box.y2)
        
        if is_active:
            if status == KilitDurumu.LOCKED:
                color = self.COLOR_GREEN
            elif status == KilitDurumu.LOCKING:
                color = self.COLOR_YELLOW
            else:
                color = self.COLOR_ORANGE
        else:
            color = self.COLOR_CYAN

        # Köşe çizgileri (Bracket box)
        line_len = max(10, int(min(box.genislik, box.yukseklik) * 0.25))
        thick = 2 if is_active else 1

        # Sol üst
        cv2.line(img, (x1, y1), (x1 + line_len, y1), color, thick)
        cv2.line(img, (x1, y1), (x1, y1 + line_len), color, thick)
        # Sağ üst
        cv2.line(img, (x2, y1), (x2 - line_len, y1), color, thick)
        cv2.line(img, (x2, y1), (x2, y1 + line_len), color, thick)
        # Sol alt
        cv2.line(img, (x1, y2), (x1 + line_len, y2), color, thick)
        cv2.line(img, (x1, y2), (x1, y2 - line_len), color, thick)
        # Sağ alt
        cv2.line(img, (x2, y2), (x2 - line_len, y2), color, thick)
        cv2.line(img, (x2, y2), (x2, y2 - line_len), color, thick)

        # Bilgi Etiketi
        area_pct = box.alan_orani(img_w, img_h) * 100.0
        area_ok = "[OK]" if (area_pct / 100.0) >= min_area_ratio else "[<5%]"
        lbl = f"ID:{box.track_id or 0} {box.conf:.2f} | {area_pct:.1f}% {area_ok}"
        
        cv2.putText(img, lbl, (x1, max(18, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

    def _draw_lock_progress(
        self,
        img: np.ndarray,
        cx: int,
        cy: int,
        duration: float,
        req_time: float,
        status: KilitDurumu
    ):
        """Kilitlenme 4.0 sn ilerleme çubuğu ve durumu."""
        bar_w = 240
        bar_h = 16
        x1 = cx - (bar_w // 2)
        y1 = cy + int(img.shape[0] * 0.22)
        
        # Arka plan kutusu
        cv2.rectangle(img, (x1 - 2, y1 - 2), (x1 + bar_w + 2, y1 + bar_h + 2), (20, 20, 20), -1)
        cv2.rectangle(img, (x1 - 2, y1 - 2), (x1 + bar_w + 2, y1 + bar_h + 2), (100, 100, 100), 1)

        progress = min(1.0, max(0.0, duration / req_time))
        fill_w = int(bar_w * progress)

        bar_color = self.COLOR_YELLOW
        if status == KilitDurumu.LOCKED:
            bar_color = self.COLOR_GREEN
            status_text = f"*** LOCKED (4.0s) ***"
        elif status == KilitDurumu.LOST:
            bar_color = self.COLOR_ORANGE
            status_text = f"TARGET LOST (TOLERANCE: {duration:.1f}s)"
        else:
            status_text = f"LOCKING: {duration:.2f}s / {req_time:.1f}s"

        if fill_w > 0:
            cv2.rectangle(img, (x1, y1), (x1 + fill_w, y1 + bar_h), bar_color, -1)

        # Durum Metni
        cv2.putText(
            img,
            status_text,
            (x1, y1 - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            bar_color,
            2,
            cv2.LINE_AA
        )

    def _draw_top_bar(
        self,
        img: np.ndarray,
        telemetry: Optional[TelemetriPaketi],
        fps: float,
        status: KilitDurumu,
        width: int
    ):
        """Ekranın üst tarafındaki telemetri durumu başlığı."""
        # Yarı saydam başlık şeridi
        overlay = img.copy()
        cv2.rectangle(overlay, (0, 0), (width, 36), (15, 15, 15), -1)
        cv2.addWeighted(overlay, 0.75, img, 0.25, 0, img)

        if telemetry is not None:
            telemetry_str = (
                f"ALT: {telemetry.IHA_irtifa:.1f}m | "
                f"SPD: {telemetry.IHA_hiz:.1f}m/s | "
                f"HDG: {int(telemetry.IHA_yonelme)} deg | "
                f"BAT: %{telemetry.IHA_batarya} | "
                f"MOD: {'OTONOM' if telemetry.IHA_otonom else 'MANUEL'}"
            )
        else:
            telemetry_str = "TELEMETRI: BAGLI DEGIL (SIMULASYON)"

        status_str = f"STATUS: {status.value} | FPS: {fps:.1f}"

        cv2.putText(img, telemetry_str, (15, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.COLOR_GREEN, 1, cv2.LINE_AA)
        cv2.putText(img, status_str, (width - 320, 23), cv2.FONT_HERSHEY_SIMPLEX, 0.5, self.COLOR_CYAN, 1, cv2.LINE_AA)
