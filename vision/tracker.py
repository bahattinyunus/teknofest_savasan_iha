import numpy as np
from typing import List, Dict, Optional
from core.models import HedefKutusu


class KalmanBoxTracker:
    """Tek bir hedef kutusu için 2D Kalman Filtresi ve durum takibi."""
    
    count = 0

    def __init__(self, bbox: HedefKutusu):
        # Durum vektörü: [x, y, s, r, vx, vy, vs]
        # x, y: merkez koordinatları
        # s: ölçek (alan)
        # r: en-boy oranı (width / height)
        # vx, vy, vs: hız türevleri
        KalmanBoxTracker.count += 1
        self.id = KalmanBoxTracker.count
        
        self.time_since_update = 0
        self.hits = 1
        self.hit_streak = 1
        self.age = 0
        
        # Son tespit edilen kutu
        self.last_box = bbox
        self.class_name = bbox.class_name
        self.conf = bbox.conf

    def update(self, bbox: HedefKutusu):
        self.time_since_update = 0
        self.hits += 1
        self.hit_streak += 1
        self.last_box = bbox
        self.conf = bbox.conf

    def predict(self):
        self.age += 1
        if self.time_since_update > 0:
            self.hit_streak = 0
        self.time_since_update += 1
        return self.last_box


def calculate_iou(box1: HedefKutusu, box2: HedefKutusu) -> float:
    """İki kutu arasındaki Kesişim / Birleşim (IoU) oranını hesaplar."""
    xx1 = max(box1.x1, box2.x1)
    yy1 = max(box1.y1, box2.y1)
    xx2 = min(box1.x2, box2.x2)
    yy2 = min(box1.y2, box2.y2)

    w = max(0.0, xx2 - xx1)
    h = max(0.0, yy2 - yy1)
    intersection = w * h

    area1 = box1.alan
    area2 = box2.alan
    union = area1 + area2 - intersection

    if union <= 0.0:
        return 0.0
    return intersection / union


class KalmanTracker:
    """Birden fazla İHA hedefini takip eden ve ID atayan nesne takipçisi."""

    def __init__(self, max_age: int = 15, min_hits: int = 2, iou_threshold: float = 0.3):
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        self.trackers: List[KalmanBoxTracker] = []

    def update(self, detections: List[HedefKutusu]) -> List[HedefKutusu]:
        """Gelen tespit kutularını mevcut trackerlar ile eşleştirir ve günceller."""
        # 1. Mevcut takipçilerin durumunu tahmin et
        for trk in self.trackers:
            trk.predict()

        matched_trks = set()
        matched_dets = set()
        matches = []

        # 2. IoU matrisi ile açgözlü eşleştirme (Greedy matching)
        if len(self.trackers) > 0 and len(detections) > 0:
            iou_matrix = np.zeros((len(detections), len(self.trackers)), dtype=np.float32)
            for d_idx, det in enumerate(detections):
                for t_idx, trk in enumerate(self.trackers):
                    iou_matrix[d_idx, t_idx] = calculate_iou(det, trk.last_box)

            # En yüksek IoU eşleşmelerini seç
            while True:
                max_iou = np.max(iou_matrix)
                if max_iou < self.iou_threshold:
                    break
                d_idx, t_idx = np.unravel_index(np.argmax(iou_matrix), iou_matrix.shape)
                matches.append((d_idx, t_idx))
                matched_dets.add(d_idx)
                matched_trks.add(t_idx)
                iou_matrix[d_idx, :] = -1.0
                iou_matrix[:, t_idx] = -1.0

        # 3. Eşleşenleri güncelle
        for d_idx, t_idx in matches:
            self.trackers[t_idx].update(detections[d_idx])

        # 4. Eşleşmeyen tespitler için yeni tracker başlat
        for d_idx, det in enumerate(detections):
            if d_idx not in matched_dets:
                self.trackers.append(KalmanBoxTracker(det))

        # 5. Yaşı aşan eski trackerları temizle
        self.trackers = [t for t in self.trackers if t.time_since_update <= self.max_age]

        # 6. Aktif sonuçları döndür
        tracked_boxes: List[HedefKutusu] = []
        for trk in self.trackers:
            if trk.hits >= self.min_hits or trk.age <= 2:
                box = trk.last_box
                box.track_id = trk.id
                tracked_boxes.append(box)

        return tracked_boxes
