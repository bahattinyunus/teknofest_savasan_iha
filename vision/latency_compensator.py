import time
from typing import Tuple, Optional
import numpy as np
from core.models import HedefKutusu
from core.logger import logger


class DelayedKalmanFilter:
    """Kamera yakalama ve derin öğrenme çıkarım gecikmesini (Latency) kompanse eden Kalman Filtresi.
    
    MBZIRC ve DARPA hava muharebe sistemlerinde uygulanan gecikme telafisi (Latency Compensation)
    sayesinde, hedef yüksek hızda manevra yaparken dahi kilitlenme merkezde tutulur.
    
    Durum Vektörü: x = [cx, cy, vx, vy]^T
    """

    def __init__(self, process_noise: float = 1.0, measurement_noise: float = 0.5):
        self.process_noise = process_noise
        self.measurement_noise = measurement_noise
        
        # 4 durumlu vektör: [x, y, vx, vy]
        self.state = np.zeros(4, dtype=np.float64)
        self.P = np.eye(4, dtype=np.float64) * 10.0
        self.last_update_time: Optional[float] = None
        self.prev_measurement: Optional[Tuple[float, float]] = None
        self.is_initialized = False

    def reset(self):
        self.state = np.zeros(4, dtype=np.float64)
        self.P = np.eye(4, dtype=np.float64) * 10.0
        self.last_update_time = None
        self.prev_measurement = None
        self.is_initialized = False

    def update(self, measured_x: float, measured_y: float, timestamp: float) -> Tuple[float, float]:
        """Yeni bir hedef tespiti geldiğinde Kalman filtresini günceller."""
        if not self.is_initialized or self.last_update_time is None:
            self.state[0] = measured_x
            self.state[1] = measured_y
            self.state[2:] = 0.0
            self.last_update_time = timestamp
            self.prev_measurement = (measured_x, measured_y)
            self.is_initialized = True
            return measured_x, measured_y

        dt = max(1e-4, timestamp - self.last_update_time)

        # İlk hız tahmini tohumu
        if self.prev_measurement is not None and np.all(self.state[2:] == 0.0):
            vx_init = (measured_x - self.prev_measurement[0]) / dt
            vy_init = (measured_y - self.prev_measurement[1]) / dt
            self.state[2] = vx_init
            self.state[3] = vy_init

        # 1. Durum Geçiş Matrisi (F)
        F = np.eye(4, dtype=np.float64)
        F[0, 2] = dt
        F[1, 3] = dt

        # Süreç gürültüsü (Q)
        Q = np.eye(4, dtype=np.float64) * (self.process_noise * dt)

        # Tahmin (Prediction)
        x_pred = F @ self.state
        P_pred = F @ self.P @ F.T + Q

        # 2. Ölçüm Güncellemesi
        H = np.zeros((2, 4), dtype=np.float64)
        H[0, 0] = 1.0
        H[1, 1] = 1.0
        R = np.eye(2, dtype=np.float64) * self.measurement_noise

        z = np.array([measured_x, measured_y], dtype=np.float64)
        y = z - H @ x_pred
        S = H @ P_pred @ H.T + R
        K = P_pred @ H.T @ np.linalg.inv(S)

        self.state = x_pred + K @ y
        self.P = (np.eye(4) - K @ H) @ P_pred
        self.last_update_time = timestamp
        self.prev_measurement = (measured_x, measured_y)

        return float(self.state[0]), float(self.state[1])

    def predict_future(self, latency_sec: float) -> Tuple[float, float]:
        """Gecikme süresi (örneğin 35 ms) kadar gelecekteki hedef konumunu tahmin eder."""
        if not self.is_initialized:
            return 0.0, 0.0

        # x_future = x + vx*dt
        pred_x = self.state[0] + self.state[2] * latency_sec
        pred_y = self.state[1] + self.state[3] * latency_sec

        return float(pred_x), float(pred_y)

    def compensate_box(self, box: HedefKutusu, latency_sec: float = 0.035, timestamp: Optional[float] = None) -> HedefKutusu:
        """Kutunun merkezini gecikme süresi kadar ileri öteleyerek anlık gerçek konumu üretir."""
        ts = timestamp if timestamp is not None else time.time()
        self.update(box.merkez_x, box.merkez_y, ts)
        pred_x, pred_y = self.predict_future(latency_sec)

        dx = pred_x - box.merkez_x
        dy = pred_y - box.merkez_y

        compensated = HedefKutusu(
            x1=box.x1 + dx,
            y1=box.y1 + dy,
            x2=box.x2 + dx,
            y2=box.y2 + dy,
            conf=box.conf,
            track_id=box.track_id,
            class_id=box.class_id,
            class_name=box.class_name
        )
        return compensated
