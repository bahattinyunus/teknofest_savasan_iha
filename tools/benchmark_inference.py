import os
import sys
import time
import argparse
from typing import Dict, Any, List
import numpy as np

# Proje ana dizinini path'e ekle
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.logger import setup_logger, logger
from vision.detector import YoloDetector, MockDetector


def benchmark_inference(
    model_path: str = "models/savasan_iha_best.pt",
    img_size: int = 640,
    iterations: int = 100,
    warmup: int = 15,
    device: str = "cpu"
) -> Dict[str, Any]:
    """Derin öğrenme hedef tespit modelinin FPS ve gecikme (Latency) performansını ölçer."""
    print("\n" + "=" * 70)
    print("      TEKNOFEST SAVAŞAN İHA - MODEL VE ÇIKARIM BENCHMARK ARACI     ")
    print("=" * 70 + "\n")

    logger.info(f"Test Parametreleri: Çözünürlük={img_size}x{img_size}, İterasyon={iterations}, Cihaz={device}")

    # Test tensörü (Rastgele kare)
    dummy_frame = np.random.randint(0, 255, (img_size, img_size, 3), dtype=np.uint8)

    # Dedektör başlat
    if os.path.exists(model_path):
        detector = YoloDetector(model_path=model_path, device=device)
        model_name = os.path.basename(model_path)
    else:
        logger.warning(f"Model dosyası bulunamadı ({model_path}), sentetik MockDetector benchmark ediliyor.")
        detector = MockDetector()
        model_name = "MockDetector (Synthetic Target Generator)"

    # 1. Warm-up (Isınma Turları - GPU/CPU cache hazırlığı)
    print(f"[*] Isınma turları yürütülüyor ({warmup} iterasyon)...")
    for _ in range(warmup):
        _ = detector.detect(dummy_frame)

    # 2. Benchmark Ölçüm Döngüsü
    print(f"[*] Asıl test çalıştırılıyor ({iterations} iterasyon)...")
    latencies_ms: List[float] = []

    t_start_total = time.perf_counter()
    for i in range(iterations):
        t0 = time.perf_counter()
        _ = detector.detect(dummy_frame)
        t1 = time.perf_counter()
        latencies_ms.append((t1 - t0) * 1000.0)

    total_time_sec = max(1e-6, time.perf_counter() - t_start_total)

    # İstatistikler
    latencies_ms = np.array(latencies_ms)
    avg_latency = float(np.mean(latencies_ms))
    median_latency = float(np.median(latencies_ms))
    p90_latency = float(np.percentile(latencies_ms, 90))
    p95_latency = float(np.percentile(latencies_ms, 95))
    p99_latency = float(np.percentile(latencies_ms, 99))
    min_latency = float(np.min(latencies_ms))
    max_latency = float(np.max(latencies_ms))
    fps = iterations / total_time_sec

    # Raporlama
    print("\n" + "-" * 70)
    print(f" Model Adı        : {model_name}")
    print(f" Giriş Çözünürlüğü: {img_size} x {img_size} x 3")
    print(f" Ortalama Hız (FPS): {fps:.1f} FPS")
    print(f" Ortalama Gecikme : {avg_latency:.2f} ms")
    print(f" Medyan (P50)     : {median_latency:.2f} ms")
    print(f" P90 Gecikme      : {p90_latency:.2f} ms")
    print(f" P95 Gecikme      : {p95_latency:.2f} ms")
    print(f" P99 Gecikme      : {p99_latency:.2f} ms")
    print(f" Min / Maks       : {min_latency:.2f} ms / {max_latency:.2f} ms")
    print("-" * 70)

    is_realtime_ready = (fps >= 25.0 and p95_latency <= 40.0)
    if is_realtime_ready:
        print(" >> DEĞERLENDİRME: [BAŞARILI] Sistem gerçek zamanlı 30 FPS kilitlenme için yeterli hıza sahip! 🚀")
    else:
        print(" >> DEĞERLENDİRME: [İYİLEŞTİRME GEREKLİ] Model Jetson üzerinde FP16 TensorRT veya ONNX ile optimize edilmelidir.")
    print("=" * 70 + "\n")

    return {
        "model_name": model_name,
        "fps": round(fps, 1),
        "avg_latency_ms": round(avg_latency, 2),
        "p50_latency_ms": round(median_latency, 2),
        "p95_latency_ms": round(p95_latency, 2),
        "p99_latency_ms": round(p99_latency, 2),
        "is_realtime_ready": is_realtime_ready
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AeroCombat Model Çıkarım Hızı ve FPS Benchmark Aracı")
    parser.add_argument("--model", type=str, default="models/savasan_iha_best.pt", help="Model yolu (.pt veya .onnx)")
    parser.add_argument("--size", type=int, default=640, help="Giriş boyutu")
    parser.add_argument("--iter", type=int, default=50, help="Ölçüm iterasyon sayısı")
    parser.add_argument("--warmup", type=int, default=10, help="Isınma turu sayısı")
    parser.add_argument("--device", type=str, default="cpu", help="Cihaz (cpu veya cuda:0)")
    args = parser.parse_args()

    benchmark_inference(args.model, args.size, args.iter, args.warmup, args.device)
