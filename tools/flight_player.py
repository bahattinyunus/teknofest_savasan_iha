import os
import sys
import time
import argparse
from typing import List, Dict, Any

# Proje ana dizinini path'e ekle
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.logger import logger
from core.models import TelemetriPaketi, ZamanBilgisi


class FlightLogPlayer:
    """Kaydedilmiş uçuş ve telemetri loglarını oynatan test oynatıcısı."""

    def __init__(self, log_path: str):
        self.log_path = log_path

    def generate_dummy_log(self, save_path: str = "logs/sample_flight.csv", duration_sec: int = 60):
        """Örnek bir uçuş telemetri CSV dosyası oluşturur."""
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        import math
        with open(save_path, "w", encoding="utf-8") as f:
            f.write("time_sec,lat,lon,alt,pitch,yaw,roll,speed,battery,autonomous,locked\n")
            for i in range(duration_sec * 5):  # 5 Hz
                t = i * 0.2
                lat = 41.1040 + 0.002 * math.cos(t * 0.1)
                lon = 28.9050 + 0.002 * math.sin(t * 0.1)
                alt = 85.0 + 5.0 * math.sin(t * 0.3)
                pitch = 1.5 * math.sin(t * 0.5)
                yaw = (t * 6.0) % 360.0
                roll = 5.0 * math.sin(t * 0.4)
                spd = 18.0 + 1.0 * math.cos(t * 0.2)
                bat = max(10, int(98 - (t / 60.0)))
                f.write(f"{t:.2f},{lat:.6f},{lon:.6f},{alt:.2f},{pitch:.2f},{yaw:.2f},{roll:.2f},{spd:.2f},{bat},1,0\n")
        logger.info(f"Örnek uçuş telemetrisi kaydedildi: {save_path}")

    def play(self, loop: bool = False):
        """CSV telemetri dosyasını satır satır okur ve simüle eder."""
        if not os.path.exists(self.log_path):
            logger.warning(f"Log dosyası bulunamadı: {self.log_path}. Örnek dosya üretiliyor...")
            self.generate_dummy_log(self.log_path)

        logger.info(f"Uçuş logu oynatılıyor: {self.log_path}")
        with open(self.log_path, "r", encoding="utf-8") as f:
            headers = f.readline().strip().split(",")
            lines = f.readlines()

        for line in lines:
            parts = line.strip().split(",")
            if len(parts) < 11:
                continue
            time_val, lat, lon, alt, pitch, yaw, roll, spd, bat, aut, lck = parts
            logger.info(
                f"[T+{float(time_val):05.1f}s] Alt: {float(alt):.1f}m | "
                f"Spd: {float(spd):.1f}m/s | Hdg: {float(yaw):03.0f}° | "
                f"P:{float(pitch):+.1f}° R:{float(roll):+.1f}° | Bat: %{bat}"
            )
            time.sleep(0.2)  # 5 Hz oynatma hızı


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Uçuş Telemetri Log Oynatıcı")
    parser.add_argument("--log", type=str, default="logs/sample_flight.csv", help="Oynatılacak CSV dosyası")
    parser.add_argument("--create-sample", action="store_true", help="Örnek log dosyası üret")
    args = parser.parse_args()

    player = FlightLogPlayer(args.log)
    if args.create_sample:
        player.generate_dummy_log(args.log)
    else:
        player.play()
