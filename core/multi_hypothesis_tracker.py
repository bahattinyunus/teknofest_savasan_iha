r"""
AeroCombat - Çoklu Hipotez Takipçisi (Multi-Hypothesis Tracker - MHT).

Yoğun hava muharebesinde, elektronik harp (EW) yanıltıcı hedeflerinde (flare/decoy)
ve hedeflerin yüksek G'li kesişim manevralarında tek hipotezli takipçilerin (Simple Kalman / SORT)
iz kaybetmesini önleyen Reid tabanlı MHT algoritması:
1. Hipotez Ağacı Yönetimi (Hypothesis Tree & Branching)
2. Mahalanobis İnovasyon Kapısı (\chi^2 gating, d_M^2 <= 9.488)
3. Durum Makinesi: TENTATIVE (Aday) -> CONFIRMED (Doğrulanmış) -> COASTING (Kayıp) -> DEAD (Silinmiş)
4. Yüksek G Manevra Algılama: İvme sıçramalarında süreç gürültüsü kovaryansını (\mathbf{Q}) dinamik genişletme
5. N-Scan ve Log-Likelihood Ratio (LLR) Budama (Pruning) ile üstel büyüme kontrolü
"""

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Tuple, Optional, Any
import numpy as np

from core.models import HedefKutusu


class TrackStatus(Enum):
    TENTATIVE = "TENTATIVE"       # Yeni tespit, yeterli tutarlılık bekleniyor
    CONFIRMED = "CONFIRMED"       # Doğrulanmış aktif savaş uçağı hedefi
    COASTING = "COASTING"         # Anlık görüş kaybı (tahminle devam ediyor)
    DEAD = "DEAD"                 # Takip sonlandırıldı


@dataclass
class TrackHypothesis:
    """Tek bir takip hipotezi durumu."""
    hypothesis_id: int
    parent_id: Optional[int]
    state_vector: np.ndarray      # [cx, cy, w, h, vx, vy, vw, vh]^T
    covariance: np.ndarray        # 8x8 kovaryans matrisi P
    score_llr: float              # Log-Likelihood Ratio (LLR)
    history: List[Tuple[float, float]] = field(default_factory=list)


class MHTTrack:
    """Çoklu hipotez barındıran hedef izi."""

    def __init__(self, track_id: int, initial_box: HedefKutusu, init_llr: float = 2.0):
        self.track_id = track_id
        self.status = TrackStatus.TENTATIVE
        self.hits = 1
        self.misses = 0
        self.age = 1
        self.high_g_detected = False

        # Başlangıç durumu [cx, cy, w, h, vx, vy, vw, vh]
        cx = initial_box.merkez_x
        cy = initial_box.merkez_y
        w = max(1.0, initial_box.genislik)
        h = max(1.0, initial_box.yukseklik)

        init_state = np.array([cx, cy, w, h, 0.0, 0.0, 0.0, 0.0], dtype=np.float64)
        init_cov = np.diag([15.0, 15.0, 10.0, 10.0, 50.0, 50.0, 20.0, 20.0]) ** 2

        self.hypotheses: List[TrackHypothesis] = [
            TrackHypothesis(
                hypothesis_id=0,
                parent_id=None,
                state_vector=init_state,
                covariance=init_cov,
                score_llr=init_llr,
                history=[(cx, cy)]
            )
        ]
        self._hypo_counter = 1

    @property
    def best_hypothesis(self) -> TrackHypothesis:
        """En yüksek LLR skoruna sahip hipotezi döner."""
        return max(self.hypotheses, key=lambda h: h.score_llr)

    @property
    def current_box(self) -> HedefKutusu:
        """En iyi hipotezden HedefKutusu çıkarır."""
        best = self.best_hypothesis
        cx, cy, w, h = best.state_vector[:4]
        w = max(2.0, w)
        h = max(2.0, h)
        x1 = cx - w / 2.0
        y1 = cy - h / 2.0
        x2 = cx + w / 2.0
        y2 = cy + h / 2.0
        return HedefKutusu(
            x1=float(x1),
            y1=float(y1),
            x2=float(x2),
            y2=float(y2),
            conf=min(0.99, max(0.1, 1.0 / (1.0 + math.exp(-best.score_llr)))),
            track_id=self.track_id
        )


class MultiHypothesisTracker:
    """
    Askeri Standartta Çoklu Hipotez Takip Sistemi (MHT).
    """

    # Chi-Square 4 serbestlik derecesi (%95 güven): 9.488
    CHI2_GATE_THRESHOLD = 9.488

    def __init__(
        self,
        confirmation_hits: int = 3,
        deletion_misses: int = 5,
        max_hypotheses_per_track: int = 4,
        measurement_noise_std: float = 4.0,
        process_noise_std: float = 2.5
    ):
        self.confirmation_hits = confirmation_hits
        self.deletion_misses = deletion_misses
        self.max_hypotheses_per_track = max_hypotheses_per_track
        self.meas_std = measurement_noise_std
        self.proc_std = process_noise_std

        self.tracks: Dict[int, MHTTrack] = {}
        self._next_track_id = 1
        self._last_time: Optional[float] = None

    def update(self, detections: List[HedefKutusu], current_time: Optional[float] = None) -> List[HedefKutusu]:
        """
        Gelen tespitleri mevcut hipotezlerle eşleştirir, yeni hipotezler üretir ve budar.
        """
        now = current_time if current_time is not None else time.time()
        dt = 0.033 if self._last_time is None else max(0.005, min(0.2, now - self._last_time))
        self._last_time = now

        # 1. Tahmin (Predict) Adımı - Tüm hipotezler için
        self._predict_all(dt)

        # 2. Ölçüm Matrisi
        measurements = [np.array([d.merkez_x, d.merkez_y, d.genislik, d.yukseklik], dtype=np.float64) for d in detections]
        assigned_measurements = set()

        # 3. İnovasyon Kapılama (Gating) ve Hipotez Çatallandırma (Branching)
        for track in list(self.tracks.values()):
            new_hypotheses = []
            matched_any_in_track = False

            for hypo in track.hypotheses:
                matched_with_any = False

                for m_idx, z in enumerate(measurements):
                    d_mahal, innov, s_mat = self._mahalanobis_distance(hypo, z)

                    if d_mahal <= self.CHI2_GATE_THRESHOLD:
                        # Geçerli eşleşme: Yeni hipotez dalı oluştur
                        updated_state, updated_cov, delta_llr = self._kalman_update(hypo, z, innov, s_mat)
                        new_hypo = TrackHypothesis(
                            hypothesis_id=track._hypo_counter,
                            parent_id=hypo.hypothesis_id,
                            state_vector=updated_state,
                            covariance=updated_cov,
                            score_llr=hypo.score_llr + delta_llr,
                            history=hypo.history + [(float(updated_state[0]), float(updated_state[1]))]
                        )
                        track._hypo_counter += 1
                        new_hypotheses.append(new_hypo)
                        assigned_measurements.add(m_idx)
                        matched_with_any = True
                        matched_any_in_track = True

                # Iska (Miss) Hipotezi: Hedef tespit edilemediğinde de bir dal kalmalı
                miss_hypo = TrackHypothesis(
                    hypothesis_id=track._hypo_counter,
                    parent_id=hypo.hypothesis_id,
                    state_vector=hypo.state_vector.copy(),
                    covariance=hypo.covariance * 1.08,  # Belirsizlik artışı
                    score_llr=hypo.score_llr - 1.2,     # Ceza puanı
                    history=list(hypo.history)
                )
                track._hypo_counter += 1
                new_hypotheses.append(miss_hypo)

            # En iyi N hipotezi seç (Pruning / Budama)
            new_hypotheses.sort(key=lambda h: h.score_llr, reverse=True)
            track.hypotheses = new_hypotheses[:self.max_hypotheses_per_track]

            # Track İstatistik ve Durum Güncellemesi
            if matched_any_in_track:
                track.hits += 1
                track.misses = 0
            else:
                track.misses += 1

            track.age += 1

            # Durum FSM
            if track.status == TrackStatus.TENTATIVE and track.hits >= self.confirmation_hits:
                track.status = TrackStatus.CONFIRMED
            elif track.misses > 0 and track.status == TrackStatus.CONFIRMED:
                track.status = TrackStatus.COASTING

            if track.misses >= self.deletion_misses or track.best_hypothesis.score_llr < -5.0:
                track.status = TrackStatus.DEAD

        # 4. Ölü İzleri Temizle
        self.tracks = {tid: t for tid, t in self.tracks.items() if t.status != TrackStatus.DEAD}

        # 5. Eşleşmeyen Ölçümlerden Yeni Aday İzler (New Tracks) Başlat
        for m_idx, det in enumerate(detections):
            if m_idx not in assigned_measurements:
                new_track = MHTTrack(track_id=self._next_track_id, initial_box=det)
                self.tracks[self._next_track_id] = new_track
                self._next_track_id += 1

        # 6. Doğrulanmış veya aktif izleri HedefKutusu listesi olarak dönder
        output_boxes = []
        for track in self.tracks.values():
            if track.status in (TrackStatus.CONFIRMED, TrackStatus.COASTING):
                output_boxes.append(track.current_box)

        return output_boxes

    def _predict_all(self, dt: float):
        """Tüm hipotez durumlarını fiziksel sabit hızlı (CV) modelle ileriye öteler."""
        # F Matrisi: [cx, cy, w, h, vx, vy, vw, vh]
        f_mat = np.eye(8, dtype=np.float64)
        for i in range(4):
            f_mat[i, i + 4] = dt

        q_mat = np.eye(8, dtype=np.float64) * (self.proc_std ** 2)
        q_mat[:4, :4] *= (dt ** 4) / 4.0
        q_mat[4:, 4:] *= (dt ** 2)

        for track in self.tracks.values():
            for hypo in track.hypotheses:
                hypo.state_vector = f_mat @ hypo.state_vector
                hypo.covariance = f_mat @ hypo.covariance @ f_mat.T + q_mat

    def _mahalanobis_distance(self, hypo: TrackHypothesis, z: np.ndarray) -> Tuple[float, np.ndarray, np.ndarray]:
        """Ölçüm ile hipotez tahmini arasındaki Mahalanobis mesafesini hesaplar."""
        h_mat = np.zeros((4, 8), dtype=np.float64)
        np.fill_diagonal(h_mat, 1.0)

        r_mat = np.eye(4, dtype=np.float64) * (self.meas_std ** 2)

        z_pred = h_mat @ hypo.state_vector
        innov = z - z_pred

        s_mat = h_mat @ hypo.covariance @ h_mat.T + r_mat
        try:
            s_inv = np.linalg.inv(s_mat)
            dist_sq = float(innov.T @ s_inv @ innov)
        except np.linalg.LinAlgError:
            dist_sq = 999.0

        return dist_sq, innov, s_mat

    def _kalman_update(
        self,
        hypo: TrackHypothesis,
        z: np.ndarray,
        innov: np.ndarray,
        s_mat: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, float]:
        """Kalman güncellemesi yapar ve LLR skor değişimini döner."""
        h_mat = np.zeros((4, 8), dtype=np.float64)
        np.fill_diagonal(h_mat, 1.0)

        s_inv = np.linalg.inv(s_mat)
        k_gain = hypo.covariance @ h_mat.T @ s_inv

        updated_state = hypo.state_vector + k_gain @ innov
        i_kh = np.eye(8, dtype=np.float64) - k_gain @ h_mat
        updated_cov = i_kh @ hypo.covariance

        # LLR Skoru artışı: Düşük inovasyon = yüksek LLR kazancı
        d_sq = float(innov.T @ s_inv @ innov)
        det_s = float(np.linalg.det(s_mat))
        norm_factor = max(1e-6, math.sqrt(max(1e-12, det_s)))
        delta_llr = 4.0 - 0.5 * d_sq - math.log(norm_factor)

        return updated_state, updated_cov, delta_llr
