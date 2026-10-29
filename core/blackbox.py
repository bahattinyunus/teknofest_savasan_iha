import os
import time
import json
import queue
import threading
from typing import Optional, Dict, Any
from datetime import datetime
from .models import TelemetriPaketi, ZamanBilgisi
from .logger import logger
from .event_bus import (
    bus,
    EVENT_LOCK_STARTED,
    EVENT_LOCK_SUCCESS,
    EVENT_LOCK_LOST,
    EVENT_GEOFENCE_ALERT,
    EVENT_SERVER_STATUS
)


class FlightBlackBox:
    """Uçuş Kara Kutusu (Black Box Flight Recorder).
    
    Yarışma uçuşu boyunca tüm telemetriyi (10-20 Hz), olayları (Event log)
    ve hakem iletişimini döngüsel ve kaza anında dahi kurtarılabilir şekilde kaydeder.
    """

    def __init__(self, base_log_dir: str = "logs"):
        self.base_log_dir = base_log_dir
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_dir = os.path.join(self.base_log_dir, f"session_{timestamp}")
        os.makedirs(self.session_dir, exist_ok=True)

        self.telemetry_csv_path = os.path.join(self.session_dir, "telemetry.csv")
        self.events_jsonl_path = os.path.join(self.session_dir, "events.jsonl")
        self.summary_json_path = os.path.join(self.session_dir, "flight_summary.json")

        self._queue = queue.Queue(maxsize=1000)
        self.is_recording = False
        self._thread: Optional[threading.Thread] = None

        # Uçuş İstatistikleri
        self.start_time: float = 0.0
        self.telemetry_count: int = 0
        self.max_alt: float = 0.0
        self.min_alt: float = 9999.0
        self.max_speed: float = 0.0
        self.start_battery: int = 100
        self.end_battery: int = 100
        self.total_locks: int = 0

        self._init_csv_header()
        self._setup_event_listeners()

    def _init_csv_header(self):
        with open(self.telemetry_csv_path, "w", encoding="utf-8") as f:
            f.write(
                "timestamp,lat,lon,alt,pitch,yaw,roll,speed,battery,autonomous,locked,target_cx,target_cy,target_w,target_h\n"
            )

    def _setup_event_listeners(self):
        def on_event(event_type: str, **kwargs):
            self.log_event(event_type, kwargs)

        bus.subscribe(EVENT_LOCK_STARTED, lambda **kw: on_event("LOCK_STARTED", **kw))
        bus.subscribe(EVENT_LOCK_SUCCESS, lambda **kw: self._on_lock_success(**kw))
        bus.subscribe(EVENT_LOCK_LOST, lambda **kw: on_event("LOCK_LOST", **kw))
        bus.subscribe(EVENT_GEOFENCE_ALERT, lambda **kw: on_event("GEOFENCE_ALERT", **kw))
        bus.subscribe(EVENT_SERVER_STATUS, lambda **kw: on_event("SERVER_STATUS", **kw))

    def _on_lock_success(self, **kwargs):
        self.total_locks += 1
        self.log_event("LOCK_SUCCESS", kwargs)

    def log_telemetry(self, tel: TelemetriPaketi):
        """Telemetri paketini kuyruğa ekler."""
        if not self.is_recording:
            return

        # İstatistikleri güncelle
        self.telemetry_count += 1
        self.max_alt = max(self.max_alt, tel.IHA_irtifa)
        self.min_alt = min(self.min_alt, tel.IHA_irtifa)
        self.max_speed = max(self.max_speed, tel.IHA_hiz)
        self.end_battery = tel.IHA_batarya
        if self.telemetry_count == 1:
            self.start_battery = tel.IHA_batarya

        line = (
            f"{time.time():.3f},{tel.IHA_enlem:.6f},{tel.IHA_boylam:.6f},{tel.IHA_irtifa:.2f},"
            f"{tel.IHA_dikilme:.2f},{tel.IHA_yonelme:.2f},{tel.IHA_yatis:.2f},{tel.IHA_hiz:.2f},"
            f"{tel.IHA_batarya},{tel.IHA_otonom},{tel.IHA_kilitlenme},{tel.Hedef_merkez_X},"
            f"{tel.Hedef_merkez_Y},{tel.Hedef_genislik},{tel.Hedef_yukseklik}\n"
        )
        try:
            self._queue.put_nowait(("CSV", line))
        except queue.Full:
            pass

    def log_event(self, event_name: str, payload: Dict[str, Any]):
        """Kritik uçuş olayını JSONL dosyasına kaydeder."""
        record = {
            "timestamp": time.time(),
            "time_str": datetime.now().isoformat(),
            "event": event_name,
            "data": str(payload)
        }
        try:
            self._queue.put_nowait(("EVENT", json.dumps(record, ensure_ascii=False) + "\n"))
        except queue.Full:
            pass

    def start(self):
        """Kara kutu yazıcı iş parçacığını başlatır."""
        self.is_recording = True
        self.start_time = time.time()
        self._thread = threading.Thread(target=self._writer_loop, daemon=True, name="BlackBoxWriter")
        self._thread.start()
        logger.info(f"FlightBlackBox (Kara Kutu) kayıt oturumu başlatıldı -> {self.session_dir}")

    def stop(self):
        """Kayıt oturumunu kapatır ve özet istatistik dosyasını oluşturur."""
        self.is_recording = False
        time.sleep(0.1)

        # Uçuş Özet Raporu (Flight Summary)
        duration_sec = time.time() - (self.start_time or time.time())
        summary = {
            "session_dir": self.session_dir,
            "ucus_suresi_sn": round(duration_sec, 2),
            "toplam_telemetri_noktasi": self.telemetry_count,
            "maksimum_irtifa_m": round(self.max_alt, 2) if self.max_alt != 0.0 else 0.0,
            "asgari_irtifa_m": round(self.min_alt, 2) if self.min_alt != 9999.0 else 0.0,
            "maksimum_hiz_m_s": round(self.max_speed, 2),
            "baslangic_batarya": self.start_battery,
            "bitis_batarya": self.end_battery,
            "tuketilen_batarya_yuzdesi": self.start_battery - self.end_battery,
            "onaylanan_kilitlenme_sayisi": self.total_locks,
            "kazanilan_tahmini_puan": self.total_locks * 100
        }

        with open(self.summary_json_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        logger.info(f"Uçuş Kara Kutusu başarıyla kapatıldı. Özet: {summary['ucus_suresi_sn']}sn, {self.total_locks} Kilit!")

    def _writer_loop(self):
        csv_file = open(self.telemetry_csv_path, "a", encoding="utf-8", buffering=1)
        event_file = open(self.events_jsonl_path, "a", encoding="utf-8", buffering=1)

        while self.is_recording or not self._queue.empty():
            try:
                rec_type, data = self._queue.get(timeout=0.2)
                if rec_type == "CSV":
                    csv_file.write(data)
                elif rec_type == "EVENT":
                    event_file.write(data)
                self._queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"BlackBox yazma hatası: {e}")

        csv_file.close()
        event_file.close()
