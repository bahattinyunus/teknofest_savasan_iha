import os
import sys
import math
import time
from typing import Optional, List, Dict, Tuple, Any
import cv2
import numpy as np

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QProgressBar, QGroupBox, QGridLayout,
        QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget,
        QPlainTextEdit, QFrame, QSplitter, QSizePolicy
    )
    from PyQt6.QtCore import QTimer, Qt, QRectF, QPointF
    from PyQt6.QtGui import (
        QImage, QPixmap, QFont, QPainter, QColor, QPen, QBrush,
        QLinearGradient, QPolygonF, QRadialGradient
    )
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False

from core.models import (
    TelemetriPaketi, RakipIHABilgisi, KilitDurumu,
    EnergyState, EWStatus, EWAlertLevel
)
from core.logger import logger
from core.event_bus import (
    bus,
    EVENT_FRAME_PROCESSED,
    EVENT_TELEMETRY_UPDATED,
    EVENT_RIVALS_UPDATED,
    EVENT_SERVER_STATUS,
    EVENT_LOCK_STARTED,
    EVENT_LOCK_PROGRESS,
    EVENT_LOCK_SUCCESS,
    EVENT_LOCK_LOST,
    EVENT_GEOFENCE_ALERT,
    EVENT_EW_ALERT,
    EVENT_ENERGY_STATE_UPDATED,
    EVENT_RWR_ALERT,
    EVENT_TACTICAL_MANEUVER
)


if PYQT_AVAILABLE:
    class PrimaryFlightDisplayWidget(QWidget):
        """Native Python PyQt6 Askeri Primary Flight Display (PFD) & Yapay Ufuk Göstergesi."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setMinimumSize(250, 210)
            self.roll_deg: float = 0.0
            self.pitch_deg: float = 0.0
            self.yaw_deg: float = 0.0
            self.airspeed_mps: float = 22.0
            self.altitude_m: float = 80.0
            self.g_load: float = 1.0
            self.stall_warning: bool = False

        def set_flight_state(
            self,
            roll_deg: float,
            pitch_deg: float,
            yaw_deg: float,
            airspeed_mps: float,
            altitude_m: float,
            g_load: float = 1.0,
            stall_warning: bool = False
        ):
            self.roll_deg = float(roll_deg)
            self.pitch_deg = float(pitch_deg)
            self.yaw_deg = float(yaw_deg)
            self.airspeed_mps = float(airspeed_mps)
            self.altitude_m = float(altitude_m)
            self.g_load = float(g_load)
            self.stall_warning = bool(stall_warning)
            self.update()

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            w = float(self.width())
            h = float(self.height())
            cx, cy = w / 2.0, h / 2.0
            radius = min(w, h) * 0.40

            # Arka plan paneli
            painter.fillRect(self.rect(), QColor("#090d14"))

            # Yapay Ufuk Dairesel Maske Alanı
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(-self.roll_deg)

            pitch_px = (self.pitch_deg / 45.0) * radius

            # Gökyüzü ve Yeryüzü
            sky_grad = QLinearGradient(0, -radius * 1.5, 0, pitch_px)
            sky_grad.setColorAt(0.0, QColor("#0c2d57"))
            sky_grad.setColorAt(1.0, QColor("#1e56a0"))
            painter.fillRect(QRectF(-radius * 1.4, -radius * 1.5, radius * 2.8, radius * 1.5 + pitch_px), sky_grad)

            ground_grad = QLinearGradient(0, pitch_px, 0, radius * 1.5)
            ground_grad.setColorAt(0.0, QColor("#5c3d1e"))
            ground_grad.setColorAt(1.0, QColor("#291a0c"))
            painter.fillRect(QRectF(-radius * 1.4, pitch_px, radius * 2.8, radius * 1.5 - pitch_px), ground_grad)

            # Ufuk çizgisi
            painter.setPen(QPen(QColor("#00ff9d"), 2.0))
            painter.drawLine(QPointF(-radius * 1.1, pitch_px), QPointF(radius * 1.1, pitch_px))

            # Pitch merdiveni (-30 .. +30 derece)
            painter.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
            for deg in (-20, -10, 10, 20):
                y_pos = pitch_px - (deg / 45.0) * radius
                if abs(y_pos) < radius * 0.85:
                    half_w = 24.0 if abs(deg) == 20 else 16.0
                    painter.drawLine(QPointF(-half_w, y_pos), QPointF(-6.0, y_pos))
                    painter.drawLine(QPointF(6.0, y_pos), QPointF(half_w, y_pos))
                    painter.drawText(QPointF(half_w + 4.0, y_pos + 3.0), f"{deg}")

            painter.restore()

            # Sabit uçak referans sembolü (Waterline W)
            painter.setPen(QPen(QColor("#ffb000"), 2.5))
            painter.drawLine(QPointF(cx - 28, cy), QPointF(cx - 10, cy))
            painter.drawLine(QPointF(cx - 10, cy), QPointF(cx - 5, cy + 6))
            painter.drawLine(QPointF(cx + 28, cy), QPointF(cx + 10, cy))
            painter.drawLine(QPointF(cx + 10, cy), QPointF(cx + 5, cy + 6))
            painter.drawEllipse(QPointF(cx, cy), 2.5, 2.5)

            # Sol Hız Şeridi (Airspeed Tape) & Sağ İrtifa Şeridi (Altitude Tape)
            tape_w = 46.0
            painter.fillRect(QRectF(4.0, 12.0, tape_w, h - 24.0), QColor(13, 20, 30, 210))
            painter.fillRect(QRectF(w - tape_w - 4.0, 12.0, tape_w, h - 24.0), QColor(13, 20, 30, 210))
            painter.setPen(QPen(QColor("#30363d"), 1.0))
            painter.drawRect(QRectF(4.0, 12.0, tape_w, h - 24.0))
            painter.drawRect(QRectF(w - tape_w - 4.0, 12.0, tape_w, h - 24.0))

            # Hız & İrtifa Kutuları
            painter.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
            painter.setPen(QColor("#00f0ff"))
            painter.drawText(QRectF(6.0, 16.0, tape_w - 4, 18.0), Qt.AlignmentFlag.AlignCenter, "SPD")
            painter.drawText(QRectF(w - tape_w - 2.0, 16.0, tape_w - 4, 18.0), Qt.AlignmentFlag.AlignCenter, "ALT")

            painter.setPen(QColor("#00ff9d"))
            painter.drawText(QRectF(6.0, cy - 10.0, tape_w - 4, 20.0), Qt.AlignmentFlag.AlignCenter, f"{self.airspeed_mps:.1f}")
            painter.drawText(QRectF(w - tape_w - 2.0, cy - 10.0, tape_w - 4, 20.0), Qt.AlignmentFlag.AlignCenter, f"{self.altitude_m:.0f}m")

            # Üst Pusula Şeridi & Alt G-Yükü / Yatış Bilgisi
            painter.setPen(QColor("#58a6ff"))
            painter.drawText(
                QRectF(cx - 55, 6.0, 110, 18.0),
                Qt.AlignmentFlag.AlignCenter,
                f"HDG {int(self.yaw_deg) % 360:03d}°"
            )

            g_color = QColor("#ff4d4d") if self.g_load > 3.5 or self.stall_warning else QColor("#c9d1d9")
            painter.setPen(g_color)
            status_txt = f"{self.g_load:.1f}G  R:{self.roll_deg:+.0f}° P:{self.pitch_deg:+.0f}°"
            if self.stall_warning:
                status_txt = "!! STALL WARNING !! " + status_txt
            painter.drawText(QRectF(55, h - 22.0, w - 110, 18.0), Qt.AlignmentFlag.AlignCenter, status_txt)
            painter.end()


    class LockCountdownRingWidget(QWidget):
        """Native Python PyQt6 4.0 Saniye Kesintisiz Kilitlenme Dairesel Sayacı (%5 Kuralı Göstergeli)."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setMinimumSize(175, 175)
            self.lock_status: KilitDurumu = KilitDurumu.IDLE
            self.lock_duration_s: float = 0.0
            self.required_duration_s: float = 4.0
            self.total_locks: int = 0
            self.target_area_pct: float = 0.0
            self.mppi_lock_prob: float = 0.0

        def set_lock_state(
            self,
            status: KilitDurumu,
            duration_s: float,
            total_locks: int,
            area_pct: float = 0.0,
            mppi_prob: float = 0.0
        ):
            self.lock_status = status
            self.lock_duration_s = max(0.0, float(duration_s))
            self.total_locks = int(total_locks)
            self.target_area_pct = float(area_pct)
            self.mppi_lock_prob = float(mppi_prob)
            self.update()

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            w = float(self.width())
            h = float(self.height())
            cx, cy = w / 2.0, h / 2.0
            r = min(w, h) * 0.37

            painter.fillRect(self.rect(), QColor("#090d14"))

            # Arka plan halkası
            rect = QRectF(cx - r, cy - r - 6, 2 * r, 2 * r)
            painter.setPen(QPen(QColor("#1f2937"), 10.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(rect, 0, 360 * 16)

            # Duruma göre renk
            if self.lock_status == KilitDurumu.LOCKED:
                ring_color = QColor("#00ff9d")
            elif self.lock_status == KilitDurumu.LOCKING:
                ring_color = QColor("#ffb000")
            elif self.lock_status == KilitDurumu.LOST:
                ring_color = QColor("#ff4d4d")
            else:
                ring_color = QColor("#00d2ff")

            progress = min(1.0, self.lock_duration_s / max(0.1, self.required_duration_s))
            if self.lock_status == KilitDurumu.LOCKED:
                progress = 1.0

            span_angle = int(-progress * 360 * 16)
            painter.setPen(QPen(ring_color, 10.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawArc(rect, 90 * 16, span_angle)

            # Merkez süre yazısı
            painter.setFont(QFont("Consolas", 16, QFont.Weight.Bold))
            painter.setPen(ring_color)
            painter.drawText(
                QRectF(cx - r, cy - 26, 2 * r, 28),
                Qt.AlignmentFlag.AlignCenter,
                f"{self.lock_duration_s:.2f}s"
            )

            painter.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
            painter.setPen(QColor("#8b949e"))
            painter.drawText(
                QRectF(cx - r, cy + 4, 2 * r, 16),
                Qt.AlignmentFlag.AlignCenter,
                f"{self.lock_status.value} ({int(progress * 100)}%)"
            )

            # Alt bilgi: Alan %5 kuralı ve MPPI kilit olasılığı
            area_color = QColor("#3fb950") if self.target_area_pct >= 5.0 else QColor("#d29922")
            painter.setPen(area_color)
            painter.drawText(
                QRectF(4, h - 22, w - 8, 18),
                Qt.AlignmentFlag.AlignCenter,
                f"Alan: %{self.target_area_pct:.1f} | Kilit: {self.total_locks} | MPPI: %{int(self.mppi_lock_prob * 100)}"
            )
            painter.end()


    class TacticalRadarScopeWidget(QWidget):
        """Native Python PyQt6 360° Taktik Radar, RWR Tehdit Konisi, Geofence ve MPPI Yörünge Ekranı."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setMinimumSize(250, 220)
            self.own_yaw_deg: float = 0.0
            self.rivals: List[RakipIHABilgisi] = []
            self.rwr_warning: bool = False
            self.sweep_angle_deg: float = 0.0
            self.mppi_path_ned: List[Tuple[float, float, float]] = []
            self.imm_mode_label: str = "CV"

        def tick_sweep(self):
            self.sweep_angle_deg = (self.sweep_angle_deg + 7.0) % 360.0
            self.update()

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            w = float(self.width())
            h = float(self.height())
            cx, cy = w / 2.0, h / 2.0
            r_max = min(w, h) * 0.42

            painter.fillRect(self.rect(), QColor("#060b10"))

            # Menzil halkaları (50m, 100m, 150m)
            painter.setPen(QPen(QColor("#143326"), 1.0, Qt.PenStyle.DashLine))
            for frac in (0.33, 0.66, 1.0):
                rr = r_max * frac
                painter.drawEllipse(QPointF(cx, cy), rr, rr)

            # Eksen çizgileri
            painter.drawLine(QPointF(cx - r_max, cy), QPointF(cx + r_max, cy))
            painter.drawLine(QPointF(cx, cy - r_max), QPointF(cx, cy + r_max))

            # RWR Arka Sektör (6 Saat Yönü) Tehdit Konisi
            if self.rwr_warning:
                painter.setBrush(QBrush(QColor(255, 45, 45, 75)))
                painter.setPen(QPen(QColor("#ff3333"), 1.5))
                painter.drawPie(
                    QRectF(cx - r_max, cy - r_max, 2 * r_max, 2 * r_max),
                    235 * 16,
                    70 * 16
                )

            # WEZ Ön Sektör Kilitlenme Konisi
            painter.setBrush(QBrush(QColor(0, 255, 157, 30)))
            painter.setPen(QPen(QColor(0, 255, 157, 90), 1.0))
            painter.drawPie(
                QRectF(cx - r_max * 0.75, cy - r_max * 0.75, 1.5 * r_max, 1.5 * r_max),
                70 * 16,
                40 * 16
            )

            # Dönen radar tarama çizgisi
            rad_sweep = math.radians(self.sweep_angle_deg)
            sx = cx + r_max * math.sin(rad_sweep)
            sy = cy - r_max * math.cos(rad_sweep)
            painter.setPen(QPen(QColor(0, 255, 157, 130), 1.8))
            painter.drawLine(QPointF(cx, cy), QPointF(sx, sy))

            # MPPI Optimal Planlanan Yörünge İzi
            if len(self.mppi_path_ned) >= 2:
                painter.setPen(QPen(QColor("#00d2ff"), 2.0, Qt.PenStyle.DotLine))
                p0 = self.mppi_path_ned[0]
                prev_pt = QPointF(cx, cy)
                for pt in self.mppi_path_ned[1:10]:
                    dn = pt[0] - p0[0]
                    de = pt[1] - p0[1]
                    px = cx + (de / 120.0) * r_max
                    py = cy - (dn / 120.0) * r_max
                    cur_pt = QPointF(px, py)
                    painter.drawLine(prev_pt, cur_pt)
                    prev_pt = cur_pt

            # Rakip İHA Sembolleri
            painter.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
            if self.rivals:
                for idx, riv in enumerate(self.rivals[:8]):
                    angle = math.radians((riv.takim_numarasi * 67 + self.own_yaw_deg) % 360)
                    dist_norm = 0.35 + 0.45 * ((idx + 1) / max(1, len(self.rivals)))
                    rx = cx + r_max * dist_norm * math.sin(angle)
                    ry = cy - r_max * dist_norm * math.cos(angle)
                    painter.setBrush(QBrush(QColor("#ff4d4d")))
                    painter.setPen(QPen(QColor("#ffffff"), 1.0))
                    painter.drawEllipse(QPointF(rx, ry), 4.5, 4.5)
                    painter.setPen(QColor("#ff8080"))
                    painter.drawText(QPointF(rx + 6, ry + 3), f"T{riv.takim_numarasi}")
            else:
                # Simülasyon aktif hedef bogey gösterimi
                bx = cx + r_max * 0.32 * math.sin(math.radians(self.sweep_angle_deg * 0.25))
                by = cy - r_max * 0.42
                painter.setBrush(QBrush(QColor("#ffb000")))
                painter.setPen(QPen(QColor("#ffffff"), 1.0))
                painter.drawEllipse(QPointF(bx, by), 5.0, 5.0)
                painter.setPen(QColor("#ffb000"))
                painter.drawText(QPointF(bx + 7, by + 3), f"TGT [{self.imm_mode_label}]")

            # Merkez Kendi İHA'mız (Üçgen Sembol)
            own_poly = QPolygonF([
                QPointF(cx, cy - 7),
                QPointF(cx - 5, cy + 6),
                QPointF(cx + 5, cy + 6)
            ])
            painter.setBrush(QBrush(QColor("#00ff9d")))
            painter.setPen(QPen(QColor("#00ff9d"), 1.2))
            painter.drawPolygon(own_poly)

            # Köşe bilgi etiketleri
            painter.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
            painter.setPen(QColor("#00ff9d"))
            painter.drawText(QPointF(8, 15), "ASD RADAR 150m")
            rwr_txt = "RWR: LOCK ALERT" if self.rwr_warning else "RWR: CLEAR"
            painter.setPen(QColor("#ff4d4d") if self.rwr_warning else QColor("#3fb950"))
            painter.drawText(QPointF(w - 108, 15), rwr_txt)
            painter.end()


    class EnergyEnvelopeChartWidget(QWidget):
        """John Boyd Enerji-Manevra (E-M) Özgül Enerji (He) ve Fazla Güç (Ps) Canlı Çizgi Grafiği."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setMinimumSize(240, 125)
            self.he_history: List[float] = [105.0] * 40
            self.ps_history: List[float] = [2.5] * 40
            self.recommended_tactic: str = "RATE_FIGHT_2_CIRCLE"
            self.corner_speed_mps: float = 24.0

        def push_energy_state(self, state: EnergyState):
            self.he_history.append(float(state.ozgurluk_enerjisi_He_m))
            self.ps_history.append(float(state.ozgurluk_fazla_gucu_Ps_mps))
            if len(self.he_history) > 50:
                self.he_history.pop(0)
                self.ps_history.pop(0)
            self.recommended_tactic = state.onerilen_taktik
            self.corner_speed_mps = state.manevra_kose_hizi_Vc_mps
            self.update()

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            w = float(self.width())
            h = float(self.height())
            painter.fillRect(self.rect(), QColor("#090d14"))

            # Izgara
            painter.setPen(QPen(QColor("#1b2430"), 1.0))
            for i in range(1, 4):
                yy = (h / 4.0) * i
                painter.drawLine(QPointF(8, yy), QPointF(w - 8, yy))

            # He Eğrisi (Turkuaz)
            if len(self.he_history) >= 2:
                min_he = min(self.he_history) - 5.0
                max_he = max(self.he_history) + 5.0
                span = max(10.0, max_he - min_he)
                painter.setPen(QPen(QColor("#00d2ff"), 2.0))
                n = len(self.he_history)
                for i in range(1, n):
                    x1 = 10.0 + ((i - 1) / (n - 1)) * (w - 20.0)
                    x2 = 10.0 + (i / (n - 1)) * (w - 20.0)
                    y1 = h - 22.0 - ((self.he_history[i - 1] - min_he) / span) * (h - 44.0)
                    y2 = h - 22.0 - ((self.he_history[i] - min_he) / span) * (h - 44.0)
                    painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

            painter.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
            cur_he = self.he_history[-1] if self.he_history else 0.0
            cur_ps = self.ps_history[-1] if self.ps_history else 0.0
            painter.setPen(QColor("#00d2ff"))
            painter.drawText(QPointF(10, 15), f"BOYD E-M | He:{cur_he:.1f}m  Ps:{cur_ps:+.1f}m/s")
            painter.setPen(QColor("#3fb950"))
            painter.drawText(QPointF(10, h - 7), f"Vc:{self.corner_speed_mps:.1f}m/s | {self.recommended_tactic}")
            painter.end()


class GCSMainWindow(QMainWindow if PYQT_AVAILABLE else object):
    """TEKNOFEST Savaşan İHA Python PyQt6 Taktik Komuta ve Yer Kontrol İstasyonu v4.0."""

    def __init__(self, system_controller=None):
        if not PYQT_AVAILABLE:
            raise RuntimeError("PyQt6 kütüphanesi yüklü değil! 'pip install PyQt6' çalıştırın.")

        super().__init__()
        self.system = system_controller
        self.setWindowTitle("AeroCombat Python Tactical GCS v4.0 - TEKNOFEST Savaşan İHA Komuta Merkezi")
        self.resize(1540, 920)
        self.setStyleSheet("""
            QMainWindow { background-color: #070a0f; color: #d0d7de; }
            QGroupBox {
                background-color: #0d1117;
                border: 1px solid #21262d;
                border-radius: 6px;
                margin-top: 10px;
                font-family: 'Consolas', 'Segoe UI', monospace;
                font-weight: bold;
                font-size: 12px;
                color: #58a6ff;
            }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; }
            QLabel { color: #c9d1d9; font-family: 'Consolas', 'Segoe UI'; font-size: 12px; }
            QPushButton {
                background-color: #161b22;
                border: 1px solid #30363d;
                border-radius: 5px;
                color: #c9d1d9;
                padding: 7px 12px;
                font-family: 'Consolas', 'Segoe UI';
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #21262d; border-color: #58a6ff; color: #ffffff; }
            QPushButton:pressed { background-color: #0d419d; }
            QProgressBar {
                border: 1px solid #30363d;
                border-radius: 4px;
                text-align: center;
                color: #ffffff;
                font-weight: bold;
                background-color: #090d14;
            }
            QProgressBar::chunk { background-color: #238636; border-radius: 3px; }
            QTableWidget {
                background-color: #090d14;
                gridline-color: #21262d;
                border: 1px solid #21262d;
                color: #c9d1d9;
                font-family: 'Consolas';
                font-size: 11px;
            }
            QHeaderView::section {
                background-color: #161b22;
                color: #58a6ff;
                padding: 4px;
                border: 1px solid #21262d;
                font-weight: bold;
            }
            QTabWidget::pane { border: 1px solid #21262d; background-color: #0d1117; border-radius: 5px; }
            QTabBar::tab {
                background: #161b22;
                color: #8b949e;
                padding: 6px 14px;
                border: 1px solid #21262d;
                font-family: 'Consolas';
                font-weight: bold;
            }
            QTabBar::tab:selected { background: #1f6feb; color: #ffffff; }
            QPlainTextEdit {
                background-color: #06090e;
                color: #00ff9d;
                border: 1px solid #21262d;
                font-family: 'Consolas', monospace;
                font-size: 11px;
            }
        """)

        self.last_frame: Optional[np.ndarray] = None
        self.kilit_sayisi: int = 0
        self._current_lock_durum: KilitDurumu = KilitDurumu.IDLE
        self._current_lock_sure: float = 0.0
        self._current_fps: float = 30.0
        self._current_area_pct: float = 0.0
        self._mppi_lock_prob: float = 0.85
        self._active_tactical_mode: str = "AUTO_PURSUIT"
        self._pending_logs: List[str] = []

        self._init_ui()
        self._setup_event_listeners()

        # 30 FPS Native UI Yenileme Zamanlayıcısı
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_ui_tick)
        self.timer.start(33)

    def _init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        root_layout = QVBoxLayout(main_widget)
        root_layout.setContentsMargins(8, 6, 8, 6)
        root_layout.setSpacing(6)

        # ==================== ÜST DURUM ŞERİDİ (TOP TELEMETRY BAR) ====================
        top_bar = QFrame()
        top_bar.setStyleSheet("background-color: #0d1117; border: 1px solid #21262d; border-radius: 6px;")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(12, 6, 12, 6)

        self.lbl_banner_title = QLabel("🦅 AEROCOMBAT PYTHON TACTICAL GCS v4.0")
        self.lbl_banner_title.setStyleSheet("color: #00f0ff; font-size: 14px; font-weight: bold;")

        self.lbl_server_conn = QLabel("● MHS: BAĞLANIYOR")
        self.lbl_server_conn.setStyleSheet("color: #d29922; font-weight: bold;")

        self.lbl_server_offset = QLabel("RTT/Offset: 0.0 ms")
        self.lbl_fps_badge = QLabel("FPS: 30.0")
        self.lbl_fps_badge.setStyleSheet("color: #00ff9d; font-weight: bold;")

        self.lbl_ew_badge = QLabel("🛡 EW/GNSS: NOMINAL")
        self.lbl_ew_badge.setStyleSheet("color: #3fb950; font-weight: bold;")

        self.lbl_merkle_badge = QLabel("🔐 SHA-256 MERKLE: HAZIR")
        self.lbl_merkle_badge.setStyleSheet("color: #a371f7; font-weight: bold;")

        self.lbl_server_score = QLabel("SKOR: 0 PUAN")
        self.lbl_server_score.setStyleSheet(
            "background-color: #122d1f; color: #00ff9d; padding: 4px 10px; "
            "border: 1px solid #238636; border-radius: 4px; font-size: 13px; font-weight: bold;"
        )

        top_layout.addWidget(self.lbl_banner_title)
        top_layout.addStretch(1)
        top_layout.addWidget(self.lbl_server_conn)
        top_layout.addSpacing(12)
        top_layout.addWidget(self.lbl_server_offset)
        top_layout.addSpacing(12)
        top_layout.addWidget(self.lbl_fps_badge)
        top_layout.addSpacing(12)
        top_layout.addWidget(self.lbl_ew_badge)
        top_layout.addSpacing(12)
        top_layout.addWidget(self.lbl_merkle_badge)
        top_layout.addSpacing(12)
        top_layout.addWidget(self.lbl_server_score)
        root_layout.addWidget(top_bar)

        # ==================== ORTA 3 SÜTUNLU ANA KOKPİT ====================
        cockpit_layout = QHBoxLayout()
        cockpit_layout.setSpacing(8)

        # -------------------- SOL SÜTUN: PFD, KİLİT HALKASI & BOYD E-M --------------------
        left_col = QVBoxLayout()
        left_col.setSpacing(6)

        pfd_group = QGroupBox("PRIMARY FLIGHT DISPLAY (PFD)")
        pfd_vbox = QVBoxLayout(pfd_group)
        self.pfd_widget = PrimaryFlightDisplayWidget()
        pfd_vbox.addWidget(self.pfd_widget)
        left_col.addWidget(pfd_group, stretch=4)

        lock_ring_group = QGroupBox("4.0s KİLİTLENME & MPPI OLASILIK")
        lock_ring_hbox = QHBoxLayout(lock_ring_group)
        self.lock_ring_widget = LockCountdownRingWidget()
        lock_ring_hbox.addWidget(self.lock_ring_widget)

        # Sayısal Aviyonik Özet
        telem_grid = QGridLayout()
        self.lbl_alt = QLabel("80.0 m")
        self.lbl_spd = QLabel("22.0 m/s")
        self.lbl_yaw = QLabel("000 deg")
        self.lbl_pitch = QLabel("0.0 deg")
        self.lbl_roll = QLabel("0.0 deg")
        self.lbl_mode = QLabel("OTONOM")
        self.lbl_mode.setStyleSheet("color: #00ff9d; font-weight: bold;")
        self.prog_battery = QProgressBar()
        self.prog_battery.setValue(100)
        self.prog_battery.setFixedHeight(16)

        telem_grid.addWidget(QLabel("İrtifa:"), 0, 0)
        telem_grid.addWidget(self.lbl_alt, 0, 1)
        telem_grid.addWidget(QLabel("Hava Hızı:"), 1, 0)
        telem_grid.addWidget(self.lbl_spd, 1, 1)
        telem_grid.addWidget(QLabel("Baş (Yaw):"), 2, 0)
        telem_grid.addWidget(self.lbl_yaw, 2, 1)
        telem_grid.addWidget(QLabel("Pitch/Roll:"), 3, 0)
        telem_grid.addWidget(self.lbl_pitch, 3, 1)
        telem_grid.addWidget(QLabel("Yatış:"), 4, 0)
        telem_grid.addWidget(self.lbl_roll, 4, 1)
        telem_grid.addWidget(QLabel("Uçuş Modu:"), 5, 0)
        telem_grid.addWidget(self.lbl_mode, 5, 1)
        telem_grid.addWidget(QLabel("Batarya:"), 6, 0)
        telem_grid.addWidget(self.prog_battery, 6, 1)
        lock_ring_hbox.addLayout(telem_grid)
        left_col.addWidget(lock_ring_group, stretch=3)

        em_group = QGroupBox("JOHN BOYD E-M ENERJİ ZARFI (He / Ps)")
        em_vbox = QVBoxLayout(em_group)
        self.energy_chart = EnergyEnvelopeChartWidget()
        em_vbox.addWidget(self.energy_chart)
        left_col.addWidget(em_group, stretch=2)

        cockpit_layout.addLayout(left_col, stretch=3)

        # -------------------- ORTA SÜTUN: CANLI KAMERA HUD & TAKTİK KOMUTA --------------------
        center_col = QVBoxLayout()
        center_col.setSpacing(6)

        video_group = QGroupBox("CANLI OPTİK HEDEFLEME HUD (IMM + MPPI + OPTİK AKIŞ RE-ID)")
        video_layout = QVBoxLayout(video_group)

        self.lbl_video = QLabel("Kamera & Sentetik Gökyüzü Akışı Başlatılıyor...")
        self.lbl_video.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_video.setMinimumSize(720, 440)
        self.lbl_video.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.lbl_video.setStyleSheet("background-color: #000000; border: 1px solid #30363d; border-radius: 4px;")
        video_layout.addWidget(self.lbl_video)

        # Alt Kilit Durumu Çubuğu
        lock_bar = QHBoxLayout()
        self.lbl_lock_title = QLabel("KİLİT DURUMU:")
        self.lbl_lock_status = QLabel("IDLE")
        self.lbl_lock_status.setStyleSheet("color: #58a6ff; font-weight: bold; font-size: 13px;")

        self.prog_lock = QProgressBar()
        self.prog_lock.setRange(0, 100)
        self.prog_lock.setValue(0)
        self.prog_lock.setFixedHeight(20)

        self.lbl_neural_maneuver = QLabel("MANEVRA: LEAD_PURSUIT")
        self.lbl_neural_maneuver.setStyleSheet("color: #00f0ff; font-weight: bold;")

        lock_bar.addWidget(self.lbl_lock_title)
        lock_bar.addWidget(self.lbl_lock_status)
        lock_bar.addWidget(self.prog_lock, stretch=1)
        lock_bar.addSpacing(10)
        lock_bar.addWidget(self.lbl_neural_maneuver)
        video_layout.addLayout(lock_bar)
        center_col.addWidget(video_group, stretch=7)

        # Taktik BFM, Güdüm ve Görev Komuta Butonları
        cmd_group = QGroupBox("OTONOM TAKTİK MANEVRA & GÖREV KOMUTA PANELİ")
        cmd_grid = QGridLayout(cmd_group)

        self.btn_mppi = QPushButton("🎯 MPPI OPTİMAL KİLİT")
        self.btn_mppi.setStyleSheet("border-color: #00d2ff; color: #00f0ff;")
        self.btn_mppi.clicked.connect(lambda: self._trigger_tactical_action("MPPI_OPTIMAL_LOCK"))

        self.btn_break = QPushButton("⚡ BFM BREAK TURN")
        self.btn_break.setStyleSheet("border-color: #d29922; color: #ffb000;")
        self.btn_break.clicked.connect(lambda: self._trigger_tactical_action("BFM_BREAK_TURN"))

        self.btn_yoyo = QPushButton("🔄 HIGH YO-YO")
        self.btn_yoyo.clicked.connect(lambda: self._trigger_tactical_action("BFM_HIGH_YOYO"))

        self.btn_kamikaze = QPushButton("🚀 KAMİKAZE QR DALIŞ")
        self.btn_kamikaze.setStyleSheet("border-color: #a371f7; color: #d2a8ff;")
        self.btn_kamikaze.clicked.connect(lambda: self._trigger_tactical_action("KAMIKAZE_DIVE"))

        self.btn_mode_toggle = QPushButton("🕹 OTONOM / MANUEL")
        self.btn_mode_toggle.clicked.connect(self._on_mode_toggle)

        self.btn_reset_lock = QPushButton("🔓 KİLİDİ SIFIRLA")
        self.btn_reset_lock.clicked.connect(self._on_reset_lock)

        self.btn_proof_dir = QPushButton("📁 KANIT KLASÖRÜ")
        self.btn_proof_dir.clicked.connect(self._on_open_proofs)

        self.btn_3d_studio = QPushButton("🌐 3D PYTHON ARENA")
        self.btn_3d_studio.setStyleSheet("border-color: #3fb950; color: #3fb950;")
        self.btn_3d_studio.clicked.connect(self._on_open_3d_arena)

        self.btn_rtl = QPushButton("🚨 ACİL RTL (EVE DÖN)")
        self.btn_rtl.setStyleSheet("background-color: #da3633; color: #ffffff; border-color: #f85149;")
        self.btn_rtl.clicked.connect(self._on_emergency_rtl)

        cmd_grid.addWidget(self.btn_mppi, 0, 0)
        cmd_grid.addWidget(self.btn_break, 0, 1)
        cmd_grid.addWidget(self.btn_yoyo, 0, 2)
        cmd_grid.addWidget(self.btn_kamikaze, 0, 3)
        cmd_grid.addWidget(self.btn_mode_toggle, 1, 0)
        cmd_grid.addWidget(self.btn_reset_lock, 1, 1)
        cmd_grid.addWidget(self.btn_3d_studio, 1, 2)
        cmd_grid.addWidget(self.btn_rtl, 1, 3)
        center_col.addWidget(cmd_group, stretch=2)

        cockpit_layout.addLayout(center_col, stretch=5)

        # -------------------- SAĞ SÜTUN: 360° RADAR, IMM/MPPI SEKME & OLAY GÜNLÜĞÜ --------------------
        right_col = QVBoxLayout()
        right_col.setSpacing(6)

        radar_group = QGroupBox("360° TAKTİK RADAR & RWR TEHDİT")
        radar_vbox = QVBoxLayout(radar_group)
        self.radar_widget = TacticalRadarScopeWidget()
        radar_vbox.addWidget(self.radar_widget)
        right_col.addWidget(radar_group, stretch=4)

        # Çok Sekmeli Taktik Analiz Paneli
        self.tabs_right = QTabWidget()

        # Sekme 1: IMM 4-Model Olasılık Barları & MPPI Telemetrisi
        tab_imm = QWidget()
        imm_layout = QVBoxLayout(tab_imm)
        self.prog_imm_cv = QProgressBar()
        self.prog_imm_ctl = QProgressBar()
        self.prog_imm_ctr = QProgressBar()
        self.prog_imm_ca = QProgressBar()
        for bar, val in ((self.prog_imm_cv, 55), (self.prog_imm_ctl, 15), (self.prog_imm_ctr, 15), (self.prog_imm_ca, 15)):
            bar.setRange(0, 100)
            bar.setValue(val)
            bar.setFixedHeight(16)

        imm_grid = QGridLayout()
        imm_grid.addWidget(QLabel("CV (Düz Seyir):"), 0, 0)
        imm_grid.addWidget(self.prog_imm_cv, 0, 1)
        imm_grid.addWidget(QLabel("CT-L (Sol Dönüş):"), 1, 0)
        imm_grid.addWidget(self.prog_imm_ctl, 1, 1)
        imm_grid.addWidget(QLabel("CT-R (Sağ Dönüş):"), 2, 0)
        imm_grid.addWidget(self.prog_imm_ctr, 2, 1)
        imm_grid.addWidget(QLabel("CA (İvmeli Kaçış):"), 3, 0)
        imm_grid.addWidget(self.prog_imm_ca, 3, 1)
        imm_layout.addLayout(imm_grid)

        self.lbl_mppi_details = QLabel("MPPI: 48 Rollout | Boresight Err: 4.2° | Menzil: 35.8m")
        self.lbl_mppi_details.setStyleSheet("color: #00f0ff;")
        self.lbl_reid_details = QLabel("Optik Akış Re-ID: Aktif | Eşleşme Skoru: %98")
        self.lbl_reid_details.setStyleSheet("color: #3fb950;")
        imm_layout.addWidget(self.lbl_mppi_details)
        imm_layout.addWidget(self.lbl_reid_details)
        self.tabs_right.addTab(tab_imm, "IMM & MPPI")

        # Sekme 2: Rakip İHA & Sürü CBBA Tablosu
        tab_rivals = QWidget()
        rivals_vbox = QVBoxLayout(tab_rivals)
        self.table_rivals = QTableWidget(0, 4)
        self.table_rivals.setHorizontalHeaderLabels(["Takım", "İrtifa", "Yönelim", "Gecikme"])
        self.table_rivals.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        rivals_vbox.addWidget(self.table_rivals)
        self.tabs_right.addTab(tab_rivals, "RAKİP / CBBA")

        right_col.addWidget(self.tabs_right, stretch=3)

        # Canlı Kokpit Sesli Uyarı ("Bitchin' Betty") ve Görev Olay Günlüğü
        log_group = QGroupBox("CANLI GÖREV, EW & SESLİ UYARI (CVWS) GÜNLÜĞÜ")
        log_vbox = QVBoxLayout(log_group)
        self.txt_event_log = QPlainTextEdit()
        self.txt_event_log.setReadOnly(True)
        self.txt_event_log.setMaximumBlockCount(150)
        log_vbox.addWidget(self.txt_event_log)
        right_col.addWidget(log_group, stretch=3)

        cockpit_layout.addLayout(right_col, stretch=3)
        root_layout.addLayout(cockpit_layout, stretch=1)

        self._append_log("AeroCombat Python PyQt6 Taktik Komuta Merkezi v4.0 başlatıldı.")

    def _append_log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        self._pending_logs.append(f"[{ts}] {msg}")

    def _setup_event_listeners(self):
        """EventBus üzerinden arka plan olaylarını dinler."""
        bus.subscribe(EVENT_FRAME_PROCESSED, self._on_frame_received)
        bus.subscribe(EVENT_TELEMETRY_UPDATED, self._on_telemetry_updated)
        bus.subscribe(EVENT_RIVALS_UPDATED, self._on_rivals_updated)
        bus.subscribe(EVENT_SERVER_STATUS, self._on_server_status)
        bus.subscribe(EVENT_LOCK_STARTED, self._on_lock_started)
        bus.subscribe(EVENT_LOCK_SUCCESS, self._on_lock_success)
        bus.subscribe(EVENT_LOCK_LOST, self._on_lock_lost)
        bus.subscribe(EVENT_ENERGY_STATE_UPDATED, self._on_energy_updated)
        bus.subscribe(EVENT_EW_ALERT, self._on_ew_alert)
        bus.subscribe(EVENT_RWR_ALERT, self._on_rwr_alert)
        bus.subscribe(EVENT_TACTICAL_MANEUVER, self._on_tactical_maneuver)
        bus.subscribe(EVENT_GEOFENCE_ALERT, self._on_geofence_alert)

    def _on_frame_received(self, frame: np.ndarray, durum: KilitDurumu, sure: float, hedef=None, fps: float = 30.0, **kwargs):
        self.last_frame = frame
        self._current_lock_durum = durum
        self._current_lock_sure = float(sure)
        self._current_fps = float(fps)
        if hedef is not None and frame is not None:
            h, w = frame.shape[:2]
            self._current_area_pct = hedef.alan_orani(w, h) * 100.0
        else:
            self._current_area_pct = 0.0

    def _on_telemetry_updated(self, telemetri: TelemetriPaketi, **kwargs):
        self._latest_telemetry = telemetri

    def _on_rivals_updated(self, rakipler: List[RakipIHABilgisi], **kwargs):
        self._latest_rivals = rakipler

    def _on_server_status(self, bagli: bool, logged_in: bool, **kwargs):
        self._server_state = (bagli, logged_in)

    def _on_lock_started(self, hedef_id=None, **kwargs):
        self._append_log(f"🎯 KİLİT SAYACI BAŞLADI -> Hedef ID: {hedef_id}")

    def _on_lock_success(self, kanit_yolu: str = "", **kwargs):
        self.kilit_sayisi += 1
        self._append_log(f"🏆 4.0s KİLİTLENME ONAYLANDI (+100 PUAN)! Kanıt: {os.path.basename(kanit_yolu)}")

    def _on_lock_lost(self, **kwargs):
        self._append_log("⚠️ Hedef kilit penceresinden çıktı (Grace süresi aşıldı).")

    def _on_energy_updated(self, energy: EnergyState, **kwargs):
        self._latest_energy = energy

    def _on_ew_alert(self, alert_msg: str = "", status: Optional[EWStatus] = None, **kwargs):
        self._latest_ew_msg = alert_msg
        self._latest_ew_status = status

    def _on_rwr_alert(self, assessment=None, **kwargs):
        self._rwr_alert_time = time.time()

    def _on_tactical_maneuver(self, command=None, **kwargs):
        self._latest_maneuver_cmd = command

    def _on_geofence_alert(self, msg: str = "Sınır İhlali!", **kwargs):
        self._append_log(f"🚨 GEOFENCE UYARISI: {msg}")

    def _update_ui_tick(self):
        """Ana GUI iş parçacığında (Main Thread) tüm özel göstergeleri 30 Hz'de günceller."""
        # 0. Arka plan thread'lerinden gelen logları güvenli şekilde ana thread'de yazdır
        while self._pending_logs:
            line = self._pending_logs.pop(0)
            self.txt_event_log.appendPlainText(line)

        # 1. Kamera HUD karesi
        if self.last_frame is not None:
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

        self.lbl_fps_badge.setText(f"FPS: {self._current_fps:.1f}")
        self.radar_widget.tick_sweep()

        # 2. Kilit Halka Göstergesi ve Bar
        self.lock_ring_widget.set_lock_state(
            status=self._current_lock_durum,
            duration_s=self._current_lock_sure,
            total_locks=self.kilit_sayisi,
            area_pct=self._current_area_pct,
            mppi_prob=self._mppi_lock_prob
        )
        self.lbl_lock_status.setText(self._current_lock_durum.value)
        pct = min(100, int((self._current_lock_sure / 4.0) * 100))
        if self._current_lock_durum == KilitDurumu.LOCKED:
            pct = 100
            self.lbl_lock_status.setStyleSheet("color: #00ff9d; font-weight: bold;")
        elif self._current_lock_durum == KilitDurumu.LOCKING:
            self.lbl_lock_status.setStyleSheet("color: #ffb000; font-weight: bold;")
        else:
            self.lbl_lock_status.setStyleSheet("color: #58a6ff; font-weight: bold;")
        self.prog_lock.setValue(pct)
        self.lbl_server_score.setText(f"SKOR: {self.kilit_sayisi * 100} PUAN (+{self.kilit_sayisi})")

        # 3. Uçuş Telemetrisi & PFD
        tel: Optional[TelemetriPaketi] = getattr(self, "_latest_telemetry", None)
        if tel is not None:
            self.lbl_alt.setText(f"{tel.IHA_irtifa:.1f} m")
            self.lbl_spd.setText(f"{tel.IHA_hiz:.1f} m/s")
            self.lbl_yaw.setText(f"{int(tel.IHA_yonelme):03d}°")
            self.lbl_pitch.setText(f"{tel.IHA_dikilme:+.1f}°")
            self.lbl_roll.setText(f"{tel.IHA_yatis:+.1f}°")
            self.lbl_mode.setText("OTONOM" if tel.IHA_otonom else "MANUEL")
            self.prog_battery.setValue(tel.IHA_batarya)

            g_load = 1.0 / max(0.35, abs(math.cos(math.radians(tel.IHA_yatis))))
            self.pfd_widget.set_flight_state(
                roll_deg=tel.IHA_yatis,
                pitch_deg=tel.IHA_dikilme,
                yaw_deg=tel.IHA_yonelme,
                airspeed_mps=tel.IHA_hiz,
                altitude_m=tel.IHA_irtifa,
                g_load=g_load,
                stall_warning=(tel.IHA_hiz < 14.5)
            )
            self.radar_widget.own_yaw_deg = tel.IHA_yonelme

        # 4. Sunucu Bağlantı & RTT Saat Ofseti
        if self.system and self.system.referee_client:
            offset_ms = self.system.referee_client.time_sync.offset_ms
            self.lbl_server_offset.setText(f"Offset: {offset_ms:+.1f} ms")
        srv_state = getattr(self, "_server_state", (True, True))
        if srv_state[0] and srv_state[1]:
            self.lbl_server_conn.setText("● MHS: BAĞLI & SENKRON")
            self.lbl_server_conn.setStyleSheet("color: #00ff9d; font-weight: bold;")
        elif srv_state[0]:
            self.lbl_server_conn.setText("● MHS: OTURUM BEKLENİYOR")
            self.lbl_server_conn.setStyleSheet("color: #ffb000; font-weight: bold;")
        else:
            self.lbl_server_conn.setText("● MHS: BAĞLANTI KOPUK")
            self.lbl_server_conn.setStyleSheet("color: #ff4d4d; font-weight: bold;")

        # 5. Boyd E-M Enerji Zarfı
        energy: Optional[EnergyState] = getattr(self, "_latest_energy", None)
        if energy is not None:
            self.energy_chart.push_energy_state(energy)

        # 6. IMM Model Olasılıkları ve MPPI Optimal Yörünge
        if self.system and getattr(self.system, "imm_filter", None) is not None:
            imm = self.system.imm_filter
            probs = imm.mu
            self.prog_imm_cv.setValue(int(probs[0] * 100))
            self.prog_imm_ctl.setValue(int(probs[1] * 100))
            self.prog_imm_ctr.setValue(int(probs[2] * 100))
            self.prog_imm_ca.setValue(int(probs[3] * 100))
            dom_idx = int(np.argmax(probs))
            self.radar_widget.imm_mode_label = imm.models[dom_idx].mode.value

        if self.system and getattr(self.system, "proof_chain", None) is not None:
            pc = self.system.proof_chain
            rec_count = len(pc.records)
            self.lbl_merkle_badge.setText(f"🔐 MERKLE ZİNCİRİ: {rec_count} KARE")

        # 7. RWR ve Nöral Manevra Durumu
        rwr_time = getattr(self, "_rwr_alert_time", 0.0)
        self.radar_widget.rwr_warning = (time.time() - rwr_time) < 2.0

        man_cmd = getattr(self, "_latest_maneuver_cmd", None)
        if man_cmd is not None and hasattr(man_cmd, "maneuver"):
            self.lbl_neural_maneuver.setText(f"MANEVRA: {man_cmd.maneuver.value}")

        # 8. Rakip Tablosu
        rivals: List[RakipIHABilgisi] = getattr(self, "_latest_rivals", [])
        self.radar_widget.rivals = rivals
        if rivals:
            self.table_rivals.setRowCount(len(rivals))
            for row, r in enumerate(rivals):
                self.table_rivals.setItem(row, 0, QTableWidgetItem(f"Takım {r.takim_numarasi}"))
                self.table_rivals.setItem(row, 1, QTableWidgetItem(f"{r.IHA_irtifa:.1f}m"))
                self.table_rivals.setItem(row, 2, QTableWidgetItem(f"{int(r.IHA_yonelme)}°"))
                self.table_rivals.setItem(row, 3, QTableWidgetItem(f"{r.zaman_farki}ms"))

    def _trigger_tactical_action(self, action_name: str):
        self._active_tactical_mode = action_name
        self.lbl_neural_maneuver.setText(f"KOMUT: {action_name}")
        self._append_log(f"⚡ Operatör Taktik Komutu Gönderildi: {action_name}")

    def _on_emergency_rtl(self):
        logger.warning("YKİ: ACİL RTL BUTONUNA BASILDI!")
        self._append_log("🚨 ACİL DURUM: Otonom RTL (Eve Dönüş) Modu Aktif Edildi!")
        if self.system and self.system.autopilot:
            self.system.autopilot.set_mode("RTL")

    def _on_mode_toggle(self):
        if self.system and self.system.autopilot:
            current = self.system.autopilot.is_autonomous
            new_mode = "MANUAL" if current else "GUIDED"
            self.system.autopilot.set_mode(new_mode)
            self._append_log(f"🕹 Otopilot Uçuş Modu Değiştirildi -> {new_mode}")

    def _on_reset_lock(self):
        if self.system and self.system.lock_engine:
            self.system.lock_engine.reset()
            self._append_log("🔓 Kilitlenme motoru operatör tarafından sıfırlandı.")

    def _on_open_proofs(self):
        proofs_dir = os.path.abspath("proofs")
        os.makedirs(proofs_dir, exist_ok=True)
        self._append_log(f"📁 Kanıt dizini açılıyor: {proofs_dir}")
        if sys.platform == "win32":
            os.startfile(proofs_dir)
        else:
            os.system(f"xdg-open '{proofs_dir}'")

    def _on_open_3d_arena(self):
        """Native Python PyQt6 3D İt Dalaşı Stüdyosunu yan pencerede açar."""
        try:
            from gcs.flight_viewer_3d import FlightViewer3DWindow
            self._viewer_3d_window = FlightViewer3DWindow()
            self._viewer_3d_window.show()
            self._append_log("🌐 Native Python 3D İt Dalaşı Stüdyosu açıldı.")
        except Exception as e:
            self._append_log(f"3D Arena hatası: {e}")


def launch_gcs(system_controller=None):
    """Native Python PyQt6 Taktik Yer Kontrol İstasyonu v4.0'ı başlatır."""
    if not PYQT_AVAILABLE:
        logger.error("PyQt6 kurulu olmadığından görsel arayüz başlatılamadı. CLI modu çalıştırılıyor.")
        return
    app = QApplication.instance() or QApplication(sys.argv)
    window = GCSMainWindow(system_controller)
    window.show()
    app.exec()
