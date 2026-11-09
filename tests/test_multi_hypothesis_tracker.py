import time
import pytest
import numpy as np
from core.models import HedefKutusu
from core.multi_hypothesis_tracker import MultiHypothesisTracker, TrackStatus, MHTTrack


def test_mht_track_initialization():
    initial_box = HedefKutusu(x1=100.0, y1=100.0, x2=150.0, y2=150.0, conf=0.85)
    track = MHTTrack(track_id=1, initial_box=initial_box)

    assert track.track_id == 1
    assert track.status == TrackStatus.TENTATIVE
    assert len(track.hypotheses) == 1
    assert track.best_hypothesis.state_vector[0] == 125.0  # cx
    assert track.best_hypothesis.state_vector[1] == 125.0  # cy


def test_mht_tracker_confirmation_and_coasting():
    tracker = MultiHypothesisTracker(confirmation_hits=3, deletion_misses=4)

    # 1. Adım: İlk Tespit
    box1 = HedefKutusu(x1=100.0, y1=100.0, x2=160.0, y2=160.0, conf=0.8)
    res1 = tracker.update([box1], current_time=0.0)
    # İlk adımda henüz TENTATIVE olduğu için çıktı listesinde olmayabilir
    assert len(tracker.tracks) == 1

    # 2. Adım: Tutarlı 2. Tespit (hafif yer değişimi)
    box2 = HedefKutusu(x1=102.0, y1=101.0, x2=162.0, y2=161.0, conf=0.85)
    tracker.update([box2], current_time=0.05)

    # 3. Adım: Tutarlı 3. Tespit -> CONFIRMED olmalı!
    box3 = HedefKutusu(x1=104.0, y1=102.0, x2=164.0, y2=162.0, conf=0.9)
    res3 = tracker.update([box3], current_time=0.10)
    assert len(res3) == 1
    assert res3[0].track_id == 1
    assert tracker.tracks[1].status == TrackStatus.CONFIRMED

    # 4. Adım: Hedef anlık kayboldu (boş tespit listesi) -> COASTING olmalı
    res4 = tracker.update([], current_time=0.15)
    assert len(res4) == 1  # Coasting durumundaki tahmin edilen kutu döner
    assert tracker.tracks[1].status == TrackStatus.COASTING


def test_mht_cross_tracks_and_pruning():
    tracker = MultiHypothesisTracker(max_hypotheses_per_track=3)

    # İki farklı hedef başlat
    target_a = HedefKutusu(x1=50.0, y1=100.0, x2=100.0, y2=140.0)
    target_b = HedefKutusu(x1=300.0, y1=200.0, x2=350.0, y2=240.0)
    tracker.update([target_a, target_b], current_time=0.0)
    assert len(tracker.tracks) == 2

    # Hipotez sayısı sınırını (max_hypotheses_per_track) kontrol et
    for i in range(5):
        box_a = HedefKutusu(x1=50.0 + i * 2, y1=100.0, x2=100.0 + i * 2, y2=140.0)
        box_b = HedefKutusu(x1=300.0 - i * 2, y1=200.0, x2=350.0 - i * 2, y2=240.0)
        tracker.update([box_a, box_b], current_time=0.05 * (i + 1))

    for t in tracker.tracks.values():
        assert len(t.hypotheses) <= tracker.max_hypotheses_per_track
