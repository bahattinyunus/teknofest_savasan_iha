import pytest
from core.models import (
    ZamanBilgisi,
    HedefKutusu,
    TelemetriPaketi,
    RakipIHABilgisi,
    SunucuYaniti,
    KilitlenmePaketi
)


def test_zaman_bilgisi():
    z = ZamanBilgisi(saat=14, dakika=30, saniye=15, milisaniye=500)
    assert z.to_dict() == {"saat": 14, "dakika": 30, "saniye": 15, "milisaniye": 500}
    assert z.to_seconds() == 14 * 3600 + 30 * 60 + 15 + 0.5
    assert str(z) == "14:30:15.500"


def test_hedef_kutusu_geometri():
    # 1280 x 720 ekran
    # Kutu: 200 x 200 -> Alan = 40000
    # Ekran alanı = 921600 -> Oran = 40000 / 921600 = ~0.0434 (%4.34)
    box = HedefKutusu(x1=100, y1=100, x2=300, y2=300)
    assert box.genislik == 200
    assert box.yukseklik == 200
    assert box.merkez_x == 200
    assert box.merkez_y == 200
    assert box.alan == 40000

    ratio = box.alan_orani(1280, 720)
    assert pytest.approx(ratio, 0.001) == 40000 / (1280 * 720)


def test_telemetri_paketi_serialization():
    z = ZamanBilgisi(saat=12, dakika=0, saniye=0, milisaniye=0)
    tel = TelemetriPaketi(
        takim_numarasi=1,
        IHA_enlem=41.104,
        IHA_boylam=28.905,
        IHA_irtifa=100.0,
        IHA_dikilme=1.5,
        IHA_yonelme=180.0,
        IHA_yatis=0.0,
        IHA_hiz=20.0,
        IHA_batarya=90,
        IHA_otonom=1,
        IHA_kilitlenme=0,
        Hedef_merkez_X=640,
        Hedef_merkez_Y=360,
        Hedef_genislik=200,
        Hedef_yukseklik=150,
        GPSSaati=z
    )
    d = tel.to_dict()
    assert d["takim_numarasi"] == 1
    assert d["GPSSaati"]["saat"] == 12
    assert d["IHA_otonom"] == 1


def test_sunucu_yaniti_parsing():
    raw_response = {
        "sunucusaati": {"saat": 15, "dakika": 20, "saniye": 10, "milisaniye": 250},
        "konumBilgileri": [
            {
                "takim_numarasi": 2,
                "IHA_enlem": 41.105,
                "IHA_boylam": 28.906,
                "IHA_irtifa": 110.0,
                "IHA_dikilme": 0.0,
                "IHA_yonelme": 90.0,
                "IHA_yatis": 0.0,
                "zaman_farki": 35
            }
        ]
    }
    resp = SunucuYaniti.from_dict(raw_response)
    assert resp.sunucusaati.saat == 15
    assert len(resp.konumBilgileri) == 1
    assert resp.konumBilgileri[0].takim_numarasi == 2
    assert resp.konumBilgileri[0].zaman_farki == 35
