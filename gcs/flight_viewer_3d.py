import os
import sys
import math
import time
import argparse
from typing import List, Tuple, Optional
import cv2
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QSlider, QComboBox, QGroupBox, QFrame
    )
    from PyQt6.QtCore import QTimer, Qt, QPointF, QRectF
    from PyQt6.QtGui import (
        QPainter, QColor, QPen, QBrush, QFont, QPolygonF, QLinearGradient
    )
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

from simulation.dogfight_simulator import DogfightSimulator, TargetBehavior


class Native3DFlightCanvas(QWidget if PYQT_AVAILABLE else object):
    """Saf Python (PyQt6 QPainter + NumPy 3D Kamera Projeksiyon Matrisi) ile
    WebGL/JS gerektirmeyen Etkileşimli 3D İt Dalaşı ve WEZ Zarflı Uçuş Sahnesi.
    """

    def __init__(self, parent=None, init_qt: bool = True):
        if PYQT_AVAILABLE and init_qt and QApplication.instance() is not None:
            super().__init__(parent)
            self.setMinimumSize(860, 560)
            self.setMouseTracking(True)
            self._qt_initialized = True
        else:
            self._qt_initialized = False

        self.camera_yaw_deg: float = 38.0
        self.camera_pitch_deg: float = 24.0
        self.camera_distance_m: float = 320.0
        self._last_mouse_pos = None

        self.history: List[dict] = []
        self.current_frame_idx: int = 0
        self.geofence_half_size_m: float = 220.0

    def load_simulation_history(self, history: List[dict]):
        self.history = history
        self.current_frame_idx = 0
        if getattr(self, "_qt_initialized", False):
            self.update()

    def project_3d_to_2d(self, pt_ned: Tuple[float, float, float], w: float, h: float) -> Optional[Tuple[float, float, float]]:
        """3D NED (North, East, Down) noktasını perspektif kamera düzlemine (x_px, y_px, depth) izdüşürür."""
        # Sahne merkezini aktif kilit/uçuş merkezine hizala
        x = float(pt_ned[1])          # East -> X
        y = float(-pt_ned[2] - 75.0)  # Altitude (-Down) -> Y (75m merkezli)
        z = float(pt_ned[0])          # North -> Z

        yaw = math.radians(self.camera_yaw_deg)
        pitch = math.radians(self.camera_pitch_deg)

        # Y ekseni etrafında dönüş (Yaw)
        x1 = x * math.cos(yaw) - z * math.sin(yaw)
        z1 = x * math.sin(yaw) + z * math.cos(yaw)
        y1 = y

        # X ekseni etrafında dönüş (Pitch)
        y2 = y1 * math.cos(pitch) - z1 * math.sin(pitch)
        z2 = y1 * math.sin(pitch) + z1 * math.cos(pitch) + self.camera_distance_m
        x2 = x1

        if z2 <= 5.0:
            return None

        fov_scale = min(w, h) * 0.95
        sx = (w / 2.0) + (x2 / z2) * fov_scale
        sy = (h / 2.0) - (y2 / z2) * fov_scale
        return (sx, sy, z2)

    def render_to_numpy_image(self, width: int = 960, height: int = 540) -> np.ndarray:
        """OpenCV veya başsız (headless) testler için 3D sahneyi BGR NumPy matrisine çizer."""
        img = np.zeros((height, width, 3), dtype=np.uint8)
        img[:, :] = (18, 12, 8)

        # Zemin ızgarası
        grid_step = 40
        for g in range(-200, 201, grid_step):
            p1 = self.project_3d_to_2d((g, -200, 0.0), width, height)
            p2 = self.project_3d_to_2d((g, 200, 0.0), width, height)
            if p1 and p2:
                cv2.line(img, (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])), (45, 35, 25), 1, cv2.LINE_AA)
            p3 = self.project_3d_to_2d((-200, g, 0.0), width, height)
            p4 = self.project_3d_to_2d((200, g, 0.0), width, height)
            if p3 and p4:
                cv2.line(img, (int(p3[0]), int(p3[1])), (int(p4[0]), int(p4[1])), (45, 35, 25), 1, cv2.LINE_AA)

        if not self.history:
            return img

        idx = min(len(self.history) - 1, max(0, self.current_frame_idx))

        # Mavi ve Kırmızı İHA Yörünge Şeritleri
        for k in range(1, idx + 1):
            h_prev = self.history[k - 1]
            h_curr = self.history[k]

            b1 = self.project_3d_to_2d((h_prev["blue_n"], h_prev["blue_e"], -h_prev["blue_alt"]), width, height)
            b2 = self.project_3d_to_2d((h_curr["blue_n"], h_curr["blue_e"], -h_curr["blue_alt"]), width, height)
            if b1 and b2:
                cv2.line(img, (int(b1[0]), int(b1[1])), (int(b2[0]), int(b2[1])), (255, 210, 0), 2, cv2.LINE_AA)

            r1 = self.project_3d_to_2d((h_prev["red_n"], h_prev["red_e"], -h_prev["red_alt"]), width, height)
            r2 = self.project_3d_to_2d((h_curr["red_n"], h_curr["red_e"], -h_curr["red_alt"]), width, height)
            if r1 and r2:
                cv2.line(img, (int(r1[0]), int(r1[1])), (int(r2[0]), int(r2[1])), (70, 70, 255), 2, cv2.LINE_AA)

        cur = self.history[idx]
        pb = self.project_3d_to_2d((cur["blue_n"], cur["blue_e"], -cur["blue_alt"]), width, height)
        pr = self.project_3d_to_2d((cur["red_n"], cur["red_e"], -cur["red_alt"]), width, height)

        if pb and pr:
            line_col = (120, 255, 0) if cur.get("in_wez", False) else (120, 120, 120)
            cv2.line(img, (int(pb[0]), int(pb[1])), (int(pr[0]), int(pr[1])), line_col, 1, cv2.LINE_AA)
            cv2.circle(img, (int(pb[0]), int(pb[1])), 6, (255, 220, 0), -1)
            cv2.circle(img, (int(pr[0]), int(pr[1])), 6, (60, 60, 255), -1)

        cv2.putText(
            img,
            f"PYTHON 3D DOGFIGHT VIEWER | t={cur['time_s']:.1f}s | Dist={cur['distance_m']:.1f}m | Locks={cur['total_locks']}",
            (16, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            (0, 255, 157),
            2,
            cv2.LINE_AA
        )
        return img

    if PYQT_AVAILABLE:
        def mousePressEvent(self, event):
            self._last_mouse_pos = event.position()

        def mouseMoveEvent(self, event):
            if self._last_mouse_pos is not None and (event.buttons() & Qt.MouseButton.LeftButton):
                 pos = event.position()
                 dx = pos.x() - self._last_mouse_pos.x()
                 dy = pos.y() - self._last_mouse_pos.y()
                 self.camera_yaw_deg = (self.camera_yaw_deg + dx * 0.45) % 360.0
                 self.camera_pitch_deg = max(-10.0, min(80.0, self.camera_pitch_deg + dy * 0.35))
                 self._last_mouse_pos = pos
                 self.update()

        def wheelEvent(self, event):
            delta = event.angleDelta().y()
            self.camera_distance_m = max(100.0, min(750.0, self.camera_distance_m - delta * 0.25))
            self.update()

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            w = float(self.width())
            h = float(self.height())

            bg = QLinearGradient(0, 0, 0, h)
            bg.setColorAt(0.0, QColor("#05080f"))
            bg.setColorAt(1.0, QColor("#0d1522"))
            painter.fillRect(self.rect(), bg)

            # 1. 3D Zemin Izgarası ve Geofence Sınır Kutusu
            painter.setPen(QPen(QColor(35, 55, 75, 140), 1.0))
            for g in range(-200, 201, 40):
                p1 = self.project_3d_to_2d((g, -200, 0.0), w, h)
                p2 = self.project_3d_to_2d((g, 200, 0.0), w, h)
                if p1 and p2:
                    painter.drawLine(QPointF(p1[0], p1[1]), QPointF(p2[0], p2[1]))
                p3 = self.project_3d_to_2d((-200, g, 0.0), w, h)
                p4 = self.project_3d_to_2d((200, g, 0.0), w, h)
                if p3 and p4:
                    painter.drawLine(QPointF(p3[0], p3[1]), QPointF(p4[0], p4[1]))

            if not self.history:
                painter.end()
                return

            idx = min(len(self.history) - 1, max(0, self.current_frame_idx))

            # 2. Mavi İHA (Avcı) ve Kırmızı İHA (Hedef) 3D Yörünge İzleri
            pen_blue = QPen(QColor("#00f0ff"), 2.4)
            pen_red = QPen(QColor("#ff4d4d"), 2.2)

            for k in range(1, idx + 1):
                hp = self.history[k - 1]
                hc = self.history[k]

                b1 = self.project_3d_to_2d((hp["blue_n"], hp["blue_e"], -hp["blue_alt"]), w, h)
                b2 = self.project_3d_to_2d((hc["blue_n"], hc["blue_e"], -hc["blue_alt"]), w, h)
                if b1 and b2:
                    painter.setPen(pen_blue)
                    painter.drawLine(QPointF(b1[0], b1[1]), QPointF(b2[0], b2[1]))

                r1 = self.project_3d_to_2d((hp["red_n"], hp["red_e"], -hp["red_alt"]), w, h)
                r2 = self.project_3d_to_2d((hc["red_n"], hc["red_e"], -hc["red_alt"]), w, h)
                if r1 and r2:
                    painter.setPen(pen_red)
                    painter.drawLine(QPointF(r1[0], r1[1]), QPointF(r2[0], r2[1]))

            # 3. Anlık İHA Konumları ve WEZ Kilit Işını
            cur = self.history[idx]
            pb = self.project_3d_to_2d((cur["blue_n"], cur["blue_e"], -cur["blue_alt"]), w, h)
            pr = self.project_3d_to_2d((cur["red_n"], cur["red_e"], -cur["red_alt"]), w, h)

            if pb and pr:
                in_wez = cur.get("in_wez", False)
                los_color = QColor("#00ff9d") if in_wez else QColor(180, 190, 205, 110)
                painter.setPen(QPen(los_color, 2.0 if in_wez else 1.0, Qt.PenStyle.DashLine))
                painter.drawLine(QPointF(pb[0], pb[1]), QPointF(pr[0], pr[1]))

                # Mavi İHA
                painter.setBrush(QBrush(QColor("#00f0ff")))
                painter.setPen(QPen(QColor("#ffffff"), 1.2))
                painter.drawEllipse(QPointF(pb[0], pb[1]), 6.5, 6.5)

                # Kırmızı İHA
                painter.setBrush(QBrush(QColor("#ff4d4d")))
                painter.drawEllipse(QPointF(pr[0], pr[1]), 6.5, 6.5)

                painter.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
                painter.setPen(QColor("#00f0ff"))
                painter.drawText(QPointF(pb[0] + 9, pb[1] - 6), f"MAVİ ({cur['blue_alt']:.0f}m)")
                painter.setPen(QColor("#ff8080"))
                painter.drawText(QPointF(pr[0] + 9, pr[1] - 6), f"HEDEF ({cur['red_alt']:.0f}m)")

            # 4. Sol Üst Taktik Telemetri Overlay
            painter.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            painter.setPen(QColor("#00ff9d"))
            painter.drawText(
                QPointF(16, 24),
                f"PYTHON 3D FLIGHT ARENA | Zaman: {cur['time_s']:.2f}s | Mesafe: {cur['distance_m']:.1f}m | ATA: {cur['ata_deg']:.1f}°"
            )
            painter.setPen(QColor("#ffb000"))
            painter.drawText(
                QPointF(16, 44),
                f"Kilit Sayacı: {cur['lock_timer_s']:.2f}s / 4.00s | Onaylanan Kilit: {cur['total_locks']} (+{cur['total_locks']*100} Puan)"
            )
            painter.setPen(QColor("#8b949e"))
            painter.drawText(
                QPointF(16, h - 14),
                "Fare Sol Tuş: 3D Kamera Döndür (Yaw/Pitch) | Fare Tekerleği: Yakınlaştır/Uzaklaştır"
            )
            painter.end()


def generate_dogfight_trajectory(behavior: TargetBehavior = TargetBehavior.WEAVE, duration_s: float = 25.0, dt: float = 0.05) -> List[dict]:
    """DogfightSimulator üzerinden 3D oynatıcı için zenginleştirilmiş yörünge geçmişi üretir."""
    sim = DogfightSimulator(dt=dt)
    sim.red_behavior = behavior
    steps = int(duration_s / dt)
    records = []

    for k in range(steps):
        snap = sim.step()
        dx = snap.red_state.x - snap.blue_state.x
        dy = snap.red_state.y - snap.blue_state.y
        dz = snap.red_state.z - snap.blue_state.z
        dist = max(0.1, snap.distance_m)
        ata_deg = 12.0 if snap.target_in_fov else 45.0
        in_wez = snap.target_in_fov and (15.0 <= dist <= 110.0)

        records.append({
            "step": k,
            "time_s": round(snap.sim_time, 2),
            "blue_n": snap.blue_state.x,
            "blue_e": snap.blue_state.y,
            "blue_alt": snap.blue_state.z,
            "red_n": snap.red_state.x,
            "red_e": snap.red_state.y,
            "red_alt": snap.red_state.z,
            "distance_m": round(dist, 2),
            "ata_deg": round(ata_deg, 1),
            "in_wez": in_wez,
            "lock_timer_s": round(snap.lock_progress * 4.0, 2),
            "total_locks": snap.successful_locks
        })
    return records


class FlightViewer3DWindow(QMainWindow if PYQT_AVAILABLE else object):
    """Saf Python PyQt6 3D İt Dalaşı Oynatıcı Penceresi."""

    def __init__(self, initial_behavior: TargetBehavior = TargetBehavior.WEAVE):
        if not PYQT_AVAILABLE:
            raise RuntimeError("PyQt6 kütüphanesi yüklü değil!")
        super().__init__()
        self.setWindowTitle("AeroCombat Native Python 3D İt Dalaşı Stüdyosu (PyQt6 3D Arena)")
        self.resize(1240, 760)
        self.setStyleSheet("""
            QMainWindow { background-color: #070a0f; color: #c9d1d9; }
            QPushButton { background-color: #161b22; border: 1px solid #30363d; border-radius: 5px; color: #c9d1d9; padding: 6px 14px; font-weight: bold; }
            QPushButton:hover { background-color: #1f6feb; color: white; }
            QComboBox { background-color: #161b22; border: 1px solid #30363d; color: #00f0ff; padding: 5px; font-weight: bold; }
            QLabel { color: #c9d1d9; font-family: 'Consolas'; font-weight: bold; }
        """)

        central = QWidget()
        self.setCentralWidget(central)
        vbox = QVBoxLayout(central)

        self.canvas_3d = Native3DFlightCanvas()
        vbox.addWidget(self.canvas_3d, stretch=1)

        ctrl_bar = QHBoxLayout()
        self.btn_play = QPushButton("⏸ DURAKLAT")
        self.btn_play.clicked.connect(self._toggle_play)

        self.combo_behavior = QComboBox()
        for b in TargetBehavior:
            self.combo_behavior.addItem(f"Rakip Taktik: {b.value}", b)
        self.combo_behavior.currentIndexChanged.connect(self._on_behavior_changed)

        self.slider_timeline = QSlider(Qt.Orientation.Horizontal)
        self.slider_timeline.valueChanged.connect(self._on_slider_moved)

        ctrl_bar.addWidget(self.btn_play)
        ctrl_bar.addWidget(self.combo_behavior)
        ctrl_bar.addWidget(QLabel("Zaman Çizelgesi:"))
        ctrl_bar.addWidget(self.slider_timeline, stretch=1)
        vbox.addLayout(ctrl_bar)

        self.is_playing = True
        self._load_scenario(initial_behavior)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(35)

    def _load_scenario(self, behavior: TargetBehavior):
        traj = generate_dogfight_trajectory(behavior=behavior, duration_s=25.0)
        self.canvas_3d.load_simulation_history(traj)
        self.slider_timeline.setRange(0, max(0, len(traj) - 1))
        self.slider_timeline.setValue(0)

    def _toggle_play(self):
        self.is_playing = not self.is_playing
        self.btn_play.setText("⏸ DURAKLAT" if self.is_playing else "▶ OYNAT")

    def _on_behavior_changed(self, idx: int):
        beh = self.combo_behavior.currentData()
        if beh is not None:
            self._load_scenario(beh)

    def _on_slider_moved(self, val: int):
        self.canvas_3d.current_frame_idx = val
        self.canvas_3d.update()

    def _tick(self):
        if self.is_playing and self.canvas_3d.history:
            nxt = (self.canvas_3d.current_frame_idx + 1) % len(self.canvas_3d.history)
            self.slider_timeline.setValue(nxt)


def launch_3d_viewer():
    app = QApplication.instance() or QApplication(sys.argv)
    win = FlightViewer3DWindow()
    win.show()
    app.exec()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AeroCombat Native Python 3D İt Dalaşı Stüdyosu")
    parser.add_argument("--headless-snapshot", type=str, default="", help="Başsız modda 3D sahneyi PNG olarak kaydet")
    args = parser.parse_args()

    if args.headless_snapshot:
        traj = generate_dogfight_trajectory(TargetBehavior.WEAVE, duration_s=20.0)
        canvas = Native3DFlightCanvas()
        canvas.load_simulation_history(traj)
        canvas.current_frame_idx = len(traj) // 2
        img = canvas.render_to_numpy_image(1280, 720)
        cv2.imwrite(args.headless_snapshot, img)
        print(f"Python 3D sahne goruntusu kaydedildi: {args.headless_snapshot}")
    else:
        launch_3d_viewer()
