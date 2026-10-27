import os
import time
import pytest
import numpy as np
from core.models import HedefKutusu, KilitDurumu
from vision.lock_engine import LockEngine


@pytest.fixture
def dummy_frame():
    # 1280x720 sahte siyah kare
    return np.zeros((720, 1280, 3), dtype=np.uint8)


def test_lock_engine_requires_5_percent_area(dummy_frame):
    """Hedef alan oranı %5'in altındaysa kilitlenme başlamamalıdır."""
    engine = LockEngine(
        gerekli_sure_sn=4.0,
        hedef_alan_orani_min=0.05,
        merkez_tolerans_orani=0.5
    )

    # Ekran merkezi: 640, 360
    # Küçük hedef: 50x50 = 2500 piksel (%0.27 < %5)
    small_box = HedefKutusu(x1=615, y1=335, x2=665, y2=385, conf=0.9, track_id=1)

    durum, sure, hedef = engine.update(dummy_frame, [small_box])
    assert durum in [KilitDurumu.IDLE, KilitDurumu.TRACKING]
    assert sure == 0.0


def test_lock_engine_starts_on_valid_target(dummy_frame):
    """Hedef hem merkezde hem de %5'ten büyükse kilit sayacı başlamalıdır."""
    engine = LockEngine(
        gerekli_sure_sn=4.0,
        hedef_alan_orani_min=0.05,
        merkez_tolerans_orani=0.5
    )

    # Yeterli hedef: 300x200 = 60000 piksel / 921600 = ~%6.5 (> %5)
    valid_box = HedefKutusu(x1=490, y1=260, x2=790, y2=460, conf=0.95, track_id=1)

    durum, sure, hedef = engine.update(dummy_frame, [valid_box])
    assert durum == KilitDurumu.LOCKING
    assert hedef is not None


def test_lock_engine_completes_lock(dummy_frame, tmp_path):
    """4.0 saniye kesintisiz kaldığında LOCKED durumuna geçmeli ve kanıt üretmelidir."""
    engine = LockEngine(
        gerekli_sure_sn=0.2,  # Test için süreyi kısa tutuyoruz
        hedef_alan_orani_min=0.05,
        merkez_tolerans_orani=0.5,
        kanit_dizini=str(tmp_path)
    )

    valid_box = HedefKutusu(x1=490, y1=260, x2=790, y2=460, conf=0.95, track_id=1)

    # İlk adım
    durum, _, _ = engine.update(dummy_frame, [valid_box])
    assert durum == KilitDurumu.LOCKING

    # Süreyi bekle
    time.sleep(0.25)

    # İkinci adım (süre tamamlandı)
    durum, sure, _ = engine.update(dummy_frame, [valid_box])
    assert durum == KilitDurumu.LOCKED
    assert engine.kilit_sayisi == 1
