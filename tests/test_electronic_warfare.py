"""
Elektronik Harp (EW), Anti-Spoofing, Karıştırma ve Decoy Filtresi Birim Testleri
"""

import pytest
import time
from core.electronic_warfare import ElectronicWarfareSuite
from core.models import EWAlertLevel, EWStatus, HedefKutusu


class TestElectronicWarfare:

    @pytest.fixture
    def ew(self):
        return ElectronicWarfareSuite(
            max_physical_speed_mps=50.0,
            max_physical_accel_g=6.0,
            rolling_window_size=10
        )

    def test_gnss_initialization_and_sanity(self, ew):
        # İlk GNSS örneği başarılı olmalı
        ok, reason = ew.update_gnss_sanity(
            lat=41.100, lon=28.900, alt_m=60.0,
            hdop=1.1, sat_count=12, reported_speed_mps=22.0,
            timestamp_s=100.0
        )
        assert ok is True
        assert reason == "GNSS_INITIALIZED"

        # Mantıklı bir sonraki adım (0.1 sn sonra 2 metre doğuya)
        ok2, reason2 = ew.update_gnss_sanity(
            lat=41.100, lon=28.900025, alt_m=60.2,
            hdop=1.1, sat_count=12, reported_speed_mps=22.1,
            timestamp_s=100.1
        )
        assert ok2 is True
        assert reason2 == "GNSS_SECURE"

    def test_gnss_spoofing_teleportation(self, ew):
        # Başlangıç
        ew.update_gnss_sanity(lat=41.100, lon=28.900, alt_m=60.0, timestamp_s=100.0)

        # 0.1 saniye sonra 5 kilometre öteye sıçrama (Spoofing)
        ok, reason = ew.update_gnss_sanity(
            lat=41.150, lon=28.950, alt_m=60.0,
            timestamp_s=100.1
        )
        assert ok is False
        assert "GNSS_SPOOFING" in reason

        status = ew.get_status()
        assert status.gnss_aldatma_tespiti is True
        assert status.tehdit_seviyesi in [EWAlertLevel.THREAT, EWAlertLevel.CRITICAL_JAMMING]

    def test_gnss_jamming_insufficient_satellites(self, ew):
        ok, reason = ew.update_gnss_sanity(
            lat=41.100, lon=28.900, alt_m=60.0,
            sat_count=2, hdop=5.5
        )
        assert ok is False
        assert "GNSS_JAMMING" in reason

    def test_telemetry_rf_jamming_detection(self, ew):
        # Başarısız paketler ve CRC hataları besle
        for _ in range(6):
            ew.record_telemetry_packet(success=False, latency_ms=850.0, crc_valid=False)

        status = ew.get_status()
        assert status.rf_karistirma_tespiti is True
        assert status.tehdit_seviyesi in [EWAlertLevel.THREAT, EWAlertLevel.CRITICAL_JAMMING]

    def test_visual_decoy_filtering(self, ew):
        # 1 adet gerçek hedef, 1 adet anormal ince/uzun sahte hedef (flare / yansıma)
        real_box = HedefKutusu(x1=200, y1=200, x2=280, y2=260, conf=0.88, track_id=1)
        fake_box = HedefKutusu(x1=500, y1=300, x2=750, y2=310, conf=0.75, track_id=2)  # Aspect ratio 250/10 = 25.0

        filtered = ew.filter_visual_decoys([real_box, fake_box])
        assert len(filtered) == 1
        assert filtered[0].track_id == 1

        status = ew.get_status()
        assert status.optik_sahte_hedef_tespiti is True

    def test_emcon_mode(self, ew):
        ew.set_emcon(True)
        status = ew.get_status()
        assert status.emcon_aktif is True
        assert status.tehdit_seviyesi == EWAlertLevel.EMCON
        assert "EMCON" in status.onerilen_eylem

        ew.set_emcon(False)
        status_after = ew.get_status()
        assert status_after.emcon_aktif is False
