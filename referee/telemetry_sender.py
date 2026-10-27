import time
import threading
from typing import Optional, Callable
from core.models import TelemetriPaketi, SunucuYaniti
from core.logger import logger
from core.event_bus import bus, EVENT_RIVALS_UPDATED, EVENT_SERVER_STATUS
from .client import RefereeClient


class TelemetrySenderThread(threading.Thread):
    """Hakem sunucusuna şartnamedeki frekansta (1-5 Hz) periyodik telemetri gönderen iş parçacığı."""

    def __init__(
        self,
        client: RefereeClient,
        frequency_hz: float = 3.0,
        telemetry_provider: Optional[Callable[[], Optional[TelemetriPaketi]]] = None
    ):
        super().__init__(name="TelemetrySenderThread", daemon=True)
        self.client = client
        self.interval = 1.0 / max(0.5, min(10.0, frequency_hz))
        self.telemetry_provider = telemetry_provider
        self.is_running = False
        self.latest_telemetry: Optional[TelemetriPaketi] = None
        self.latest_server_response: Optional[SunucuYaniti] = None
        self._lock = threading.Lock()

    def set_telemetry(self, telemetri: TelemetriPaketi):
        """Dışarıdan en güncel telemetri paketini günceller."""
        with self._lock:
            self.latest_telemetry = telemetri

    def start_loop(self):
        """Gönderici döngüsünü başlatır."""
        self.is_running = True
        self.start()
        logger.info(f"Telemetri gönderici thread başlatıldı. Frekans: {1.0 / self.interval:.1f} Hz")

    def stop_loop(self):
        """Gönderici döngüsünü durdurur."""
        self.is_running = False

    def run(self):
        while self.is_running:
            start_time = time.time()

            # Oturum açık değilse giriş yapmayı dene
            if not self.client.is_logged_in:
                success = self.client.giris_yap()
                bus.emit(EVENT_SERVER_STATUS, bagli=success, logged_in=self.client.is_logged_in)
                if not success:
                    time.sleep(2.0)
                    continue

            # Gönderilecek paketi temin et
            current_packet = None
            if self.telemetry_provider is not None:
                current_packet = self.telemetry_provider()
            
            if current_packet is None:
                with self._lock:
                    current_packet = self.latest_telemetry

            if current_packet is not None:
                # Sunucu senkronize zamanını pakete bas
                current_packet.GPSSaati = self.client.time_sync.get_synced_time()
                
                success, response = self.client.telemetri_gonder(current_packet)
                bus.emit(EVENT_SERVER_STATUS, bagli=success, logged_in=self.client.is_logged_in)

                if success and response is not None:
                    self.latest_server_response = response
                    # Rakip İHA konumlarını EventBus üzerinden bildir
                    bus.emit(EVENT_RIVALS_UPDATED, rakipler=response.konumBilgileri, sunucusaati=response.sunucusaati)

            # İstenen frekansı tutturmak için kalan süre kadar uyu
            elapsed = time.time() - start_time
            sleep_time = max(0.005, self.interval - elapsed)
            time.sleep(sleep_time)

        # Döngü bittiğinde güvenli çıkış yap
        if self.client.is_logged_in:
            self.client.cikis_yap()
