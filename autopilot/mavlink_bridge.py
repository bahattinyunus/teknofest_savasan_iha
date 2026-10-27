import time
import math
import threading
from typing import Optional, Dict, Any
from core.models import TelemetriPaketi, ZamanBilgisi
from core.logger import logger
from core.event_bus import bus, EVENT_TELEMETRY_UPDATED


class MavlinkBridge:
    """PyMAVLink tabanlı Otopilot (Pixhawk / Cube / SITL) haberleşme köprüsü."""

    def __init__(self, connection_string: str = "tcp:127.0.0.1:5760", baud: int = 115200, takim_no: int = 1):
        self.connection_string = connection_string
        self.baud = baud
        self.takim_no = takim_no
        
        self.master = None
        self.is_connected = False
        self.is_running = False
        self._thread: Optional[threading.Thread] = None

        # Güncel Otopilot Değerleri
        self.lat: float = 41.1040
        self.lon: float = 28.9050
        self.alt: float = 80.0
        self.pitch: float = 0.0
        self.yaw: float = 0.0
        self.roll: float = 0.0
        self.groundspeed: float = 16.0
        self.battery_remaining: int = 95
        self.is_armed: bool = False
        self.flight_mode: str = "MANUAL"
        self.is_autonomous: int = 0

    def connect(self) -> bool:
        """Otopilota bağlantı açar."""
        try:
            from pymavlink import mavutil
            logger.info(f"MAVLink bağlantısı kuruluyor: {self.connection_string} (Baud: {self.baud})")
            self.master = mavutil.mavlink_connection(self.connection_string, baud=self.baud)
            
            # İlk Heartbeat bekle
            logger.info("Heartbeat bekleniyor...")
            msg = self.master.wait_heartbeat(timeout=5)
            if msg:
                self.is_connected = True
                logger.info(f"Otopilot bağlandı! Sistem ID: {self.master.target_system}, Bileşen: {self.master.target_component}")
                return True
            else:
                logger.warning("Heartbeat zaman aşımına uğradı.")
                return False
        except ImportError:
            logger.error("pymavlink kütüphanesi eksik! 'pip install pymavlink' çalıştırın.")
            return False
        except Exception as e:
            logger.error(f"MAVLink bağlantı hatası: {e}")
            return False

    def start(self):
        """Telemetri dinleme iş parçacığını başlatır."""
        if not self.is_connected and not self.connect():
            logger.warning("Otopilota bağlanılamadı, telemetri dinleyici başlatılamadı.")
            return
        
        self.is_running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True, name="MavlinkListenThread")
        self._thread.start()

    def stop(self):
        self.is_running = False
        if self.master:
            try:
                self.master.close()
            except Exception:
                pass

    def _listen_loop(self):
        """MAVLink paketlerini sürekli okuyan arka plan döngüsü."""
        while self.is_running and self.master:
            try:
                msg = self.master.recv_match(blocking=True, timeout=1.0)
                if not msg:
                    continue

                msg_type = msg.get_type()

                if msg_type == 'HEARTBEAT':
                    # Uçuş modu ve arm durumu
                    from pymavlink import mavutil
                    self.flight_mode = mavutil.mode_string_v10(msg)
                    self.is_autonomous = 1 if self.flight_mode in ["AUTO", "GUIDED"] else 0

                elif msg_type == 'GLOBAL_POSITION_INT':
                    self.lat = msg.lat / 1e7
                    self.lon = msg.lon / 1e7
                    self.alt = msg.relative_alt / 1000.0  # metre cinsinden
                    self.groundspeed = math.hypot(msg.vx, msg.vy) / 100.0

                elif msg_type == 'ATTITUDE':
                    self.roll = math.degrees(msg.roll)
                    self.pitch = math.degrees(msg.pitch)
                    self.yaw = (math.degrees(msg.yaw) + 360) % 360

                elif msg_type == 'SYS_STATUS':
                    self.battery_remaining = max(0, min(100, msg.battery_remaining))

            except Exception as e:
                logger.error(f"MAVLink okuma hatası: {e}")
                time.sleep(0.5)

    def get_telemetry_packet(
        self,
        target_center_x: int = 0,
        target_center_y: int = 0,
        target_w: int = 0,
        target_h: int = 0,
        is_locked: int = 0
    ) -> TelemetriPaketi:
        """Güncel otopilot durumundan şartnameye uygun TelemetriPaketi üretir."""
        return TelemetriPaketi(
            takim_numarasi=self.takim_no,
            IHA_enlem=self.lat,
            IHA_boylam=self.lon,
            IHA_irtifa=self.alt,
            IHA_dikilme=self.pitch,
            IHA_yonelme=self.yaw,
            IHA_yatis=self.roll,
            IHA_hiz=self.groundspeed,
            IHA_batarya=self.battery_remaining,
            IHA_otonom=self.is_autonomous,
            IHA_kilitlenme=is_locked,
            Hedef_merkez_X=target_center_x,
            Hedef_merkez_Y=target_center_y,
            Hedef_genislik=target_w,
            Hedef_yukseklik=target_h,
            GPSSaati=ZamanBilgisi.now()
        )

    def set_mode(self, mode_name: str) -> bool:
        """Uçuş modunu değiştirir (Örn: 'RTL', 'GUIDED', 'AUTO', 'FBWA')."""
        if not self.master:
            return False
        try:
            from pymavlink import mavutil
            mode_id = self.master.mode_mapping().get(mode_name)
            if mode_id is None:
                logger.error(f"Bilinmeyen uçuş modu: {mode_name}")
                return False
            self.master.set_mode(mode_id)
            logger.info(f"Otopilot modu değiştirildi: {mode_name}")
            return True
        except Exception as e:
            logger.error(f"Mod değiştirme hatası: {e}")
            return False


class MockMavlinkBridge(MavlinkBridge):
    """Fiziksel otopilot veya SITL olmadan gerçekçi telemetri üreten simülasyon köprüsü."""

    def __init__(self, takim_no: int = 1):
        super().__init__(connection_string="MOCK", takim_no=takim_no)
        self.is_connected = True
        self.start_time = time.time()
        self.is_autonomous = 1
        self.flight_mode = "GUIDED"
        logger.info("MockMavlinkBridge (Sanal Otopilot) aktif edildi.")

    def start(self):
        self.is_running = True
        self._thread = threading.Thread(target=self._simulate_loop, daemon=True, name="MockMavlinkThread")
        self._thread.start()

    def _simulate_loop(self):
        while self.is_running:
            t = time.time() - self.start_time
            # Uçağın havada hafif manevralar yapmasını simüle et
            self.pitch = 2.0 + 1.5 * math.sin(t * 0.4)
            self.roll = 4.0 * math.sin(t * 0.3)
            self.yaw = (t * 5.0) % 360.0
            self.alt = 85.0 + 5.0 * math.sin(t * 0.2)
            self.groundspeed = 18.0 + 1.0 * math.cos(t * 0.5)
            self.battery_remaining = max(10, int(98 - (t / 60.0)))

            # Koordinatları hafif kaydır (Daire çizerek uçuş)
            self.lat = 41.1040 + 0.002 * math.cos(math.radians(self.yaw))
            self.lon = 28.9050 + 0.002 * math.sin(math.radians(self.yaw))

            time.sleep(0.1)  # 10 Hz güncelleme
