"""
Çoklu İHA İt Dalaşı Simülatörü ve Test Köprüsü (Dogfight SITL Combat Simulator).
Mavi (Dost) ve Kırmızı (Rakip) İHA'ların 3D uçuş dinamiklerini, görsel izdüşümlerini,
it dalaşı manevralarını ve kilitlenme motorunu simüle eden simülasyon motoru.
"""

import math
import time
import numpy as np
from enum import Enum
from dataclasses import dataclass
from typing import Tuple, List, Optional, Dict, Any
from core.models import HedefKutusu, TelemetriPaketi, RakipIHA, KilitDurumu
from vision.lock_engine import LockEngine


class TargetBehavior(Enum):
    """Kırmızı İHA'nın simüle edilen uçuş manevra davranışı."""
    ORBIT = "ORBIT"               # Sabit daire çizme (standart devriye)
    WEAVE = "WEAVE"               # Sinüzoidal S-dönüşleri (hafif kaçınma)
    AGGRESSIVE_BFM = "AGGRESSIVE_BFM" # Yüksek G'li ani Break Turn ve makas
    HEAD_ON = "HEAD_ON"           # Kafa kafaya geçiş ve merge manevrası


@dataclass
class AircraftState:
    """3D Simüle edilen uçak durum vektörü."""
    x: float = 0.0               # Kuzey (m)
    y: float = 0.0               # Doğu (m)
    z: float = 80.0              # İrtifa (m)
    vx: float = 20.0             # Kuzey hızı (m/s)
    vy: float = 0.0              # Doğu hızı (m/s)
    vz: float = 0.0              # Dikey hız (m/s)
    roll: float = 0.0            # Yatış (derece)
    pitch: float = 0.0           # Dikilme (derece)
    yaw: float = 0.0             # Yönelme (derece, 0: Kuzey, 90: Doğu)
    speed: float = 20.0          # Yer hızı (m/s)


@dataclass
class DogfightStepResult:
    """Simülasyonun tek bir zaman adımındaki çıktıları."""
    sim_time: float
    blue_state: AircraftState
    red_state: AircraftState
    distance_m: float
    target_in_fov: bool
    target_box: Optional[HedefKutusu]
    lock_status: KilitDurumu
    lock_progress: float
    successful_locks: int


class DogfightSimulator:
    """
    3D Taktik İt Dalaşı Simülatörü.
    """
    def __init__(
        self,
        img_width: int = 1280,
        img_height: int = 720,
        hfov_deg: float = 80.0,
        vfov_deg: float = 50.0,
        dt: float = 0.05,        # 20 Hz simülasyon adımı
        lock_engine: Optional[LockEngine] = None
    ):
        self.dt = dt
        self.img_w = img_width
        self.img_h = img_height
        self.hfov = hfov_deg
        self.vfov = vfov_deg
        
        self.lock_engine = lock_engine or LockEngine(
            gerekli_sure_sn=4.0,
            hedef_alan_orani_min=0.05,
            kayip_toleransi_sn=0.35
        )
        self.dummy_frame = np.zeros((self.img_h, self.img_w, 3), dtype=np.uint8)
        
        self.sim_time = 0.0
        self.successful_locks = 0
        
        # Mavi İHA başlangıç (Takip eden bizim uçağımız)
        self.blue = AircraftState(x=0.0, y=0.0, z=80.0, speed=22.0, yaw=0.0)
        # Kırmızı İHA başlangıç (Öndeki hedef)
        self.red = AircraftState(x=70.0, y=10.0, z=82.0, speed=19.0, yaw=0.0)
        self.red_behavior = TargetBehavior.WEAVE

    def reset(
        self,
        blue_pos: Tuple[float, float, float] = (0.0, 0.0, 80.0),
        red_pos: Tuple[float, float, float] = (60.0, 5.0, 80.0),
        behavior: TargetBehavior = TargetBehavior.WEAVE
    ) -> None:
        """Simülasyon ortamını sıfırlar."""
        self.blue = AircraftState(x=blue_pos[0], y=blue_pos[1], z=blue_pos[2], speed=22.0, yaw=0.0)
        self.red = AircraftState(x=red_pos[0], y=red_pos[1], z=red_pos[2], speed=19.0, yaw=0.0)
        self.red_behavior = behavior
        self.sim_time = 0.0
        self.successful_locks = 0
        self.lock_engine.reset()

    def step(self) -> DogfightStepResult:
        """
        Simülasyonu 1 adım (dt) ilerletir.
        """
        self.sim_time += self.dt
        
        # 1. Kırmızı Uçak Manevrasını Güncelle
        self._update_red_dynamics()
        
        # 2. Mavi Uçak Otomatik Takip Güdümünü Çalıştır (Oransal Seyrüsefer / Lead Pursuit)
        self._update_blue_guidance()
        
        # 3. Kırmızı Uçağın Mavi Kamerasına İzdüşümünü Hesapla
        target_box, in_fov = self._project_to_camera()
        
        # 4. Kilitlenme Motorunu Güncelle
        status, elapsed, locked_box = self.lock_engine.update(
            frame=self.dummy_frame,
            hedefler=[target_box] if (target_box and in_fov) else []
        )
        lock_progress = min(100.0, (elapsed / max(0.01, self.lock_engine.gerekli_sure_sn)) * 100.0)
        
        if status == KilitDurumu.LOCKED:
            self.successful_locks += 1
            
        dx = self.red.x - self.blue.x
        dy = self.red.y - self.blue.y
        dz = self.red.z - self.blue.z
        dist = math.sqrt(dx ** 2 + dy ** 2 + dz ** 2)

        return DogfightStepResult(
            sim_time=round(self.sim_time, 2),
            blue_state=self.blue,
            red_state=self.red,
            distance_m=round(dist, 1),
            target_in_fov=in_fov,
            target_box=target_box,
            lock_status=status,
            lock_progress=round(lock_progress, 1),
            successful_locks=self.successful_locks
        )

    def _update_red_dynamics(self) -> None:
        """Kırmızı İHA uçuş hareketini günceller."""
        t = self.sim_time
        if self.red_behavior == TargetBehavior.ORBIT:
            turn_rate = 12.0 # deg/sec
            self.red.yaw = (self.red.yaw + turn_rate * self.dt) % 360.0
            self.red.roll = 25.0
        elif self.red_behavior == TargetBehavior.WEAVE:
            # S-dönüşleri (Sinüs dalgası yönelme)
            turn_rate = 18.0 * math.sin(t * 0.8)
            self.red.yaw = (self.red.yaw + turn_rate * self.dt) % 360.0
            self.red.roll = turn_rate * 1.5
        elif self.red_behavior == TargetBehavior.AGGRESSIVE_BFM:
            # 3 saniyede bir sert yön değiştirme
            cycle = int(t / 3.0) % 2
            turn_rate = 32.0 if cycle == 0 else -32.0
            self.red.yaw = (self.red.yaw + turn_rate * self.dt) % 360.0
            self.red.roll = 45.0 if cycle == 0 else -45.0
        elif self.red_behavior == TargetBehavior.HEAD_ON:
            self.red.yaw = 180.0 # Bize doğru geliyor
            self.red.roll = 0.0

        yaw_rad = math.radians(self.red.yaw)
        self.red.x += self.red.speed * math.cos(yaw_rad) * self.dt
        self.red.y += self.red.speed * math.sin(yaw_rad) * self.dt

    def _update_blue_guidance(self) -> None:
        """Mavi İHA'nın hedefi takip eden güdüm dinamiği."""
        dx = self.red.x - self.blue.x
        dy = self.red.y - self.blue.y
        target_bearing = math.degrees(math.atan2(dy, dx)) % 360.0
        
        # Açı farkı
        yaw_err = (target_bearing - self.blue.yaw + 180.0) % 360.0 - 180.0
        
        # Maksimum dönüş hızı sınırı (örneğin 25 deg/s)
        max_turn_rate = 25.0
        turn_cmd = max(-max_turn_rate, min(max_turn_rate, yaw_err * 2.0))
        
        self.blue.yaw = (self.blue.yaw + turn_cmd * self.dt) % 360.0
        self.blue.roll = max(-45.0, min(45.0, turn_cmd * 1.8))
        
        # İrtifa eşitleme
        dz = self.red.z - self.blue.z
        self.blue.z += max(-3.0, min(3.0, dz * 1.5)) * self.dt
        
        yaw_rad = math.radians(self.blue.yaw)
        self.blue.x += self.blue.speed * math.cos(yaw_rad) * self.dt
        self.blue.y += self.blue.speed * math.sin(yaw_rad) * self.dt

    def _project_to_camera(self) -> Tuple[Optional[HedefKutusu], bool]:
        """Kırmızı uçağın Mavi uçağın kamera ekranına 2D izdüşümünü ve bounding box'ını hesaplar."""
        dx = self.red.x - self.blue.x
        dy = self.red.y - self.blue.y
        dz = self.red.z - self.blue.z
        
        # Mavi uçağın gövde eksenine dönüşüm
        psi = math.radians(self.blue.yaw)
        c_psi, s_psi = math.cos(psi), math.sin(psi)
        
        x_body = dx * c_psi + dy * s_psi      # İleri (m)
        y_body = -dx * s_psi + dy * c_psi     # Sağ (m)
        z_body = dz                           # Yukarı (m)
        
        # Kamera önünde değilse (arkamızda ise) kadrajda olamaz
        if x_body <= 2.0:
            return None, False
            
        # Açısal sapmalar (Azimut ve Elevasyon)
        azimuth_deg = math.degrees(math.atan2(y_body, x_body))
        elevation_deg = math.degrees(math.atan2(z_body, x_body))
        
        # FOV kontrolü
        in_fov = (abs(azimuth_deg) <= self.hfov / 2.0) and (abs(elevation_deg) <= self.vfov / 2.0)
        
        # Ekran merkez koordinatları
        cx = self.img_w / 2.0
        cy = self.img_h / 2.0
        
        # Piksel izdüşümü
        px = cx + (azimuth_deg / (self.hfov / 2.0)) * cx
        py = cy - (elevation_deg / (self.vfov / 2.0)) * cy
        
        # Hedefin piksel boyutu (mesafeyle ters orantılı)
        dist = math.sqrt(dx ** 2 + dy ** 2 + dz ** 2)
        # 50 metrede %6 ekran kaplasın
        box_w = max(10.0, (self.img_w * 0.28 * 50.0) / max(5.0, dist))
        box_h = box_w * 0.45
        
        x1 = max(0.0, px - box_w / 2.0)
        y1 = max(0.0, py - box_h / 2.0)
        x2 = min(float(self.img_w), px + box_w / 2.0)
        y2 = min(float(self.img_h), py + box_h / 2.0)
        
        box = HedefKutusu(
            x1=round(x1, 1),
            y1=round(y1, 1),
            x2=round(x2, 1),
            y2=round(y2, 1),
            conf=0.92,
            track_id=1,
            class_name="iha"
        )
        return box, in_fov

    def run_simulation(self, duration_s: float = 10.0) -> Dict[str, Any]:
        """
        Belirtilen süre boyunca simülasyonu adım adım koşturur ve özet istatistik döndürür.
        """
        steps = int(duration_s / self.dt)
        in_fov_steps = 0
        locking_steps = 0
        min_dist = float("inf")
        
        for _ in range(steps):
            res = self.step()
            if res.target_in_fov:
                in_fov_steps += 1
            if res.lock_status in (KilitDurumu.LOCKING, KilitDurumu.LOCKED):
                locking_steps += 1
            if res.distance_m < min_dist:
                min_dist = res.distance_m

        return {
            "total_sim_time_s": duration_s,
            "fov_occupancy_pct": round((in_fov_steps / max(1, steps)) * 100.0, 1),
            "locking_time_s": round(locking_steps * self.dt, 2),
            "successful_locks": self.successful_locks,
            "minimum_distance_m": min_dist,
            "final_distance_m": res.distance_m
        }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AeroCombat 3D Dogfight SITL Simulator")
    parser.add_argument("--duration", type=float, default=10.0, help="Simülasyon süresi (saniye)")
    parser.add_argument("--behavior", type=str, default="WEAVE", choices=["ORBIT", "WEAVE", "AGGRESSIVE_BFM", "HEAD_ON"])
    args = parser.parse_args()

    sim = DogfightSimulator()
    sim.reset(behavior=TargetBehavior(args.behavior))
    print(f"\n[Dogfight Simulator] Simülasyon başlatılıyor: Davranış={args.behavior}, Süre={args.duration}s")
    summary = sim.run_simulation(duration_s=args.duration)
    print("\n--- SIMULASYON SONUC RAPORU ---")
    for k, v in summary.items():
        print(f" {k:<25}: {v}")
    print("--------------------------------\n")
