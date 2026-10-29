import pytest
import numpy as np
from core.models import TelemetriPaketi, RakipIHABilgisi, HSSBolgesi, ZamanBilgisi, KilitDurumu
from vision.tactical_radar import TacticalRadarMinimap


def test_tactical_radar_rendering():
    radar = TacticalRadarMinimap(size=200, max_range_m=150.0)

    own = TelemetriPaketi(
        takim_numarasi=1, IHA_enlem=41.100, IHA_boylam=28.900, IHA_irtifa=100.0,
        IHA_dikilme=0.0, IHA_yonelme=45.0, IHA_yatis=0.0, IHA_hiz=20.0,
        IHA_batarya=90, IHA_otonom=1, IHA_kilitlenme=0,
        Hedef_merkez_X=0, Hedef_merkez_Y=0, Hedef_genislik=0, Hedef_yukseklik=0,
        GPSSaati=ZamanBilgisi.now()
    )

    rival = RakipIHABilgisi(
        takim_numarasi=2, IHA_enlem=41.1005, IHA_boylam=28.9005, IHA_irtifa=110.0,
        IHA_dikilme=0.0, IHA_yonelme=180.0, IHA_yatis=0.0
    )

    hss = HSSBolgesi(hss_id=1, merkez_enlem=41.101, merkez_boylam=28.901, yaricap_m=50.0, alt_irtifa_m=0.0, ust_irtifa_m=120.0)

    radar_img = radar.render_radar(own, [rival], [hss], lock_status=KilitDurumu.LOCKING)

    assert radar_img is not None
    assert radar_img.shape == (200, 200, 3)
    # Arka plan rengi dışındaki piksel varlığı (çizim başarılı mı?)
    assert np.any(radar_img != 15)


def test_tactical_radar_hud_overlay():
    radar = TacticalRadarMinimap(size=100)
    hud_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    radar_img = np.full((100, 100, 3), 200, dtype=np.uint8)

    overlaid = radar.overlay_on_hud(hud_frame, radar_img, x_offset=10, y_offset=10)
    assert overlaid.shape == (720, 1280, 3)
    # Bindirme bölgesinde pikseller güncellenmeli
    assert np.any(overlaid[15, 15] > 0)
