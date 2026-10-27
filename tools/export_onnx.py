import os
import argparse
from core.logger import logger


def export_yolo_to_onnx(model_path: str, imgsz: int = 640, half: bool = True):
    """Ultralytics PyTorch modelini Jetson / GPU için optimize ONNX ve TensorRT formatına çevirir."""
    if not os.path.exists(model_path):
        logger.error(f"Model dosyası bulunamadı: {model_path}")
        return

    try:
        from ultralytics import YOLO
        logger.info(f"Model yükleniyor: {model_path}")
        model = YOLO(model_path)
        
        logger.info(f"ONNX dışa aktarımı başlatılıyor (imgsz={imgsz}, half={half})...")
        export_path = model.export(
            format="onnx",
            imgsz=imgsz,
            half=half,
            dynamic=False,
            simplify=True
        )
        logger.info(f"Dışa aktarım başarıyla tamamlandı: {export_path}")
    except ImportError:
        logger.error("ultralytics kütüphanesi bulunamadı! 'pip install ultralytics' çalıştırın.")
    except Exception as e:
        logger.error(f"Dışa aktarım hatası: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YOLO Modelini Optimize ONNX Formatına Dönüştürücü")
    parser.add_argument("--model", type=str, default="models/savasan_iha_best.pt", help="PyTorch model yolu (.pt)")
    parser.add_argument("--imgsz", type=int, default=640, help="Giriş çözünürlüğü")
    parser.add_argument("--half", action="store_true", default=True, help="FP16 yarı hassasiyet")
    args = parser.parse_args()

    export_yolo_to_onnx(args.model, args.imgsz, args.half)
