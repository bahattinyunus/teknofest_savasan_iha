import numpy as np
from core.models import HedefKutusu
from vision.optical_flow_tracker import OpticalFlowReIDTracker


def test_optical_flow_coasting_during_temporary_occlusion():
    tracker = OpticalFlowReIDTracker(max_coast_frames=6)
    frame1 = np.zeros((360, 640, 3), dtype=np.uint8)
    frame1[140:200, 260:340] = (40, 180, 240)

    box1 = HedefKutusu(x1=260, y1=140, x2=340, y2=200, conf=0.92, track_id=11)
    out1 = tracker.update_and_recover(frame1, [box1], dt=0.05, current_time=1.0)
    assert len(out1) == 1
    assert out1[0].track_id == 11

    # İkinci karede hedef sağa kaymış ve tespit edilmiş
    frame2 = np.zeros((360, 640, 3), dtype=np.uint8)
    frame2[140:200, 270:350] = (40, 180, 240)
    box2 = HedefKutusu(x1=270, y1=140, x2=350, y2=200, conf=0.90, track_id=11)
    out2 = tracker.update_and_recover(frame2, [box2], dt=0.05, current_time=1.05)
    assert len(out2) == 1

    # Üçüncü karede YOLO tespiti anlık olarak düşüyor (detections == [])
    frame3 = np.zeros((360, 640, 3), dtype=np.uint8)
    frame3[140:200, 280:360] = (40, 180, 240)
    out3 = tracker.update_and_recover(frame3, [], dt=0.05, current_time=1.10)

    # Optik akış ve hız hafızası hedefi ID=11 ile korumalı
    assert len(out3) == 1
    assert out3[0].track_id == 11
    assert out3[0].merkez_x > box2.merkez_x


def test_optical_reid_restores_track_id_after_reappearance():
    tracker = OpticalFlowReIDTracker(max_coast_frames=5, reid_similarity_threshold=0.50)
    frame1 = np.zeros((360, 640, 3), dtype=np.uint8)
    frame1[100:160, 200:280] = (20, 220, 90)

    box_initial = HedefKutusu(x1=200, y1=100, x2=280, y2=160, conf=0.95, track_id=42)
    tracker.update_and_recover(frame1, [box_initial], dt=0.05, current_time=1.0)

    # 1 kare tespit kaybı
    tracker.update_and_recover(frame1, [], dt=0.05, current_time=1.05)

    # Sonraki karede dedektör aynı hedefe yanlışlıkla yeni bir ID (99) veriyor
    box_new_id = HedefKutusu(x1=208, y1=102, x2=288, y2=162, conf=0.91, track_id=99)
    recovered = tracker.update_and_recover(frame1, [box_new_id], dt=0.05, current_time=1.10)

    assert len(recovered) == 1
    assert recovered[0].track_id == 42  # Re-ID eski kilit ID'sini (42) geri yüklemeli
