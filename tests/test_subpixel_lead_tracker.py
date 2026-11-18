from core.models import HedefKutusu
from vision.subpixel_lead_tracker import SubPixelDynamicLeadCompensator


def test_subpixel_lead_compensator_stabilizes_5_percent_box_and_computes_lead():
    comp = SubPixelDynamicLeadCompensator(frame_width=1280, frame_height=720, lead_horizon_s=0.15)

    # 260x190 = 49,400 px^2 -> 1280x720 (921,600) ekranın %5.36'sı
    sol = None
    for k in range(10):
        cx = 600.0 + k * 6.0
        cy = 360.0 - k * 2.0
        box = HedefKutusu(
            x1=cx - 130.0,
            y1=cy - 95.0,
            x2=cx + 130.0,
            y2=cy + 95.0,
            conf=0.93,
            track_id=5
        )
        sol = comp.refine_and_compute_lead(box=box, dt=0.04, own_p_rad_s=0.02, own_q_rad_s=-0.01, own_r_rad_s=0.05)

    assert sol is not None
    assert sol.is_within_5_percent_rule is True
    assert sol.stabilized_area_ratio_pct >= 5.0
    # Hedef sağa (+x) hareket ettiği için önleme nişangahı (lead reticle) mevcut merkezden sağda olmalı
    assert sol.lead_reticle_xy[0] > sol.subpixel_center_xy[0]
