import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import numpy as np

from core.models import HedefKutusu


@dataclass
class OpticalTrackMemory:
    """Hedef başına korunan renk histogramı ve kısa vadeli optik hareket belleği."""
    track_id: int
    last_box: HedefKutusu
    last_seen_time: float
    velocity_px_s: Tuple[float, float] = (0.0, 0.0)
    hsv_histogram: Optional[np.ndarray] = None
    occlusion_frames: int = 0
    reid_match_score: float = 1.0


class OpticalFlowReIDTracker:
    """Bulut/Güneş Kararması (Occlusion) ve Kısa Kadraj Kayıpları İçin
    Lucas-Kanade Optik Akış + HSV Histogram Re-Identification Kurtarma Motoru.

    TEKNOFEST şartnamesindeki 0.35s kayıp toleransı (grace period) penceresinde:
      1. YOLO tespiti anlık olarak düştüğünde (`detections == []`), son bilinen hedef
         bölgesindeki köşe noktalarını (Shi-Tomasi / Lucas-Kanade Pyramidal Optical Flow)
         veya hız vektörünü kullanarak kutuyu max `max_coast_frames` boyunca sürükler.
      2. Hedef yeniden tespit edildiğinde HSV renk/parlaklık histogramı Bhattacharyya /
         Cosine benzerliği ve uzamsal yakınlık ile aynı `track_id`'yi korur; böylece
         4.0 saniyelik kilitlenme sayacının ID değişimi yüzünden sıfırlanmasını önler.
    """

    def __init__(
        self,
        max_coast_frames: int = 8,
        reid_similarity_threshold: float = 0.55,
        max_reid_distance_px: float = 220.0,
        hist_bins: Tuple[int, int] = (16, 16)
    ):
        self.max_coast_frames = max(1, int(max_coast_frames))
        self.reid_similarity_threshold = float(reid_similarity_threshold)
        self.max_reid_distance_px = float(max_reid_distance_px)
        self.hist_bins = hist_bins

        self.memories: Dict[int, OpticalTrackMemory] = {}
        self._prev_gray: Optional[np.ndarray] = None

    @staticmethod
    def _to_gray(frame: np.ndarray) -> np.ndarray:
        if frame.ndim == 2:
            return frame
        # BGR -> Grayscale
        return (0.114 * frame[:, :, 0] + 0.587 * frame[:, :, 1] + 0.299 * frame[:, :, 2]).astype(np.uint8)

    def compute_appearance_embedding(self, frame: np.ndarray, box: HedefKutusu) -> np.ndarray:
        """Hedef kutusu içindeki piksel dağılımından L2-normalize görünüm vektörü çıkarır."""
        h, w = frame.shape[:2]
        x1 = max(0, min(w - 1, int(box.x1)))
        y1 = max(0, min(h - 1, int(box.y1)))
        x2 = max(x1 + 1, min(w, int(box.x2)))
        y2 = max(y1 + 1, min(h, int(box.y2)))

        roi = frame[y1:y2, x1:x2]
        if roi.size == 0:
            return np.ones(32, dtype=np.float32) / math.sqrt(32.0)

        if roi.ndim == 2:
            hist, _ = np.histogram(roi, bins=32, range=(0, 256))
            vec = hist.astype(np.float32)
        else:
            # Kanal bazlı yoğunluk ve renk oranı histogramı (16 + 16 = 32 bin)
            b_chan = roi[:, :, 0].astype(np.float32)
            g_chan = roi[:, :, 1].astype(np.float32)
            r_chan = roi[:, :, 2].astype(np.float32)
            luma = 0.114 * b_chan + 0.587 * g_chan + 0.299 * r_chan
            chroma = (r_chan - b_chan) + 128.0

            h_luma, _ = np.histogram(luma, bins=self.hist_bins[0], range=(0, 256))
            h_chroma, _ = np.histogram(chroma, bins=self.hist_bins[1], range=(0, 256))
            vec = np.concatenate([h_luma, h_chroma]).astype(np.float32)

        norm = float(np.linalg.norm(vec))
        if norm > 1e-6:
            vec /= norm
        else:
            vec = np.ones_like(vec) / math.sqrt(len(vec))
        return vec

    @staticmethod
    def cosine_similarity(vec_a: Optional[np.ndarray], vec_b: Optional[np.ndarray]) -> float:
        if vec_a is None or vec_b is None or vec_a.shape != vec_b.shape:
            return 0.5
        sim = float(np.dot(vec_a, vec_b))
        return max(0.0, min(1.0, sim))

    def _estimate_patch_flow(
        self,
        prev_gray: np.ndarray,
        curr_gray: np.ndarray,
        box: HedefKutusu
    ) -> Tuple[float, float]:
        """Önceki ve şimdiki gri kare arasında hedef yaması üzerinde 2D gradyan optik akış kestirimi."""
        h, w = prev_gray.shape[:2]
        x1 = max(2, min(w - 3, int(box.x1)))
        y1 = max(2, min(h - 3, int(box.y1)))
        x2 = max(x1 + 2, min(w - 2, int(box.x2)))
        y2 = max(y1 + 2, min(h - 2, int(box.y2)))

        patch_prev = prev_gray[y1:y2, x1:x2].astype(np.float32)
        patch_curr = curr_gray[y1:y2, x1:x2].astype(np.float32)

        if patch_prev.shape[0] < 3 or patch_prev.shape[1] < 3:
            return (0.0, 0.0)

        # Lucas-Kanade En Küçük Kareler Optik Akış: [sum Ix^2, sum IxIy; sum IxIy, sum Iy^2] [u, v]^T = -[sum IxIt, sum IyIt]^T
        ix = 0.5 * (patch_prev[1:-1, 2:] - patch_prev[1:-1, :-2])
        iy = 0.5 * (patch_prev[2:, 1:-1] - patch_prev[:-2, 1:-1])
        it = patch_curr[1:-1, 1:-1] - patch_prev[1:-1, 1:-1]

        a11 = float(np.sum(ix * ix)) + 1e-3
        a12 = float(np.sum(ix * iy))
        a22 = float(np.sum(iy * iy)) + 1e-3
        b1 = -float(np.sum(ix * it))
        b2 = -float(np.sum(iy * it))

        det = a11 * a22 - a12 * a12
        if abs(det) < 1e-3:
            return (0.0, 0.0)

        u = (a22 * b1 - a12 * b2) / det
        v = (-a12 * b1 + a11 * b2) / det
        # Aşırı sıçramaları sınırla
        u = max(-35.0, min(35.0, u))
        v = max(-35.0, min(35.0, v))
        return (u, v)

    def update_and_recover(
        self,
        frame: np.ndarray,
        tracked_boxes: List[HedefKutusu],
        dt: float = 0.033,
        current_time: float = 0.0
    ) -> List[HedefKutusu]:
        """Mevcut takip kutularını Re-ID ile doğrular ve anlık kaybolan aktif hedefleri
        optik akışla (Optical Flow Coasting) kurtarır.
        """
        dt = max(1e-3, float(dt))
        curr_gray = self._to_gray(frame)
        h, w = frame.shape[:2]

        active_ids_in_frame = set()
        recovered_list: List[HedefKutusu] = []

        # 1. Gelen kutuların Re-ID kimlik eşleştirmesi ve hafıza güncellemesi
        for box in tracked_boxes:
            emb = self.compute_appearance_embedding(frame, box)
            tid = box.track_id

            # Eğer yeni bir ID atanmışsa ama kısa süre önce kaybolmuş bir hedefe çok benziyorsa ID'yi geri yükle
            if tid not in self.memories and self.memories:
                best_old_id = None
                best_score = -1.0
                for old_id, mem in self.memories.items():
                    if mem.occlusion_frames > 0 and mem.occlusion_frames <= self.max_coast_frames:
                        dist = math.hypot(box.merkez_x - mem.last_box.merkez_x, box.merkez_y - mem.last_box.merkez_y)
                        if dist <= self.max_reid_distance_px:
                            app_sim = self.cosine_similarity(emb, mem.hsv_histogram)
                            dist_sim = 1.0 - (dist / self.max_reid_distance_px)
                            combined = 0.65 * app_sim + 0.35 * dist_sim
                            if combined > best_score and combined >= self.reid_similarity_threshold:
                                best_score = combined
                                best_old_id = old_id

                if best_old_id is not None:
                    box.track_id = best_old_id
                    tid = best_old_id

            if tid is not None:
                active_ids_in_frame.add(tid)
                prev_mem = self.memories.get(tid)
                if prev_mem is not None:
                    vx = 0.6 * prev_mem.velocity_px_s[0] + 0.4 * ((box.merkez_x - prev_mem.last_box.merkez_x) / dt)
                    vy = 0.6 * prev_mem.velocity_px_s[1] + 0.4 * ((box.merkez_y - prev_mem.last_box.merkez_y) / dt)
                    sim_score = self.cosine_similarity(emb, prev_mem.hsv_histogram)
                    blended_hist = 0.75 * prev_mem.hsv_histogram + 0.25 * emb
                    blended_hist /= (float(np.linalg.norm(blended_hist)) + 1e-6)
                else:
                    vx, vy = (0.0, 0.0)
                    sim_score = 1.0
                    blended_hist = emb

                self.memories[tid] = OpticalTrackMemory(
                    track_id=tid,
                    last_box=HedefKutusu(
                        x1=box.x1, y1=box.y1, x2=box.x2, y2=box.y2,
                        conf=box.conf, track_id=tid, class_id=box.class_id, class_name=box.class_name
                    ),
                    last_seen_time=current_time,
                    velocity_px_s=(vx, vy),
                    hsv_histogram=blended_hist,
                    occlusion_frames=0,
                    reid_match_score=round(sim_score, 4)
                )

            recovered_list.append(box)

        # 2. Bu karede tespit edilemeyen (Occlusion / Blur) hedefleri optik akışla sürükle
        expired_ids = []
        for tid, mem in self.memories.items():
            if tid in active_ids_in_frame:
                continue

            mem.occlusion_frames += 1
            if mem.occlusion_frames > self.max_coast_frames:
                expired_ids.append(tid)
                continue

            # Lucas-Kanade optik akış + kinematik hız birleşimi
            flow_dx, flow_dy = (0.0, 0.0)
            if self._prev_gray is not None:
                flow_dx, flow_dy = self._estimate_patch_flow(self._prev_gray, curr_gray, mem.last_box)

            kin_dx = mem.velocity_px_s[0] * dt
            kin_dy = mem.velocity_px_s[1] * dt

            dx = 0.5 * flow_dx + 0.5 * kin_dx
            dy = 0.5 * flow_dy + 0.5 * kin_dy

            bw = mem.last_box.genislik
            bh = mem.last_box.yukseklik
            new_cx = max(bw / 2.0, min(w - bw / 2.0, mem.last_box.merkez_x + dx))
            new_cy = max(bh / 2.0, min(h - bh / 2.0, mem.last_box.merkez_y + dy))

            coasted_box = HedefKutusu(
                x1=new_cx - bw / 2.0,
                y1=new_cy - bh / 2.0,
                x2=new_cx + bw / 2.0,
                y2=new_cy + bh / 2.0,
                conf=max(0.30, round(mem.last_box.conf * (0.92 ** mem.occlusion_frames), 3)),
                track_id=tid,
                class_id=mem.last_box.class_id,
                class_name=mem.last_box.class_name
            )
            mem.last_box = coasted_box
            recovered_list.append(coasted_box)

        for eid in expired_ids:
            del self.memories[eid]

        self._prev_gray = curr_gray
        return recovered_list
