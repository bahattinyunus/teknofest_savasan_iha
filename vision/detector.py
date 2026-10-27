import os
import math
import time
from typing import List, Optional
import numpy as np

from core.models import HedefKutusu
from core.logger import logger


class BaseDetector:
    """Tespit algoritmaları için temel soyut sınıf."""
    def detect(self, frame: np.ndarray) -> List[HedefKutusu]:
        raise NotImplementedError


class YoloDetector(BaseDetector):
    """Ultralytics YOLO (v8 / v11) veya ONNX tabanlı İHA tespit sınıfı."""
    
    def __init__(
        self,
        model_path: str = "models/savasan_iha_best.pt",
        conf_thresh: float = 0.45,
        iou_thresh: float = 0.45,
        device: str = "cpu"
    ):
        self.model_path = model_path
        self.conf_thresh = conf_thresh
        self.iou_thresh = iou_thresh
        self.device = device
        self.model = None
        self._init_model()

    def _init_model(self):
        if not os.path.exists(self.model_path):
            logger.warning(f"YOLO model dosyası bulunamadı: {self.model_path}. Simülasyon moduna geçilebilir.")
            return

        try:
            from ultralytics import YOLO
            self.model = YOLO(self.model_path)
            logger.info(f"YOLO modeli başarıyla yüklendi: {self.model_path} [Cihaz: {self.device}]")
        except ImportError:
            logger.error("ultralytics kütüphanesi yüklü değil! 'pip install ultralytics' çalıştırın.")
        except Exception as e:
            logger.error(f"YOLO modeli yüklenirken hata oluştu: {e}")

    def detect(self, frame: np.ndarray) -> List[HedefKutusu]:
        if self.model is None or frame is None:
            return []

        try:
            results = self.model.predict(
                source=frame,
                conf=self.conf_thresh,
                iou=self.iou_thresh,
                device=self.device,
                verbose=False
            )
            
            boxes_found = []
            if len(results) > 0 and results[0].boxes is not None:
                for box in results[0].boxes:
                    coords = box.xyxy[0].cpu().numpy()
                    conf = float(box.conf[0].cpu().numpy())
                    cls_id = int(box.cls[0].cpu().numpy())
                    cls_name = self.model.names.get(cls_id, "iha")
                    
                    boxes_found.append(HedefKutusu(
                        x1=float(coords[0]),
                        y1=float(coords[1]),
                        x2=float(coords[2]),
                        y2=float(coords[3]),
                        conf=conf,
                        class_id=cls_id,
                        class_name=cls_name
                    ))
            return boxes_found
        except Exception as e:
            logger.error(f"Tespit hatası: {e}")
            return []


class MockDetector(BaseDetector):
    """Test ve simülasyon ortamı için sanal rakip İHA üreten tespitçi."""
    
    def __init__(self, start_x: float = 640.0, start_y: float = 360.0):
        self.start_x = start_x
        self.start_y = start_y
        self.start_time = time.time()
        logger.info("MockDetector (Sanal Hedef Üretici) aktif edildi.")

    def detect(self, frame: np.ndarray) -> List[HedefKutusu]:
        if frame is None:
            return []
            
        h, w = frame.shape[:2]
        t = time.time() - self.start_time
        
        # Ekranın merkezinde sinüzoidal hareket eden bir hedef simülasyonu
        # 1280x720 ekranda %5 alan yaklaşık 1280*720*0.05 = 46080 piksel^2 (yaklaşık 240x192 piksel)
        box_w = 260.0 + 20.0 * math.sin(t * 0.5)
        box_h = 190.0 + 15.0 * math.cos(t * 0.5)
        
        # Merkez etrafında hafif salınım
        center_x = (w / 2.0) + 120.0 * math.sin(t * 0.8)
        center_y = (h / 2.0) + 70.0 * math.cos(t * 0.6)
        
        x1 = max(0.0, center_x - box_w / 2.0)
        y1 = max(0.0, center_y - box_h / 2.0)
        x2 = min(float(w), center_x + box_w / 2.0)
        y2 = min(float(h), center_y + box_h / 2.0)
        
        return [
            HedefKutusu(
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                conf=0.92,
                track_id=1,
                class_id=0,
                class_name="rakip_iha"
            )
        ]
