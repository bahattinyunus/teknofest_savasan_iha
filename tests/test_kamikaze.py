import pytest
import numpy as np
from core.models import KamikazeDurumu, QRKoordinati, HSSBolgesi, KamikazePaketi, ZamanBilgisi
from vision.kamikaze_engine import KamikazeEngine
from autopilot.geofence import GeofenceMonitor


def test_kamikaze_engine_workflow():
    engine = KamikazeEngine(min_pullup_alt_m=20.0, hedef_yaklasma_mesafesi_m=100.0)
    assert engine.durum == KamikazeDurumu.BEKLEMEDE

    # 1. Hedef ata
    target_qr = QRKoordinati(qrEnlem=41.1045, qrBoylam=28.9055)
    engine.set_hedef_koordinati(target_qr)
    assert engine.durum == KamikazeDurumu.HEDEFE_YONELIS

    # 2. Hedefe uzak bir nokta (Dalış başlamaz)
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    durum, _, pullup = engine.update(dummy_frame, 41.1080, 28.9080, current_alt=80.0)
    assert durum == KamikazeDurumu.HEDEFE_YONELIS
    assert pullup is False

    # 3. Hedefe yakın nokta (Dalış başlar)
    durum, _, pullup = engine.update(dummy_frame, 41.1045, 28.9055, current_alt=60.0)
    assert durum == KamikazeDurumu.DALISTA

    # 4. Asgari irtifa ihlali (Pull-up emri üretir)
    durum, _, pullup = engine.update(dummy_frame, 41.1045, 28.9055, current_alt=18.0)
    assert pullup is True
    assert durum in [KamikazeDurumu.PAS_GECME, KamikazeDurumu.TAMAMLANDI]


def test_hss_threat_avoidance():
    geo = GeofenceMonitor(
        polygon_coords=[[41.10, 28.90], [41.10, 28.92], [41.12, 28.92], [41.12, 28.90]],
        min_alt_m=30.0,
        max_alt_m=150.0
    )
    # HSS Bölgesi: [41.105, 28.905], yarıçap 80m, irtifa 0-100m
    hss = HSSBolgesi(hss_id=1, merkez_enlem=41.105, merkez_boylam=28.905, yaricap_m=80.0, alt_irtifa_m=0.0, ust_irtifa_m=100.0)
    geo.set_hss_bolgeleri([hss])

    # HSS merkezi tam içinde (İhlal var)
    is_safe, msg = geo.validate_position(41.105, 28.905, 50.0)
    assert is_safe is False
    assert "HSS İHLALİ" in msg

    # HSS'in üstünden uçuş (İrtifa 110m > HSS tavanı 100m -> Güvenli)
    is_safe, msg = geo.validate_position(41.105, 28.905, 110.0)
    assert is_safe is True
    assert msg == "GÜVENLİ BÖLGE"


def test_kamikaze_paketi_serialization():
    z1 = ZamanBilgisi(saat=14, dakika=20, saniye=10, milisaniye=100)
    z2 = ZamanBilgisi(saat=14, dakika=20, saniye=15, milisaniye=200)
    paket = KamikazePaketi(
        kamikazeBaslangicZamani=z1,
        kamikazeBitisZamani=z2,
        qrMetni="TEKNOFEST_QR_12345",
        otonom=1
    )
    d = paket.to_dict()
    assert d["qrMetni"] == "TEKNOFEST_QR_12345"
    assert d["otonom"] == 1
    assert d["kamikazeBaslangicZamani"]["saniye"] == 10
