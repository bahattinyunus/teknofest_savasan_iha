import pytest
from core.models import TelemetriPaketi, RakipIHABilgisi, ZamanBilgisi
from autopilot.swarm_tactics import SwarmTacticsController, SwarmFormation, SwarmRole


def test_swarm_wingman_offset_position():
    swarm = SwarmTacticsController(separation_distance_m=50.0)
    # Lider: [41.100, 28.900, 100m], Kuzeye uçuyor (0 deg)
    w_lat, w_lon, w_alt = swarm.compute_wingman_offset_position(
        leader_lat=41.100, leader_lon=28.900, leader_alt=100.0,
        leader_heading_deg=0.0, side="right"
    )

    # Kanatçı liderin arkasında (Güneyinde: lat < 41.100) ve sağında (Doğusunda: lon > 28.900) olmalı
    assert w_lat < 41.100
    assert w_lon > 28.900
    assert w_alt != 100.0


def test_swarm_pincer_attack_vectors():
    swarm = SwarmTacticsController()
    target_rival = RakipIHABilgisi(
        takim_numarasi=9, IHA_enlem=41.105, IHA_boylam=28.905, IHA_irtifa=100.0,
        IHA_dikilme=0.0, IHA_yonelme=180.0, IHA_yatis=0.0
    )
    leader_pos = (41.100, 28.900, 100.0)
    wingman_pos = (41.100, 28.910, 100.0)

    l_hdg, w_hdg = swarm.compute_pincer_attack_vectors(target_rival, leader_pos, wingman_pos)
    assert 0.0 <= l_hdg <= 360.0
    assert 0.0 <= w_hdg <= 360.0
    # Kıskaç açıları birbirinden farklı olmalı
    assert abs(l_hdg - w_hdg) > 10.0


def test_swarm_bait_and_ambush_evaluation():
    swarm = SwarmTacticsController()
    # Kendi İHA'mız: Rakibin tam önünde
    own = TelemetriPaketi(
        takim_numarasi=1, IHA_enlem=41.105, IHA_boylam=28.900, IHA_irtifa=100.0,
        IHA_dikilme=0.0, IHA_yonelme=0.0, IHA_yatis=0.0, IHA_hiz=20.0,
        IHA_batarya=90, IHA_otonom=1, IHA_kilitlenme=0,
        Hedef_merkez_X=0, Hedef_merkez_Y=0, Hedef_genislik=0, Hedef_yukseklik=0,
        GPSSaati=ZamanBilgisi.now()
    )
    # Takım arkadaşı: Yanda güvenli konumda
    partner = TelemetriPaketi(
        takim_numarasi=2, IHA_enlem=41.100, IHA_boylam=28.910, IHA_irtifa=100.0,
        IHA_dikilme=0.0, IHA_yonelme=270.0, IHA_yatis=0.0, IHA_hiz=20.0,
        IHA_batarya=90, IHA_otonom=1, IHA_kilitlenme=0,
        Hedef_merkez_X=0, Hedef_merkez_Y=0, Hedef_genislik=0, Hedef_yukseklik=0,
        GPSSaati=ZamanBilgisi.now()
    )
    # Rakip: [41.100, 28.900], Kuzeye (0°) yönelmiş, doğrudan kendi İHA'mızın peşinde
    rival = RakipIHABilgisi(
        takim_numarasi=3, IHA_enlem=41.100, IHA_boylam=28.900, IHA_irtifa=100.0,
        IHA_dikilme=0.0, IHA_yonelme=0.0, IHA_yatis=0.0
    )

    tactic = swarm.evaluate_bait_and_ambush(own, partner, rival)
    assert tactic["my_role"] == SwarmRole.BAIT.value
    assert tactic["partner_role"] == SwarmRole.HUNTER.value
