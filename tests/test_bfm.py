import pytest
from core.models import TelemetriPaketi, RakipIHABilgisi, ZamanBilgisi
from autopilot.bfm_maneuvers import BFMEvasiveTactics, ManevraTipi


def test_bfm_threat_detection():
    bfm = BFMEvasiveTactics(tehdit_mesafesi_m=100.0, tehdit_aci_konisi_deg=30.0)

    # Bizim İHA: Kuzeye (0 derece) uçuyor
    own = TelemetriPaketi(
        takim_numarasi=1, IHA_enlem=41.100, IHA_boylam=28.900, IHA_irtifa=100.0,
        IHA_dikilme=0.0, IHA_yonelme=0.0, IHA_yatis=0.0, IHA_hiz=20.0,
        IHA_batarya=90, IHA_otonom=1, IHA_kilitlenme=0,
        Hedef_merkez_X=0, Hedef_merkez_Y=0, Hedef_genislik=0, Hedef_yukseklik=0,
        GPSSaati=ZamanBilgisi.now()
    )

    # Rakip İHA: Tam arkamızda (Güneyde, ~50 metre arkamızda)
    # 0.00045 derece ~ 50m
    trailing_rival = RakipIHABilgisi(
        takim_numarasi=2, IHA_enlem=41.09955, IHA_boylam=28.900, IHA_irtifa=100.0,
        IHA_dikilme=0.0, IHA_yonelme=0.0, IHA_yatis=0.0
    )

    threat = bfm.evaluate_threat(own, [trailing_rival])
    assert threat is not None
    assert threat.takim_numarasi == 2


def test_bfm_maneuver_execution():
    bfm = BFMEvasiveTactics(maks_yatis_acisi_deg=45.0)

    own = TelemetriPaketi(
        takim_numarasi=1, IHA_enlem=41.100, IHA_boylam=28.900, IHA_irtifa=100.0,
        IHA_dikilme=0.0, IHA_yonelme=0.0, IHA_yatis=0.0, IHA_hiz=20.0,
        IHA_batarya=90, IHA_otonom=1, IHA_kilitlenme=0,
        Hedef_merkez_X=0, Hedef_merkez_Y=0, Hedef_genislik=0, Hedef_yukseklik=0,
        GPSSaati=ZamanBilgisi.now()
    )

    trailing_rival = RakipIHABilgisi(
        takim_numarasi=2, IHA_enlem=41.09955, IHA_boylam=28.900, IHA_irtifa=100.0,
        IHA_dikilme=0.0, IHA_yonelme=0.0, IHA_yatis=0.0
    )

    manevra, roll, pitch, heading = bfm.execute_evasion(own, trailing_rival)
    assert manevra == ManevraTipi.BREAK_TURN
    assert abs(roll) == 45.0
