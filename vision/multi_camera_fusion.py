"""
Çift Kameralı / Geniş-Dar Açı Görsel Sensör Füzyonu (Multi-Camera Dual-Lens Fusion).
Geniş açı (Wide FOV ~90°) durumsal farkındalık kamerası ile dar açı / telefoto (Zoom FOV ~35°)
kilitlenme kamerasından gelen tespitleri uzaysal olarak birleştirir; uzak hedeflerde %5 alan kuralını
erken sağlamak için otomatik kamera geçişi (hand-off) ve koordinat dönüşümü yapar.
"""

import math
from enum import Enum
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any
from core.models import HedefKutusu
from core.logger import logger


class CameraRole(Enum):
    """Kamera Türü ve Görevi."""
    WIDE = "WIDE"           # Geniş açı (Geniş arama & yakın it dalaşı)
    ZOOM = "ZOOM"           # Dar açı / Telefoto (Uzak menzil & erken %5 kilitlenme)
    FUSED = "FUSED"         # İki kameranın ortak doğrulaması


@dataclass
class FusedTarget:
    """Çift kamera füzyonundan çıkan birleştirilmiş hedef çıktısı."""
    track_id: Optional[int]
    primary_box: HedefKutusu         # Kilitlenme motoruna beslenecek optimize kutu
    source_camera: CameraRole
    wide_box: Optional[HedefKutusu]
    zoom_box: Optional[HedefKutusu]
    confidence: float
    effective_area_ratio: float       # Ekran alanı oranı (Zoom avantajı uygulanmış)
    magnification_factor: float       # Dar açı büyütme çarpanı (örn. 2.6x)


class MultiCameraFusion:
    """
    Geniş ve Dar açılı çift kamera tespitlerini uzaysal olarak eşleştiren ve birleştiren füzyon motoru.
    """
    def __init__(
        self,
        wide_hfov_deg: float = 90.0,
        zoom_hfov_deg: float = 35.0,
        frame_width: int = 1280,
        frame_height: int = 720,
        iou_threshold: float = 0.25
    ):
        self.wide_hfov = wide_hfov_deg
        self.zoom_hfov = zoom_hfov_deg
        self.width = frame_width
        self.height = frame_height
        self.iou_thresh = iou_threshold

        # Büyütme oranı (Focal length ratio): s = tan(HFOV_wide/2) / tan(HFOV_zoom/2)
        half_w = math.radians(wide_hfov_deg / 2.0)
        half_z = math.radians(zoom_hfov_deg / 2.0)
        self.scale_factor = math.tan(half_w) / math.tan(half_z)
        self.cx = frame_width / 2.0
        self.cy = frame_height / 2.0

    def wide_to_zoom_coords(self, box: HedefKutusu) -> HedefKutusu:
        """Geniş açı kameradaki kutuyu Zoom kameranın piksel koordinatlarına dönüştürür."""
        # Merkezden bağıl piksel farkı
        dx = box.merkez_x - self.cx
        dy = box.merkez_y - self.cy

        # Zoom kamerada merkez ve boyutlar scale_factor ile büyür
        zoom_cx = self.cx + dx * self.scale_factor
        zoom_cy = self.cy + dy * self.scale_factor
        zoom_w = box.genislik * self.scale_factor
        zoom_h = box.yukseklik * self.scale_factor

        return HedefKutusu(
            x1=round(zoom_cx - zoom_w / 2.0, 1),
            y1=round(zoom_cy - zoom_h / 2.0, 1),
            x2=round(zoom_cx + zoom_w / 2.0, 1),
            y2=round(zoom_cy + zoom_h / 2.0, 1),
            conf=box.conf,
            track_id=box.track_id,
            class_id=box.class_id,
            class_name=box.class_name
        )

    def zoom_to_wide_coords(self, box: HedefKutusu) -> HedefKutusu:
        """Zoom kameradaki kutuyu Geniş kamera koordinatlarına dönüştürür."""
        dx = box.merkez_x - self.cx
        dy = box.merkez_y - self.cy

        wide_cx = self.cx + dx / self.scale_factor
        wide_cy = self.cy + dy / self.scale_factor
        wide_w = box.genislik / self.scale_factor
        wide_h = box.yukseklik / self.scale_factor

        return HedefKutusu(
            x1=round(wide_cx - wide_w / 2.0, 1),
            y1=round(wide_cy - wide_h / 2.0, 1),
            x2=round(wide_cx + wide_w / 2.0, 1),
            y2=round(wide_cy + wide_h / 2.0, 1),
            conf=box.conf,
            track_id=box.track_id,
            class_id=box.class_id,
            class_name=box.class_name
        )

    def fuse(
        self,
        wide_detections: List[HedefKutusu],
        zoom_detections: List[HedefKutusu]
    ) -> List[FusedTarget]:
        """
        Her iki kameradan gelen tespitleri eşleştirir, en iyi hedef temsilini üretir.
        """
        fused_targets: List[FusedTarget] = []
        matched_zoom_indices = set()

        # 1. Geniş açı tespitlerini Zoom koordinatlarına izdüşürüp eşleştir
        for wide_box in wide_detections:
            projected_zoom = self.wide_to_zoom_coords(wide_box)
            best_match_idx = None
            best_iou = 0.0

            for z_idx, zoom_box in enumerate(zoom_detections):
                if z_idx in matched_zoom_indices:
                    continue
                iou = self._calculate_iou(projected_zoom, zoom_box)
                if iou > best_iou and iou >= self.iou_thresh:
                    best_iou = iou
                    best_match_idx = z_idx

            if best_match_idx is not None:
                # İki kamerada da tespit edildi! (FUSED)
                matched_zoom_indices.add(best_match_idx)
                zoom_box = zoom_detections[best_match_idx]
                
                # Zoom kameranın sağladığı büyütülmüş kutu kilitlenme için önceliklidir
                fused_conf = min(0.99, max(wide_box.conf, zoom_box.conf) + 0.05)
                area_ratio = zoom_box.alan_orani(self.width, self.height)

                fused_targets.append(FusedTarget(
                    track_id=zoom_box.track_id or wide_box.track_id,
                    primary_box=zoom_box,
                    source_camera=CameraRole.FUSED,
                    wide_box=wide_box,
                    zoom_box=zoom_box,
                    confidence=round(fused_conf, 2),
                    effective_area_ratio=round(area_ratio, 4),
                    magnification_factor=round(self.scale_factor, 2)
                ))
            else:
                # Yalnızca Geniş kamerada var (Hedef henüz Zoom kadrajına girmemiş veya kenarda)
                area_ratio = wide_box.alan_orani(self.width, self.height)
                fused_targets.append(FusedTarget(
                    track_id=wide_box.track_id,
                    primary_box=wide_box,
                    source_camera=CameraRole.WIDE,
                    wide_box=wide_box,
                    zoom_box=None,
                    confidence=wide_box.conf,
                    effective_area_ratio=round(area_ratio, 4),
                    magnification_factor=1.0
                ))

        # 2. Yalnızca Zoom kamerasında yakalanan hedefler (Uzak hedefler)
        for z_idx, zoom_box in enumerate(zoom_detections):
            if z_idx not in matched_zoom_indices:
                area_ratio = zoom_box.alan_orani(self.width, self.height)
                fused_targets.append(FusedTarget(
                    track_id=zoom_box.track_id,
                    primary_box=zoom_box,
                    source_camera=CameraRole.ZOOM,
                    wide_box=None,
                    zoom_box=zoom_box,
                    confidence=zoom_box.conf,
                    effective_area_ratio=round(area_ratio, 4),
                    magnification_factor=round(self.scale_factor, 2)
                ))

        # Alan oranı ve güvene göre sırala (Kilitlenmeye en yakın hedef önde)
        fused_targets.sort(key=lambda t: (t.effective_area_ratio, t.confidence), reverse=True)
        return fused_targets

    @staticmethod
    def _calculate_iou(boxA: HedefKutusu, boxB: HedefKutusu) -> float:
        """İki sınırlayıcı kutu arasındaki Kesişim / Birleşim (IoU) oranını hesaplar."""
        xA = max(boxA.x1, boxB.x1)
        yA = max(boxA.y1, boxB.y1)
        xB = min(boxA.x2, boxB.x2)
        yB = min(boxA.y2, boxB.y2)

        inter_w = max(0.0, xB - xA)
        inter_h = max(0.0, yB - yA)
        inter_area = inter_w * inter_h

        boxA_area = boxA.alan
        boxB_area = boxB.alan
        union_area = boxA_area + boxB_area - inter_area

        if union_area <= 0.0:
            return 0.0
        return inter_area / union_area
