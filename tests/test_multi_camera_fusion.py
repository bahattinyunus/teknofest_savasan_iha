"""
Çift Kamera Görsel Füzyon Birim Testleri.
"""

import pytest
from core.models import HedefKutusu
from vision.multi_camera_fusion import (
    MultiCameraFusion,
    CameraRole,
    FusedTarget
)


def test_multi_camera_fusion_coordinate_transforms():
    fusion = MultiCameraFusion(wide_hfov_deg=90.0, zoom_hfov_deg=35.0, frame_width=1280, frame_height=720)
    
    # Büyütme oranı yaklaşık 2.5 - 3.5 arasında olmalı
    assert 2.5 < fusion.scale_factor < 3.5

    # Tam merkezde 100x100 kutu
    wide_box = HedefKutusu(x1=590.0, y1=310.0, x2=690.0, y2=410.0)
    zoom_box = fusion.wide_to_zoom_coords(wide_box)
    
    # Merkez değişmemeli (cx=640, cy=360)
    assert abs(zoom_box.merkez_x - 640.0) < 0.5
    assert abs(zoom_box.merkez_y - 360.0) < 0.5
    # Boyut büyütme oranı ile büyümeli
    assert zoom_box.genislik > 200.0


def test_multi_camera_fusion_matched_target():
    fusion = MultiCameraFusion(wide_hfov_deg=90.0, zoom_hfov_deg=45.0, frame_width=1280, frame_height=720)
    
    # Geniş kamerada merkezde küçük kutu (60x40 piksel)
    wide_target = HedefKutusu(x1=610.0, y1=340.0, x2=670.0, y2=380.0, conf=0.85, track_id=1)
    
    # Zoom kamerada büyütülmüş karşılığı
    projected = fusion.wide_to_zoom_coords(wide_target)
    zoom_target = HedefKutusu(
        x1=projected.x1,
        y1=projected.y1,
        x2=projected.x2,
        y2=projected.y2,
        conf=0.92,
        track_id=10
    )

    fused_list = fusion.fuse(
        wide_detections=[wide_target],
        zoom_detections=[zoom_target]
    )
    
    assert len(fused_list) == 1
    fused = fused_list[0]
    assert fused.source_camera == CameraRole.FUSED
    assert fused.confidence > 0.90
    assert fused.zoom_box is not None
    assert fused.wide_box is not None
    # Zoom kameradaki kutu daha büyük alan oranına sahip olmalı
    assert fused.effective_area_ratio > wide_target.alan_orani(1280, 720)


def test_multi_camera_fusion_wide_only():
    fusion = MultiCameraFusion()
    # Ekranın çok köşesinde hedef (Zoom kameranın görüş açısının dışında)
    edge_box = HedefKutusu(x1=20.0, y1=20.0, x2=80.0, y2=60.0, conf=0.80, track_id=2)
    
    fused_list = fusion.fuse(
        wide_detections=[edge_box],
        zoom_detections=[]
    )
    assert len(fused_list) == 1
    assert fused_list[0].source_camera == CameraRole.WIDE
    assert fused_list[0].zoom_box is None
