import math
from typing import List, Optional, Tuple, Dict
import numpy as np
from core.models import HedefKutusu


class TacticalTargetEvaluator:
    """Çoklu hedef ortamında en yüksek kilitlenme olasılığına sahip hedefi seçen taktik değerlendirici.
    
    Kriterler:
    - Kadraj merkezine yakınlık (w_merkez)
    - %5 boyut kuralına yakınlık / büyüklük (w_alan)
    - Model güven skoru (w_guven)
    - Takip kararlılığı / Track ID devamlılığı (w_devamlilik)
    """

    def __init__(
        self,
        w_merkez: float = 0.35,
        w_alan: float = 0.35,
        w_guven: float = 0.15,
        w_devamlilik: float = 0.15,
        hedef_alan_min: float = 0.05
    ):
        self.w_merkez = w_merkez
        self.w_alan = w_alan
        self.w_guven = w_guven
        self.w_devamlilik = w_devamlilik
        self.hedef_alan_min = hedef_alan_min
        self.last_selected_track_id: Optional[int] = None

    def evaluate_targets(
        self,
        targets: List[HedefKutusu],
        screen_w: int,
        screen_h: int
    ) -> List[Tuple[HedefKutusu, float]]:
        """Her hedef için 0-100 arası taktik öncelik skoru hesaplar ve sıralı liste döndürür."""
        if not targets:
            return []

        cx = screen_w / 2.0
        cy = screen_h / 2.0
        max_dist = math.hypot(cx, cy)
        total_screen_area = screen_w * screen_h

        scored_targets = []

        for t in targets:
            # 1. Merkez Skoru (0.0 - 1.0): Merkeze ne kadar yakınsa o kadar yüksek
            dist = math.hypot(t.merkez_x - cx, t.merkez_y - cy)
            score_merkez = max(0.0, 1.0 - (dist / max_dist))

            # 2. Alan Skoru (0.0 - 1.0): %5 kuralını aştıkça artar
            area_ratio = t.alan / max(1.0, total_screen_area)
            score_alan = min(1.0, area_ratio / self.hedef_alan_min)

            # 3. Güven Skoru (0.0 - 1.0)
            score_guven = max(0.0, min(1.0, t.conf))

            # 4. Devamlılık Skoru: Önceki adımda kilitlenilen hedefse bonus
            score_devamlilik = 1.0 if (self.last_selected_track_id is not None and t.track_id == self.last_selected_track_id) else 0.0

            # Ağırlıklı Toplam Skor (0 - 100)
            total_score = (
                (score_merkez * self.w_merkez) +
                (score_alan * self.w_alan) +
                (score_guven * self.w_guven) +
                (score_devamlilik * self.w_devamlilik)
            ) * 100.0

            scored_targets.append((t, total_score))

        # En yüksek skora göre sırala
        scored_targets.sort(key=lambda x: x[1], reverse=True)
        return scored_targets

    def select_best_target(
        self,
        targets: List[HedefKutusu],
        screen_w: int,
        screen_h: int
    ) -> Optional[HedefKutusu]:
        """Taktiksel olarak kilitlenmeye en uygun tekil hedefi seçer."""
        scored = self.evaluate_targets(targets, screen_w, screen_h)
        if scored:
            best_target = scored[0][0]
            self.last_selected_track_id = best_target.track_id
            return best_target
        self.last_selected_track_id = None
        return None
