import pytest
from core.models import TelemetriPaketi, RakipIHABilgisi, ZamanBilgisi, KilitDurumu
from autopilot.tactical_decision_agent import TacticalDecisionAgent, TacticalState


def test_tactical_decision_agent_patrol():
    agent = TacticalDecisionAgent()
    own = TelemetriPaketi(
        takim_numarasi=1, IHA_enlem=41.100, IHA_boylam=28.900, IHA_irtifa=100.0,
        IHA_dikilme=0.0, IHA_yonelme=0.0, IHA_yatis=0.0, IHA_hiz=20.0,
        IHA_batarya=90, IHA_otonom=1, IHA_kilitlenme=0,
        Hedef_merkez_X=0, Hedef_merkez_Y=0, Hedef_genislik=0, Hedef_yukseklik=0,
        GPSSaati=ZamanBilgisi.now()
    )

    state, roll, pitch, heading = agent.evaluate_tactics(own, rivals=[])
    assert state == TacticalState.PATROL


def test_tactical_decision_agent_offensive_wez():
    agent = TacticalDecisionAgent(wez_range_max_m=200.0)
    # Kendi uçağımız: Kuzeye uçuyor (heading 0 deg)
    own = TelemetriPaketi(
        takim_numarasi=1, IHA_enlem=41.100, IHA_boylam=28.900, IHA_irtifa=100.0,
        IHA_dikilme=0.0, IHA_yonelme=0.0, IHA_yatis=0.0, IHA_hiz=20.0,
        IHA_batarya=90, IHA_otonom=1, IHA_kilitlenme=0,
        Hedef_merkez_X=0, Hedef_merkez_Y=0, Hedef_genislik=0, Hedef_yukseklik=0,
        GPSSaati=ZamanBilgisi.now()
    )

    # Rakip İHA: Tam önümüzde (Kuzeyde ~60m ileride) ve o da kuzeye uçuyor (heading 0 deg)
    rival = RakipIHABilgisi(
        takim_numarasi=2, IHA_enlem=41.1005, IHA_boylam=28.900, IHA_irtifa=100.0,
        IHA_dikilme=0.0, IHA_yonelme=0.0, IHA_yatis=0.0
    )

    state, roll, pitch, heading = agent.evaluate_tactics(own, rivals=[rival])
    # Hedef tam önümüzde ve arkasındayız -> WEZ (Kilitlenme Bölgesi)
    assert state == TacticalState.OFFENSIVE_WEZ


def test_tactical_decision_agent_defensive():
    agent = TacticalDecisionAgent()
    own = TelemetriPaketi(
        takim_numarasi=1, IHA_enlem=41.100, IHA_boylam=28.900, IHA_irtifa=100.0,
        IHA_dikilme=0.0, IHA_yonelme=0.0, IHA_yatis=0.0, IHA_hiz=20.0,
        IHA_batarya=90, IHA_otonom=1, IHA_kilitlenme=0,
        Hedef_merkez_X=0, Hedef_merkez_Y=0, Hedef_genislik=0, Hedef_yukseklik=0,
        GPSSaati=ZamanBilgisi.now()
    )

    # Rakip İHA: Tam arkamızda (Güneyde ~50m geride) ve kilit açısında
    trailing_rival = RakipIHABilgisi(
        takim_numarasi=2, IHA_enlem=41.09955, IHA_boylam=28.900, IHA_irtifa=100.0,
        IHA_dikilme=0.0, IHA_yonelme=0.0, IHA_yatis=0.0
    )

    state, roll, pitch, heading = agent.evaluate_tactics(own, rivals=[trailing_rival])
    assert state == TacticalState.DEFENSIVE_EVASION
