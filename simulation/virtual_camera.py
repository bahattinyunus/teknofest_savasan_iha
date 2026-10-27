import cv2
import time
import math
import numpy as np


class VirtualCameraFeed:
    """Yapay gökyüzü ve hareketli rakip İHA içeren sentetik video akışı üretici.
    
    Kamera donanımı veya uçuş alanı olmadan algoritmaları ve kilitlenmeyi
    tamamen yerel bilgisayarda test etmeyi sağlar.
    """

    def __init__(self, width: int = 1280, height: int = 720, fps: int = 30):
        self.width = width
        self.height = height
        self.fps = fps
        self.start_time = time.time()

    def get_frame(self) -> np.ndarray:
        """Gerçek zamanlı sentetik kare üretir."""
        t = time.time() - self.start_time

        # 1. Gökyüzü Degrade Arka Planı (Mavi tonları)
        frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        frame[:, :] = [180, 130, 70]  # Gökyüzü mavisi (BGR)

        # Alt kısım ufuk/yeryüzü
        horizon_y = int(self.height * 0.75 + 15 * math.sin(t * 0.5))
        frame[horizon_y:, :] = [60, 90, 70]  # Arazi yeşili

        # Bulutlar
        cv2.circle(frame, (int((t * 20) % (self.width + 200) - 100), int(self.height * 0.25)), 60, (230, 230, 230), -1)
        cv2.circle(frame, (int((t * 20 + 50) % (self.width + 200) - 100), int(self.height * 0.23)), 70, (230, 230, 230), -1)

        # 2. Sentetik Rakip İHA Konumu ve Hareketi
        # Uçak ekran merkezinde manevra yapar
        cx = (self.width / 2.0) + (self.width * 0.12) * math.sin(t * 0.7)
        cy = (self.height / 2.0) + (self.height * 0.08) * math.cos(t * 0.9)
        
        # %5 kuralını sağlayacak boyutta (Genişlik ~ 240px, Yükseklik ~ 180px)
        scale = 1.0 + 0.15 * math.sin(t * 0.4)
        wing_span = int(120 * scale)
        fuselage_len = int(80 * scale)

        # Uçak Gövdesi ve Kanatları (Gri/Kamuflaj İHA)
        pt_nose = (int(cx), int(cy - fuselage_len * 0.6))
        pt_tail = (int(cx), int(cy + fuselage_len * 0.6))
        pt_wing_left = (int(cx - wing_span), int(cy))
        pt_wing_right = (int(cx + wing_span), int(cy))

        # Kanat çizgisi
        cv2.line(frame, pt_wing_left, pt_wing_right, (40, 40, 40), int(10 * scale), cv2.LINE_AA)
        # Gövde çizgisi
        cv2.line(frame, pt_nose, pt_tail, (50, 50, 50), int(14 * scale), cv2.LINE_AA)
        # Kuyruk yatay kanatçık
        tail_wing = int(wing_span * 0.35)
        cv2.line(frame, (int(cx - tail_wing), pt_tail[1]), (int(cx + tail_wing), pt_tail[1]), (30, 30, 30), int(6 * scale), cv2.LINE_AA)

        # Motor egzoz efekti
        cv2.circle(frame, pt_tail, int(4 * scale), (0, 165, 255), -1)

        return frame
