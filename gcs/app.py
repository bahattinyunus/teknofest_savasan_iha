import sys
import os
import time
from typing import Optional, List
import cv2
import numpy as np

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QProgressBar, QGroupBox, QGridLayout,
        QTableWidget, QTableWidgetItem, QHeaderView
    )
    from PyQt6.QtCore import QTimer, Qt
    from PyQt6.QtGui import QImage, QPixmap, QFont
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

from core.models import TelemetriPaketi, RakipIHABilgisi, KilitDurumu
from core.logger import logger
from core.event_bus import (
    bus,
    EVENT_FRAME_PROCESSED,
    EVENT_TELEMETRY_UPDATED,
    EVENT_RIVALS_UPDATED,
    EVENT_SERVER_STATUS,
    EVENT_LOCK_SUCCESS
)


class GCSMainWindow(QMainWindow if PYQT_AVAILABLE else object):
    """TEKNOFEST Savaşan İHA Yer Kontrol İstasyonu (YKİ) Ana Ekranı."""

    def __init__(self, system_controller=None):
        if not PYQT_AVAILABLE:
            raise RuntimeError("PyQt6 kütüphanesi yüklü değil! 'pip install PyQt6' çalıştırın.")
            
        super().__init__()
        self.system = system_controller
        self.setWindowTitle("AeroCombat - TEKNOFEST Savaşan İHA Yer Kontrol İstasyonu")
        self.resize(1400, 850)
        self.setStyleSheet("""
            QMainWindow { background-color: #0d1117; color: #c9d1d9; }
            QGroupBox { border: 1px solid #30363d; border-radius: 6px; margin-top: 10px; font-weight: bold; color: #58a6ff; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
            QLabel { color: #c9d1d9; font-size: 13px; }
            QPushButton { background-color: #21262d; border: 1px solid #30363d; border-radius: 6px; color: #c9d1d9; padding: 8px 16px; font-weight: bold; }
            QPushButton:hover { background-color: #30363d; border-color: #8b949e; }
            QProgressBar { border: 1px solid #30363d; border-radius: 4px; text-align: center; color: white; background-color: #161b22; }
            QProgressBar::chunk { background-color: #238636; border-radius: 4px; }
            QTableWidget { background-color: #161b22; gridline-color: #30363d; border: 1px solid #30363d; color: #c9d1d9; }
            QHeaderView::section { background-color: #0d1117; color: #8b949e; padding: 4px; border: 1px solid #30363d; }
        """)

        self.last_frame: Optional[np.ndarray] = None
        self.kilit_sayisi = 0

        self._init_ui()
        self._setup_event_listeners()

        # UI Yenileme Zamanlayıcısı (30 FPS)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_ui_tick)
        self.timer.start(33)

    def _init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)

        # ---------------- SOL PANEL: KAMERA & HUD ----------------
        video_group = QGroupBox("CANLI KAMERA AKIŞI & HEDEF KİLİTLENME HUD")
        video_layout = QVBoxLayout(video_group)

        self.lbl_video = QLabel("Kamera Başlatılıyor...")
        self.lbl_video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_video.setMinimumSize(854, 480)
        self.lbl_video.setStyleSheet("background-color: #000000; border: 1px solid #30363d; border-radius: 4px;")
        video_layout.addWidget(self.lbl_video)

        # Kilit Durumu ve İlerleme
        lock_box = QHBoxLayout()
        self.lbl_lock_title = QLabel("KİLİT DURUMU:")
        self.lbl_lock_title.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.lbl_lock_status = QLabel("ARANIYOR (IDLE)")
        self.lbl_lock_status.setFont(QFont("Arial", 12, QFont.Weight.Bold))
        self.lbl_lock_status.setStyleSheet("color: #58a6ff;")

        self.prog_lock = QProgressBar()
        self.prog_lock.setRange(0, 100)
        self.prog_lock.setValue(0)
        self.prog_lock.setFixedHeight(24)

        lock_box.addWidget(self.lbl_lock_title)
        lock_box.addWidget(self.lbl_lock_status)
        lock_box.addWidget(self.prog_lock)
        video_layout.addLayout(lock_box)

        main_layout.addWidget(video_group, stretch=7)

        # ---------------- SAĞ PANEL: TELEMETRİ & KONTROL ----------------
        side_layout = QVBoxLayout()

        # 1. Hakem Sunucusu Durumu
        server_group = QGroupBox("HAKEM SUNUCUSU (MHS) BAĞLANTISI")
        server_layout = QGridLayout(server_group)

        self.lbl_server_conn = QLabel("BAĞLI DEĞİL")
        self.lbl_server_conn.setStyleSheet("color: #f85149; font-weight: bold;")
        self.lbl_server_score = QLabel("0 PUAN")
        self.lbl_server_score.setStyleSheet("color: #3fb950; font-weight: bold; font-size: 15px;")
        self.lbl_server_offset = QLabel("Offset: 0 ms")

        server_layout.addWidget(QLabel("Sunucu Durumu:"), 0, 0)
        server_layout.addWidget(self.lbl_server_conn, 0, 1)
        server_layout.addWidget(QLabel("Toplam Skor:"), 1, 0)
        server_layout.addWidget(self.lbl_server_score, 1, 1)
        server_layout.addWidget(QLabel("Zaman Senkronu:"), 2, 0)
        server_layout.addWidget(self.lbl_server_offset, 2, 1)
        side_layout.addWidget(server_group)

        # 2. Uçuş Telemetrisi
        telem_group = QGroupBox("UÇUŞ TELEMETRİSİ (MAVLINK)")
        telem_layout = QGridLayout(telem_group)

        self.lbl_alt = QLabel("0.0 m")
        self.lbl_spd = QLabel("0.0 m/s")
        self.lbl_yaw = QLabel("000 deg")
        self.lbl_pitch = QLabel("0.0 deg")
        self.lbl_roll = QLabel("0.0 deg")
        self.lbl_mode = QLabel("MANUEL")
        self.prog_battery = QProgressBar()
        self.prog_battery.setValue(100)

        telem_layout.addWidget(QLabel("İrtifa:"), 0, 0)
        telem_layout.addWidget(self.lbl_alt, 0, 1)
        telem_layout.addWidget(QLabel("Hız:"), 0, 2)
        telem_layout.addWidget(self.lbl_spd, 0, 3)

        telem_layout.addWidget(QLabel("Yönelim (Yaw):"), 1, 0)
        telem_layout.addWidget(self.lbl_yaw, 1, 1)
        telem_layout.addWidget(QLabel("Uçuş Modu:"), 1, 2)
        telem_layout.addWidget(self.lbl_mode, 1, 3)

        telem_layout.addWidget(QLabel("Dikilme / Yatış:"), 2, 0)
        telem_layout.addWidget(self.lbl_pitch, 2, 1)
        telem_layout.addWidget(self.lbl_roll, 2, 2)

        telem_layout.addWidget(QLabel("Batarya:"), 3, 0)
        telem_layout.addWidget(self.prog_battery, 3, 1, 1, 3)
        side_layout.addWidget(telem_group)

        # 3. Rakip İHA Konumları
        rivals_group = QGroupBox("RADAR / RAKİP İHALAR (MHS)")
        rivals_layout = QVBoxLayout(rivals_group)
        self.table_rivals = QTableWidget(0, 4)
        self.table_rivals.setHorizontalHeaderLabels(["Takım", "İrtifa", "Yönelim", "Gecikme"])
        self.table_rivals.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_rivals.setFixedHeight(140)
        rivals_layout.addWidget(self.table_rivals)
        side_layout.addWidget(rivals_group)

        # 4. Acil Durum & Kontrol Butonları
        btn_group = QGroupBox("GÖREV KONTROLÜ")
        btn_layout = QGridLayout(btn_group)

        btn_rtl = QPushButton("ACİL RTL (EVE DÖN)")
        btn_rtl.setStyleSheet("background-color: #da3633; color: white;")
        btn_rtl.clicked.connect(self._on_emergency_rtl)

        btn_mode_toggle = QPushButton("OTONOM / MANUEL GEÇİŞ")
        btn_mode_toggle.clicked.connect(self._on_mode_toggle)

        btn_reset_lock = QPushButton("KİLİDİ SIFIRLA")
        btn_reset_lock.clicked.connect(self._on_reset_lock)

        btn_proof_dir = QPushButton("KANIT KLASÖRÜNÜ AÇ")
        btn_proof_dir.clicked.connect(self._on_open_proofs)

        btn_layout.addWidget(btn_rtl, 0, 0)
        btn_layout.addWidget(btn_mode_toggle, 0, 1)
        btn_layout.addWidget(btn_reset_lock, 1, 0)
        btn_layout.addWidget(btn_proof_dir, 1, 1)
        side_layout.addWidget(btn_group)

        main_layout.addLayout(side_layout, stretch=3)

    def _setup_event_listeners(self):
        """EventBus üzerinden arka plan olaylarını dinler."""
        bus.subscribe(EVENT_FRAME_PROCESSED, self._on_frame_received)
        bus.subscribe(EVENT_TELEMETRY_UPDATED, self._on_telemetry_updated)
        bus.subscribe(EVENT_RIVALS_UPDATED, self._on_rivals_updated)
        bus.subscribe(EVENT_SERVER_STATUS, self._on_server_status)
        bus.subscribe(EVENT_LOCK_SUCCESS, self._on_lock_success)

    def _on_frame_received(self, frame: np.ndarray, durum: KilitDurumu, sure: float, **kwargs):
        self.last_frame = frame
        self._current_lock_durum = durum
        self._current_lock_sure = sure

    def _on_telemetry_updated(self, telemetri: TelemetriPaketi, **kwargs):
        self.lbl_alt.setText(f"{telemetri.IHA_irtifa:.1f} m")
        self.lbl_spd.setText(f"{telemetri.IHA_hiz:.1f} m/s")
        self.lbl_yaw.setText(f"{int(telemetri.IHA_yonelme):03d} deg")
        self.lbl_pitch.setText(f"P:{telemetri.IHA_dikilme:.1f}")
        self.lbl_roll.setText(f"R:{telemetri.IHA_yatis:.1f}")
        self.lbl_mode.setText("OTONOM" if telemetri.IHA_otonom else "MANUEL")
        self.prog_battery.setValue(telemetri.IHA_batarya)

    def _on_rivals_updated(self, rakipler: List[RakipIHABilgisi], **kwargs):
        self.table_rivals.setRowCount(len(rakipler))
        for row, r in enumerate(rakipler):
            self.table_rivals.setItem(row, 0, QTableWidgetItem(f"Takım {r.takim_numarasi}"))
            self.table_rivals.setItem(row, 1, QTableWidgetItem(f"{r.IHA_irtifa:.1f}m"))
            self.table_rivals.setItem(row, 2, QTableWidgetItem(f"{int(r.IHA_yonelme)}°"))
            self.table_rivals.setItem(row, 3, QTableWidgetItem(f"{r.zaman_farki}ms"))

    def _on_server_status(self, bagli: bool, logged_in: bool, **kwargs):
        if bagli and logged_in:
            self.lbl_server_conn.setText("BAĞLI & OTURUM AÇIK")
            self.lbl_server_conn.setStyleSheet("color: #3fb950; font-weight: bold;")
        elif bagli:
            self.lbl_server_conn.setText("BAĞLANDI (GİRİŞ BEKLENİYOR)")
            self.lbl_server_conn.setStyleSheet("color: #d29922; font-weight: bold;")
        else:
            self.lbl_server_conn.setText("BAĞLANTI KOPUK")
            self.lbl_server_conn.setStyleSheet("color: #f85149; font-weight: bold;")

    def _on_lock_success(self, **kwargs):
        self.kilit_sayisi += 1
        self.lbl_server_score.setText(f"{self.kilit_sayisi * 100} PUAN (+{self.kilit_sayisi})")

    def _update_ui_tick(self):
        """Her karede video görüntüsünü PyQt QLabel'a basar."""
        if self.last_frame is not None:
            # OpenCV BGR -> QImage RGB
            rgb_frame = cv2.cvtColor(self.last_frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_frame.shape
            bytes_per_line = ch * w
            q_img = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(q_img).scaled(
                self.lbl_video.width(),
                self.lbl_video.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.lbl_video.setPixmap(pixmap)

        if hasattr(self, "_current_lock_durum"):
            self.lbl_lock_status.setText(self._current_lock_durum.value)
            pct = min(100, int((getattr(self, "_current_lock_sure", 0.0) / 4.0) * 100))
            self.prog_lock.setValue(pct)
            if self._current_lock_durum == KilitDurumu.LOCKED:
                self.lbl_lock_status.setStyleSheet("color: #3fb950; font-weight: bold;")
            elif self._current_lock_durum == KilitDurumu.LOCKING:
                self.lbl_lock_status.setStyleSheet("color: #d29922; font-weight: bold;")
            else:
                self.lbl_lock_status.setStyleSheet("color: #58a6ff; font-weight: bold;")

    def _on_emergency_rtl(self):
        logger.warning("YKİ: ACİL RTL BUTONUNA BASILDI!")
        if self.system and self.system.autopilot:
            self.system.autopilot.set_mode("RTL")

    def _on_mode_toggle(self):
        if self.system and self.system.autopilot:
            current = self.system.autopilot.is_autonomous
            new_mode = "MANUAL" if current else "GUIDED"
            self.system.autopilot.set_mode(new_mode)

    def _on_reset_lock(self):
        if self.system and self.system.lock_engine:
            self.system.lock_engine.reset()

    def _on_open_proofs(self):
        proofs_dir = os.path.abspath("proofs")
        os.makedirs(proofs_dir, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(proofs_dir)
        else:
            os.system(f"xdg-open '{proofs_dir}'")


def launch_gcs(system_controller=None):
    """PyQt6 Yer Kontrol İstasyonunu başlatır."""
    if not PYQT_AVAILABLE:
        logger.error("PyQt6 kurulu olmadığından görsel arayüz başlatılamadı. CLI modu çalıştırılıyor.")
        return
    app = QApplication.instance() or QApplication(sys.argv)
    window = GCSMainWindow(system_controller)
    window.show()
    app.exec()
