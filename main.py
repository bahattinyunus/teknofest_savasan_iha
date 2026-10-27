import os
import sys
import time
import yaml
import argparse
import threading
from typing import Dict, Any, Optional
import cv2
import numpy as np

from core.logger import setup_logger, logger
from core.models import TelemetriPaketi, KilitDurumu, ZamanBilgisi
from core.event_bus import (
    bus,
    EVENT_FRAME_PROCESSED,
    EVENT_TELEMETRY_UPDATED,
    EVENT_LOCK_SUCCESS,
    EVENT_GEOFENCE_ALERT
)
from vision.detector import YoloDetector, MockDetector
from vision.tracker import KalmanTracker
from vision.lock_engine import LockEngine
from vision.visualizer import HUDVisualizer
from referee.client import RefereeClient
from referee.telemetry_sender import TelemetrySenderThread
from autopilot.mavlink_bridge import MavlinkBridge, MockMavlinkBridge
from autopilot.geofence import GeofenceMonitor
from autopilot.guidance import GuidanceController
from simulation.virtual_camera import VirtualCameraFeed


class AeroCombatSystem:
    """TEKNOFEST Savaşan İHA Tümleşik Otonom Sistem Yöneticisi."""

    def __init__(self, config_path: str = "config/default_config.yaml", use_mock_server: bool = True):
        self.config = self._load_config(config_path)
        self.use_mock_server = use_mock_server
        self.is_running = False

        # Alt Bileşenler
        self.autopilot = None
        self.detector = None
        self.tracker = None
        self.lock_engine = None
        self.visualizer = None
        self.geofence = None
        self.guidance = None
        self.referee_client = None
        self.telemetry_sender = None
        self.virtual_camera = None

        self._init_subsystems()
        self._setup_events()

    def _load_config(self, path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            logger.warning(f"Konfigürasyon dosyası bulunamadı ({path}), varsayılanlar kullanılıyor.")
            return {}
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _init_subsystems(self):
        gen_cfg = self.config.get("general", {})
        cam_cfg = self.config.get("kamera", {})
        det_cfg = self.config.get("tespit_ve_takip", {})
        lck_cfg = self.config.get("kilitlenme", {})
        ref_cfg = self.config.get("hakem_sunucusu", {})
        auto_cfg = self.config.get("otopilot", {})
        geo_cfg = self.config.get("geofence", {})

        takim_no = gen_cfg.get("takim_numarasi", 1)

        # 1. Geofence & Güvenlik
        sinirlar = geo_cfg.get("sinir_noktalari", [])
        self.geofence = GeofenceMonitor(
            polygon_coords=sinirlar,
            min_alt_m=geo_cfg.get("min_irtifa_m", 30.0),
            max_alt_m=geo_cfg.get("maks_irtifa_m", 150.0),
            warning_dist_m=geo_cfg.get("uyari_mesafesi_m", 25.0)
        )

        # 2. Otopilot Köprüsü
        if auto_cfg.get("simulasyon", True):
            self.autopilot = MockMavlinkBridge(takim_no=takim_no)
        else:
            self.autopilot = MavlinkBridge(
                connection_string=auto_cfg.get("baglanti_dizgesi", "tcp:127.0.0.1:5760"),
                baud=auto_cfg.get("baud_rate", 115200),
                takim_no=takim_no
            )

        # 3. Güdüm ve Takip Kontrolcüsü
        self.guidance = GuidanceController(method="visual_servoing")

        # 4. Görüntü İşleme: Tespit & Takip
        if det_cfg.get("simulasyon_modu", False) or not os.path.exists(det_cfg.get("model_yolu", "")):
            self.detector = MockDetector()
        else:
            self.detector = YoloDetector(
                model_path=det_cfg.get("model_yolu", ""),
                conf_thresh=det_cfg.get("guven_esigi", 0.45),
                iou_thresh=det_cfg.get("iou_esigi", 0.45),
                device=det_cfg.get("cihaz", "cpu")
            )

        self.tracker = KalmanTracker()

        # 5. Kilitlenme Motoru
        self.lock_engine = LockEngine(
            gerekli_sure_sn=lck_cfg.get("gerekli_sure_sn", 4.0),
            hedef_alan_orani_min=lck_cfg.get("hedef_alan_orani_min", 0.05),
            merkez_tolerans_orani=lck_cfg.get("merkez_tolerans_orani", 0.35),
            kayip_toleransi_sn=lck_cfg.get("kayip_toleransi_sn", 0.35),
            kanit_dizini=gen_cfg.get("kanit_dizini", "proofs"),
            kanit_fps=lck_cfg.get("kanit_fps", 20)
        )

        # 6. HUD Görselleştirici
        self.visualizer = HUDVisualizer()

        # 7. Hakem Sunucusu İstemcisi
        server_url = ref_cfg.get("url", "http://127.0.0.1:8000")
        self.referee_client = RefereeClient(
            base_url=server_url,
            username=ref_cfg.get("kullanici_adi", f"takim{takim_no}"),
            password=ref_cfg.get("sifre", "sifre123"),
            timeout=ref_cfg.get("zaman_asimi_sn", 1.5)
        )

        # 8. Periyodik Telemetri Gönderici Thread
        def telemetry_provider():
            target_cx, target_cy, target_w, target_h = 0, 0, 0, 0
            is_locked = 1 if self.lock_engine.durum == KilitDurumu.LOCKED else 0
            if self.lock_engine.aktif_hedef is not None:
                h = self.lock_engine.aktif_hedef
                target_cx = int(h.merkez_x)
                target_cy = int(h.merkez_y)
                target_w = int(h.genislik)
                target_h = int(h.yukseklik)

            packet = self.autopilot.get_telemetry_packet(
                target_center_x=target_cx,
                target_center_y=target_cy,
                target_w=target_w,
                target_h=target_h,
                is_locked=is_locked
            )
            # Geofence güvenlik doğrulamasını kontrol et
            is_safe, msg = self.geofence.validate_position(packet.IHA_enlem, packet.IHA_boylam, packet.IHA_irtifa)
            if not is_safe:
                logger.warning(f"UYARI: {msg}")

            bus.emit(EVENT_TELEMETRY_UPDATED, telemetri=packet)
            return packet

        self.telemetry_sender = TelemetrySenderThread(
            client=self.referee_client,
            frequency_hz=ref_cfg.get("telemetri_frekansi_hz", 3.0),
            telemetry_provider=telemetry_provider
        )

        # 9. Sentetik Kamera
        self.virtual_camera = VirtualCameraFeed(
            width=cam_cfg.get("genislik", 1280),
            height=cam_cfg.get("yukseklik", 720)
        )

    def _setup_events(self):
        """Olay dinleyicileri (Kilitlenme tamamlandığında sunucuya otomatik bildir vb.)"""
        def on_lock_success(paket, kanit_yolu, **kwargs):
            logger.info(f"Olay Yakalandı: Kilit Başarılı -> Kanıt: {kanit_yolu}")
            # Hakem sunucusuna kilitlenme paketini anında gönder
            threading.Thread(
                target=self.referee_client.kilitlenme_bilgisi_gonder,
                args=(paket,),
                daemon=True
            ).start()

        bus.subscribe(EVENT_LOCK_SUCCESS, on_lock_success)

    def _start_mock_server_if_needed(self):
        """Yerel test için Mock Hakem Sunucusunu arka planda ayağa kaldırır."""
        if self.use_mock_server:
            def run_server():
                try:
                    import uvicorn
                    from mock_server.app import app as mock_app
                    logger.info("Mock Hakem Sunucusu 127.0.0.1:8000 adresinde başlatılıyor...")
                    uvicorn.run(mock_app, host="127.0.0.1", port=8000, log_level="warning")
                except Exception as e:
                    logger.warning(f"Mock sunucu başlatılamadı: {e}")

            server_thread = threading.Thread(target=run_server, daemon=True, name="MockServerThread")
            server_thread.start()
            time.sleep(1.0)  # Sunucunun dinlemeye geçmesini bekle

    def start(self, use_gui: bool = True):
        """Tüm sistemi başlatır."""
        logger.info("==========================================================")
        logger.info("   AeroCombat TEKNOFEST Savaşan İHA Sistemi Başlatılıyor  ")
        logger.info("==========================================================")

        self.is_running = True

        # 1. Mock sunucu gerekiyorsa başlat
        self._start_mock_server_if_needed()

        # 2. Otopilot bağlantısını başlat
        self.autopilot.start()

        # 3. Telemetri gönderici iş parçacığını başlat
        self.telemetry_sender.start_loop()

        # 4. Görüntü İşleme Döngüsünü başlat
        if use_gui:
            # Görüntü işleme iş parçacığını arka planda çalıştır, ana thread PyQt'de kalsın
            vision_thread = threading.Thread(target=self._vision_loop, daemon=True, name="VisionLoopThread")
            vision_thread.start()

            # PyQt6 GCS Başlat
            try:
                from gcs.app import launch_gcs
                launch_gcs(system_controller=self)
            except Exception as e:
                logger.error(f"GCS Arayüz hatası: {e}. OpenCV pencere moduna geçiliyor.")
                self._run_opencv_window()
        else:
            self._run_opencv_window()

    def _vision_loop(self):
        """Kare yakalama, tespit, takip, kilitlenme ve HUD çizim ana döngüsü."""
        t_prev = time.time()
        fps = 30.0

        while self.is_running:
            t_now = time.time()
            dt = t_now - t_prev
            fps = 1.0 / max(1e-4, dt)
            t_prev = t_now

            # Kareyi al (Sanal veya gerçek kamera)
            frame = self.virtual_camera.get_frame()

            # 1. Hedef Tespiti
            detections = self.detector.detect(frame)

            # 2. Çoklu Hedef Takibi (Kalman Filter / ByteTrack)
            tracked_boxes = self.tracker.update(detections)

            # 3. Kilitlenme Durum Makinesi
            server_offset = self.referee_client.time_sync.offset_ms
            durum, sure, aktif_hedef = self.lock_engine.update(
                frame=frame,
                hedefler=tracked_boxes,
                server_offset_ms=server_offset
            )

            # 4. HUD Çizimi
            current_tel = self.autopilot.get_telemetry_packet(is_locked=(1 if durum == KilitDurumu.LOCKED else 0))
            hud_frame = self.visualizer.draw_hud(
                frame=frame,
                boxes=tracked_boxes,
                lock_status=durum,
                lock_duration=sure,
                target_box=aktif_hedef,
                telemetry=current_tel,
                fps=fps
            )

            # 5. EventBus üzerinden kareyi yayınla (GCS GUI için)
            bus.emit(
                EVENT_FRAME_PROCESSED,
                frame=hud_frame,
                durum=durum,
                sure=sure,
                hedef=aktif_hedef,
                fps=fps
            )

            time.sleep(max(0.001, 0.033 - (time.time() - t_now)))

    def _run_opencv_window(self):
        """PyQt olmadığı durumlarda yüksek performanslı OpenCV pencere döngüsü."""
        logger.info("OpenCV HUD Görselleştirme Penceresi Açılıyor (Çıkmak için 'q' tuşuna basın)...")
        cv2.namedWindow("AeroCombat HUD - TEKNOFEST Savasan IHA", cv2.WINDOW_NORMAL)

        def frame_listener(frame, **kwargs):
            self._latest_hud_frame = frame

        self._latest_hud_frame = None
        bus.subscribe(EVENT_FRAME_PROCESSED, frame_listener)

        # Vision döngüsünü arka planda başlat
        vision_thread = threading.Thread(target=self._vision_loop, daemon=True)
        vision_thread.start()

        while self.is_running:
            if self._latest_hud_frame is not None:
                cv2.imshow("AeroCombat HUD - TEKNOFEST Savasan IHA", self._latest_hud_frame)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:
                logger.info("Kullanıcı çıkış isteği gönderdi.")
                break
            elif key == ord('r'):
                logger.info("Kilit sıfırlandı.")
                self.lock_engine.reset()

        cv2.destroyAllWindows()
        self.stop()

    def stop(self):
        """Sistemi güvenli bir şekilde kapatır."""
        self.is_running = False
        if self.telemetry_sender:
            self.telemetry_sender.stop_loop()
        if self.autopilot:
            self.autopilot.stop()
        logger.info("AeroCombat sistemi güvenle kapatıldı.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TEKNOFEST Savaşan İHA Otonom Görev Sistemi")
    parser.add_argument("--config", type=str, default="config/default_config.yaml", help="Konfigürasyon dosyası")
    parser.add_argument("--no-gui", action="store_true", help="PyQt arayüzü yerine OpenCV penceresi çalıştır")
    parser.add_argument("--no-mock-server", action="store_true", help="Dahili mock hakem sunucusunu başlatma")
    args = parser.parse_args()

    app = AeroCombatSystem(
        config_path=args.config,
        use_mock_server=not args.no_mock_server
    )
    app.start(use_gui=not args.no_gui)
