import pytest
from core.models import TelemetriPaketi, RakipIHABilgisi, ZamanBilgisi
from autopilot.guidance import GuidanceController, PurePursuit, FlightEnvelopeLimiter


def test_pure_pursuit_heading():
    # Kendi konumu (0, 0), hedef konumu (1, 1) -> Kuzeydoğu (45 derece)
    heading = PurePursuit.compute_heading(0.0, 0.0, 1.0, 1.0)
    assert pytest.approx(heading, 0.1) == 45.0


def test_flight_envelope_limiter():
    limiter = FlightEnvelopeLimiter(max_bank_deg=45.0, max_g_load=2.0)
    # Hız: 20 m/s, Dönüş hızı: 10 deg/s
    bank = limiter.calculate_coordinated_bank(20.0, 10.0)
    assert 0.0 < bank <= 45.0


def test_guidance_controller_facade():
    controller = GuidanceController(method="pure_pursuit")
    tel = TelemetriPaketi(
        takim_numarasi=1, IHA_enlem=41.10, IHA_boylam=28.90, IHA_irtifa=100.0,
        IHA_dikilme=0.0, IHA_yonelme=0.0, IHA_yatis=0.0, IHA_hiz=20.0,
        IHA_batarya=90, IHA_otonom=1, IHA_kilitlenme=0,
        Hedef_merkez_X=0, Hedef_merkez_Y=0, Hedef_genislik=0, Hedef_yukseklik=0,
        GPSSaati=ZamanBilgisi.now()
    )
    rival = RakipIHABilgisi(
        takim_numarasi=2, IHA_enlem=41.11, IHA_boylam=28.90, IHA_irtifa=100.0,
        IHA_dikilme=0.0, IHA_yonelme=0.0, IHA_yatis=0.0
    )
    hdg = controller.step_gps_pursuit(tel, rival)
    # Tam kuzey yönü (0 veya 360 derece)
    assert pytest.approx(hdg, 0.1) == 0.0 or pytest.approx(hdg, 0.1) == 360.0
