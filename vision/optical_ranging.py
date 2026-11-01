"""
Monoküler Görsel Menzil ve 3 Boyutlu Konum Kestirimi (Optical Target Ranging & 3D Estimation).
Kamera iğne deliği (pinhole) optik modeli ve bilinen hedef kanat açıklığı/gövde boyutları üzerinden
lazer veya radar kullanmaksızın hedefin 3D bağıl mesafesini (slant range) ve NED konumunu hesaplar.
"""

import math
from dataclasses import dataclass
from typing import Tuple, Optional, Dict, Any
from core.models import HedefKutusu


@dataclass
class OpticalRangingResult:
    """Monoküler görsel menzil kestirim sonucu."""
    slant_range_m: float           # 3D doğrudan kuş uçuşu mesafe (m)
    x_cam_m: float                 # Kamera koordinat sistemi X ekseni (sağ, m)
    y_cam_m: float                 # Kamera koordinat sistemi Y ekseni (aşağı, m)
    z_cam_m: float                 # Kamera koordinat sistemi Z ekseni (derinlik / optik eksen, m)
    azimuth_deg: float             # Görüş açısı yatay sapma (derece, +sağ, -sol)
    elevation_deg: float           # Görüş açısı dikey sapma (derece, +yukarı, -aşağı)
    in_wez: bool                   # Hedef angajman / kilitlenme bölgesinde mi? (Weapon Engagement Zone)
    estimated_wingspan_px: float   # Algılanan piksel genişliği


class OpticalRanger:
    """
    Kamera kalibrasyon parametreleri ile monoküler hedef menzili ve 3D konum kestiricisi.
    """
    def __init__(
        self,
        img_width: int = 1280,
        img_height: int = 720,
        hfov_deg: float = 84.0,
        assumed_target_wingspan_m: float = 1.20,
        min_engagement_range_m: float = 15.0,
        max_engagement_range_m: float = 120.0,
        max_engagement_angle_deg: float = 25.0
    ):
        self.img_width = img_width
        self.img_height = img_height
        self.assumed_wingspan = assumed_target_wingspan_m
        self.min_range = min_engagement_range_m
        self.max_range = max_engagement_range_m
        self.max_angle = max_engagement_angle_deg
        
        # Pinhole fokal uzunluk hesabı: f_x = (W / 2) / tan(HFOV / 2)
        half_hfov_rad = math.radians(hfov_deg / 2.0)
        self.fx = (img_width / 2.0) / math.tan(half_hfov_rad)
        # Kare piksel varsayımı ile fy = fx
        self.fy = self.fx
        self.cx = img_width / 2.0
        self.cy = img_height / 2.0

    def estimate_range(
        self,
        box: HedefKutusu,
        uav_roll_deg: float = 0.0,
        uav_pitch_deg: float = 0.0,
        uav_yaw_deg: float = 0.0,
        target_physical_span_m: Optional[float] = None
    ) -> OpticalRangingResult:
        """
        Hedef kutusundan 3D bağıl pozisyon ve menzil kestirimi yapar.
        """
        span_m = target_physical_span_m or self.assumed_wingspan
        # Hedef genişliği (piksel). Sıfıra bölünmeyi önlemek için en az 1 piksel
        w_px = max(1.0, box.genislik)
        
        # Derinlik (Z): Z = (f * W_real) / w_px
        z_cam = (self.fx * span_m) / w_px
        
        # Kamera koordinatlarında merkez noktası
        u = box.merkez_x
        v = box.merkez_y
        
        x_cam = ((u - self.cx) * z_cam) / self.fx
        y_cam = ((v - self.cy) * z_cam) / self.fy
        
        # 3D Slant Range (Pisagor)
        slant_range = math.sqrt(x_cam ** 2 + y_cam ** 2 + z_cam ** 2)
        
        # Azimut ve Elevasyon açıları
        # Azimut: Yatay düzlem açısı (+: sağ)
        azimuth_deg = math.degrees(math.atan2(x_cam, z_cam))
        # Elevasyon: Dikey düzlem açısı (+: yukarı, -y_cam yukarıyı temsil etmesi için eksi)
        elevation_deg = math.degrees(math.atan2(-y_cam, z_cam))
        
        # Weapon Engagement Zone (WEZ) kontrolü
        total_off_boresight = math.sqrt(azimuth_deg ** 2 + elevation_deg ** 2)
        in_range = self.min_range <= slant_range <= self.max_range
        in_angle = total_off_boresight <= self.max_angle
        in_wez = in_range and in_angle

        return OpticalRangingResult(
            slant_range_m=round(slant_range, 2),
            x_cam_m=round(x_cam, 2),
            y_cam_m=round(y_cam, 2),
            z_cam_m=round(z_cam, 2),
            azimuth_deg=round(azimuth_deg, 2),
            elevation_deg=round(elevation_deg, 2),
            in_wez=in_wez,
            estimated_wingspan_px=round(w_px, 1)
        )

    def camera_to_ned(
        self,
        optical_res: OpticalRangingResult,
        uav_roll_deg: float,
        uav_pitch_deg: float,
        uav_yaw_deg: float
    ) -> Tuple[float, float, float]:
        """
        Kamera koordinatlarındaki vektörü (X_cam, Y_cam, Z_cam)
        Uçağın yönelimine (Roll, Pitch, Yaw) göre Kuzey-Doğu-Aşağı (NED) bağıl fark vektörüne dönüştürür.
        Kamera uçağın burnuna ileri doğru monte edilmiş varsayılır:
        Gövde Frame (Body): X_b = Z_cam (İleri), Y_b = X_cam (Sağ), Z_b = Y_cam (Aşağı).
        """
        # Gövde eksenine dönüşüm
        x_b = optical_res.z_cam_m
        y_b = optical_res.x_cam_m
        z_b = optical_res.y_cam_m
        
        # Euler açıları (Radyan)
        phi = math.radians(uav_roll_deg)
        theta = math.radians(uav_pitch_deg)
        psi = math.radians(uav_yaw_deg)
        
        c_phi, s_phi = math.cos(phi), math.sin(phi)
        c_th, s_th = math.cos(theta), math.sin(theta)
        c_psi, s_psi = math.cos(psi), math.sin(psi)
        
        # Yönelim Dönüşüm Matrisi (Rotation Matrix R_body_to_ned = R_z(psi) * R_y(theta) * R_x(phi))
        r11 = c_th * c_psi
        r12 = s_phi * s_th * c_psi - c_phi * s_psi
        r13 = c_phi * s_th * c_psi + s_phi * s_psi
        
        r21 = c_th * s_psi
        r22 = s_phi * s_th * s_psi + c_phi * c_psi
        r23 = c_phi * s_th * s_psi - s_phi * c_psi
        
        r31 = -s_th
        r32 = s_phi * c_th
        r33 = c_phi * c_th
        
        delta_north = r11 * x_b + r12 * y_b + r13 * z_b
        delta_east  = r21 * x_b + r22 * y_b + r23 * z_b
        delta_down  = r31 * x_b + r32 * y_b + r33 * z_b
        
        return round(delta_north, 2), round(delta_east, 2), round(delta_down, 2)
