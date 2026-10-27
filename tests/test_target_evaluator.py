import pytest
from core.models import HedefKutusu
from vision.target_evaluator import TacticalTargetEvaluator


def test_target_evaluator_prioritizes_center_and_size():
    evaluator = TacticalTargetEvaluator()

    # Hedef 1: Tam merkezde ve büyük (300x200 piksel)
    t1 = HedefKutusu(x1=490, y1=260, x2=790, y2=460, conf=0.9, track_id=1)
    # Hedef 2: Ekranın sol üst köşesinde ve çok küçük (50x50 piksel)
    t2 = HedefKutusu(x1=20, y1=20, x2=70, y2=70, conf=0.5, track_id=2)

    scored = evaluator.evaluate_targets([t1, t2], screen_w=1280, screen_h=720)
    assert len(scored) == 2
    # t1'in skoru t2'den belirgin şekilde yüksek olmalı
    assert scored[0][0].track_id == 1
    assert scored[0][1] > scored[1][1]


def test_target_evaluator_select_best():
    evaluator = TacticalTargetEvaluator()
    t1 = HedefKutusu(x1=490, y1=260, x2=790, y2=460, conf=0.9, track_id=1)
    best = evaluator.select_best_target([t1], screen_w=1280, screen_h=720)
    assert best is not None
    assert best.track_id == 1
