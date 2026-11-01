"""
Optik Hedef Menzili ve 3D Kestirim Birim Testleri.
"""

import pytest
import math
from core.models import HedefKutusu
from vision.optical_ranging import OpticalRanger, OpticalRangingResult


def test_optical_ranging_centered_target():
    ranger = OpticalRanger(
        img_width=1280,
        img_height=720,
        hfov_deg=84.0,
        assumed_target_wingspan_m=1.20
    )
    
    # Tam merkezde kutu (cx=640, cy=360)
    # Genişlik = 100 piksel
    box = HedefKutusu(
        x1=590.0,
        y1=335.0,
        x2=690.0,
        y2=385.0
    )
    
    res = ranger.estimate_range(box)
    assert res.estimated_wingspan_px == 100.0
    # Merkezde olduğu için Azimut ve Elevasyon ~ 0 derece olmalı
    assert abs(res.azimuth_deg) < 0.5
    assert abs(res.elevation_deg) < 0.5
    # Slant range derinlik (Z) ile neredeyse aynı olmalı
    assert abs(res.slant_range_m - res.z_cam_m) < 0.1
    # 100 pikselde mesafe mantıklı aralıkta olmalı (yaklaşık 8 - 15m)
    assert 5.0 < res.slant_range_m < 30.0


def test_optical_ranging_off_center_angles():
    ranger = OpticalRanger(img_width=1280, img_height=720, hfov_deg=80.0)
    
    # Ekranın sağ üst köşesine yakın hedef
    box = HedefKutusu(
        x1=1000.0,
        y1=100.0,
        x2=1100.0,
        y2=150.0
    )
    res = ranger.estimate_range(box)
    
    # Sağda olduğu için Azimut pozitif olmalı
    assert res.azimuth_deg > 0.0
    # Yukarıda olduğu için Elevasyon pozitif olmalı
    assert res.elevation_deg > 0.0
    assert res.x_cam_m > 0.0
    assert res.y_cam_m < 0.0


def test_optical_ranging_camera_to_ned():
    ranger = OpticalRanger()
    res = OpticalRangingResult(
        slant_range_m=50.0,
        x_cam_m=0.0,     # Tam merkez
        y_cam_m=0.0,     # Dikey sapma yok
        z_cam_m=50.0,    # 50m ileri
        azimuth_deg=0.0,
        elevation_deg=0.0,
        in_wez=True,
        estimated_wingspan_px=80.0
    )
    
    # Uçak düz uçuyor, yönelme: 0 (Kuzey)
    dn, de, dd = ranger.camera_to_ned(res, uav_roll_deg=0, uav_pitch_deg=0, uav_yaw_deg=0)
    assert abs(dn - 50.0) < 0.5
    assert abs(de) < 0.5
    assert abs(dd) < 0.5
    
    # Uçak Doğuya dönük (Yaw = 90 deg)
    dn_e, de_e, dd_e = ranger.camera_to_ned(res, uav_roll_deg=0, uav_pitch_deg=0, uav_yaw_deg=90.0)
    assert abs(dn_e) < 0.5
    assert abs(de_e - 50.0) < 0.5
