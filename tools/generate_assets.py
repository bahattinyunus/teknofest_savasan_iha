"""
AeroCombat Görsel Varlık Üreticisi (Asset Generator).
Sistem HUD'ı, radar minimap'i, çift kamera karşılaştırması ve taktiksel devriye rotalarını
yüksek çözünürlüklü PNG formatında docs/assets/ dizinine kaydeder.
"""

import os
import sys
import math

# Proje ana dizinini Python yoluna ekle
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
import cv2
import matplotlib.pyplot as plt
from core.models import HedefKutusu, KilitDurumu, TelemetriPaketi, RakipIHABilgisi, HSSBolgesi
from vision.visualizer import HUDVisualizer
from vision.tactical_radar import TacticalRadarMinimap
from vision.multi_camera_fusion import MultiCameraFusion
from autopilot.mission_planner import TacticalMissionPlanner, SearchPattern


def ensure_asset_dir():
    os.makedirs("docs/assets", exist_ok=True)


def generate_hud_screenshot():
    """Gerçek HUDVisualizer ile askeri standartta canlı kilitlenme ekranı üretir."""
    w, h = 1280, 720
    # Gerçekçi gradyanlı gökyüzü ve bulut arka planı
    frame = np.zeros((h, w, 3), dtype=np.uint8)
    for y in range(h):
        # Üst kısım koyu lacivert gök, alt kısım ufuk mavisi
        ratio = y / h
        b = int(140 + 40 * ratio)
        g = int(80 + 30 * ratio)
        r = int(30 + 20 * ratio)
        frame[y, :] = (b, g, r)

    # Ufuk çizgisi altına hafif dağ / arazi silüeti
    cv2.circle(frame, (200, 750), 300, (45, 65, 35), -1)
    cv2.circle(frame, (600, 780), 350, (50, 70, 40), -1)
    cv2.circle(frame, (1100, 740), 280, (40, 60, 30), -1)

    # Hedef İHA silüeti (Merkez yakınında)
    target_cx, target_cy = 670, 350
    # Gövde ve kanatlar
    cv2.line(frame, (target_cx - 45, target_cy), (target_cx + 45, target_cy), (35, 35, 35), 4) # Kanat
    cv2.line(frame, (target_cx, target_cy - 12), (target_cx, target_cy + 18), (35, 35, 35), 6) # Gövde
    cv2.line(frame, (target_cx - 18, target_cy + 14), (target_cx + 18, target_cy + 14), (40, 40, 40), 3) # Arka kanat

    # HUD Visualizer ile askeri göstergeleri bindir
    visualizer = HUDVisualizer()
    
    # 6.2% alan kaplayan hedef kutusu
    box = HedefKutusu(
        x1=target_cx - 110,
        y1=target_cy - 55,
        x2=target_cx + 110,
        y2=target_cy + 55,
        conf=0.95,
        track_id=1,
        class_name="iha"
    )

    telem = TelemetriPaketi(
        takim_numarasi=1,
        IHA_enlem=41.1000,
        IHA_boylam=28.9000,
        IHA_irtifa=84.5,
        IHA_dikilme=3.2,
        IHA_yonelme=42.0,
        IHA_yatis=-8.5,
        IHA_hiz=22.4,
        IHA_batarya=88,
        IHA_otonom=1,
        IHA_kilitlenme=1,
        Hedef_merkez_X=target_cx,
        Hedef_merkez_Y=target_cy,
        Hedef_genislik=220,
        Hedef_yukseklik=110
    )
    
    hud_frame = visualizer.draw_hud(
        frame=frame,
        boxes=[box],
        lock_status=KilitDurumu.LOCKING,
        lock_duration=2.85,
        target_box=box,
        telemetry=telem,
        fps=31.5,
        req_lock_time=4.0,
        min_area_ratio=0.05
    )

    out_path = "docs/assets/hud_lockon_sample.png"
    cv2.imwrite(out_path, hud_frame)
    print(f"[+] HUD kilitlenme görseli üretildi: {out_path}")


def generate_radar_sample():
    """2D Askeri Taktik Hava Muharebe Radarı (ASD) görselini üretir."""
    radar = TacticalRadarMinimap(size=360, max_range_m=160.0)
    
    own_telemetry = TelemetriPaketi(
        takim_numarasi=1,
        IHA_enlem=41.1000,
        IHA_boylam=28.9000,
        IHA_irtifa=85.0,
        IHA_dikilme=2.0,
        IHA_yonelme=45.0,
        IHA_yatis=0.0,
        IHA_hiz=21.0,
        IHA_batarya=92,
        IHA_otonom=1,
        IHA_kilitlenme=1,
        Hedef_merkez_X=640,
        Hedef_merkez_Y=360,
        Hedef_genislik=120,
        Hedef_yukseklik=60
    )

    rivals = [
        RakipIHABilgisi(takim_numarasi=3, IHA_enlem=41.1006, IHA_boylam=28.9008, IHA_irtifa=92.0, IHA_dikilme=0.0, IHA_yonelme=220.0, IHA_yatis=0.0),
        RakipIHABilgisi(takim_numarasi=7, IHA_enlem=41.0993, IHA_boylam=28.8992, IHA_irtifa=80.0, IHA_dikilme=0.0, IHA_yonelme=60.0, IHA_yatis=0.0),
        RakipIHABilgisi(takim_numarasi=12, IHA_enlem=41.1009, IHA_boylam=28.8988, IHA_irtifa=110.0, IHA_dikilme=0.0, IHA_yonelme=135.0, IHA_yatis=0.0),
    ]

    hss_zones = [
        HSSBolgesi(hss_id=1, merkez_enlem=41.0995, merkez_boylam=28.9015, yaricap_m=45.0, alt_irtifa_m=0.0, ust_irtifa_m=120.0)
    ]

    radar_img = radar.render_radar(
        own_tel=own_telemetry,
        rivals=rivals,
        hss_list=hss_zones,
        lock_status=KilitDurumu.LOCKING
    )

    # Arka plana yüksek kontrastlı koyu panel ekle
    panel = np.zeros((440, 440, 3), dtype=np.uint8)
    panel[:] = (18, 22, 26)
    rh, rw = radar_img.shape[:2]
    ox, oy = (440 - rw) // 2, (440 - rh) // 2
    panel[oy:oy+rh, ox:ox+rw] = radar_img
    
    cv2.putText(panel, "AEROCOMBAT 2D TACTICAL RADAR", (45, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(panel, "SCALE: 50m / 100m / 150m RINGS", (45, 420), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA)

    out_path = "docs/assets/radar_minimap_sample.png"
    cv2.imwrite(out_path, panel)
    print(f"[+] Taktik radar görseli üretildi: {out_path}")


def generate_mission_patterns_plot():
    """Taktiksel Arama Desenlerini (Creeping Line, Figure-8, Orbit) şık bir grafikte çizer."""
    planner = TacticalMissionPlanner()
    polygon = [
        [41.100, 28.900],
        [41.100, 28.912],
        [41.108, 28.912],
        [41.108, 28.900],
        [41.100, 28.900]
    ]

    # Matplotlib stil
    plt.style.use('dark_background')
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), facecolor='#11151c')

    # 1. Creeping Line
    ax1 = axes[0]
    ax1.set_facecolor('#181f2a')
    poly_y = [p[0] for p in polygon]
    poly_x = [p[1] for p in polygon]
    ax1.plot(poly_x, poly_y, 'r--', linewidth=1.8, label="Geofence Sınırı")
    
    wps1 = planner.generate_creeping_line(polygon[:-1], spacing_m=120.0)
    w1_x = [w.lon for w in wps1]
    w1_y = [w.lat for w in wps1]
    ax1.plot(w1_x, w1_y, color='#00e5ff', marker='o', markersize=4, linestyle='-', linewidth=2, label="Creeping Line (Zikzak)")
    ax1.plot(w1_x[0], w1_y[0], 'go', markersize=8, label="Başlangıç")
    ax1.set_title("1. Creeping Line (Geniş Alan Arama)", color='#00e5ff', fontsize=11, fontweight='bold')
    ax1.grid(True, linestyle=':', alpha=0.3, color='#455a64')
    ax1.legend(loc='lower left', fontsize=8)

    # 2. Figure-8 (Sekiz Deseni)
    ax2 = axes[1]
    ax2.set_facecolor('#181f2a')
    ax2.plot(poly_x, poly_y, 'r--', linewidth=1.5, alpha=0.5)
    wps2 = planner.generate_figure_8(center_lat=41.104, center_lon=28.906, radius_m=140.0, points_per_loop=14)
    w2_x = [w.lon for w in wps2]
    w2_y = [w.lat for w in wps2]
    ax2.plot(w2_x, w2_y, color='#76ff03', marker='s', markersize=4, linestyle='-', linewidth=2, label="Figure-8 (Sekiz)")
    ax2.plot(28.906, 41.104, 'yo', markersize=8, label="Merkez")
    ax2.set_title("2. Figure-8 (Sürekli Hız & 360° Tarama)", color='#76ff03', fontsize=11, fontweight='bold')
    ax2.grid(True, linestyle=':', alpha=0.3, color='#455a64')
    ax2.legend(loc='lower left', fontsize=8)

    # 3. Dynamic Intercept & Orbit
    ax3 = axes[2]
    ax3.set_facecolor('#181f2a')
    ax3.plot(poly_x, poly_y, 'r--', linewidth=1.5, alpha=0.5)
    wps3 = planner.generate_orbit(center_lat=41.104, center_lon=28.906, radius_m=180.0, num_points=16)
    w3_x = [w.lon for w in wps3]
    w3_y = [w.lat for w in wps3]
    ax3.plot(w3_x, w3_y, color='#ffd600', linestyle='-', linewidth=2, label="Orbit Devriye")
    # Intercept vektörü
    ax3.annotate("", xy=(28.909, 41.106), xytext=(28.904, 41.103),
                 arrowprops=dict(facecolor='#ff1744', edgecolor='#ff1744', width=2, headwidth=8))
    ax3.plot([28.909], [41.106], 'r*', markersize=12, label="Hedef İHA Önleme")
    ax3.set_title("3. Orbit & Taktiksel Önleme (Intercept)", color='#ffd600', fontsize=11, fontweight='bold')
    ax3.grid(True, linestyle=':', alpha=0.3, color='#455a64')
    ax3.legend(loc='lower left', fontsize=8)

    plt.tight_layout()
    out_path = "docs/assets/mission_patterns.png"
    plt.savefig(out_path, dpi=200, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()
    print(f"[+] Görev arama desenleri grafiği üretildi: {out_path}")


def generate_dual_camera_comparison():
    """Geniş (90°) ve Zoom (35°) kamera büyütme avantajını gösteren yan yana görsel üretir."""
    w, h = 640, 480
    fusion = MultiCameraFusion(wide_hfov_deg=90.0, zoom_hfov_deg=35.0, frame_width=w, frame_height=h)

    # 1. Geniş Açı Kare (Uzakta küçük hedef)
    wide_img = np.zeros((h, w, 3), dtype=np.uint8)
    for y in range(h):
        wide_img[y, :] = (int(140 + 30 * y/h), int(80 + 20 * y/h), 30)
    
    # Küçük hedef (30x15 px -> alan oranı %0.15)
    tw_w, tw_h = 32, 16
    cx, cy = w // 2, h // 2
    cv2.rectangle(wide_img, (cx - tw_w//2, cy - tw_h//2), (cx + tw_w//2, cy + tw_h//2), (0, 255, 255), 2)
    cv2.putText(wide_img, "WIDE FOV (90 deg)", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    cv2.putText(wide_img, f"Hedef Boyutu: {tw_w}x{tw_h} px", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 220, 220), 1)
    cv2.putText(wide_img, "Alan Orani: %0.16 [YETERRSIZ]", (20, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

    # 2. Dar Açı Zoom Kare (Aynı hedef 2.6x optik büyütülmüş)
    zoom_img = np.zeros((h, w, 3), dtype=np.uint8)
    for y in range(h):
        zoom_img[y, :] = (int(135 + 30 * y/h), int(75 + 20 * y/h), 25)

    scale = fusion.scale_factor
    tz_w, tz_h = int(tw_w * scale), int(tw_h * scale)
    cv2.rectangle(zoom_img, (cx - tz_w//2, cy - tz_h//2), (cx + tz_w//2, cy + tz_h//2), (0, 255, 0), 2)
    cv2.circle(zoom_img, (cx, cy), 5, (0, 255, 0), -1)
    
    cv2.putText(zoom_img, f"TELEPHOTO ZOOM ({scale:.1f}x)", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    cv2.putText(zoom_img, f"Hedef Boyutu: {tz_w}x{tz_h} px", (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (220, 220, 220), 1)
    cv2.putText(zoom_img, f"Alan Orani: %{(tz_w*tz_h)/(w*h)*100:.2f} [UYGUN - KILIT BASLADI]", (20, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)

    # Yan yana birleştir
    combined = np.hstack([wide_img, zoom_img])
    cv2.line(combined, (w, 0), (w, h), (255, 255, 255), 2)

    out_path = "docs/assets/dual_camera_fov_comparison.png"
    cv2.imwrite(out_path, combined)
    print(f"[+] Çift kamera karşılaştırma görseli üretildi: {out_path}")


if __name__ == "__main__":
    ensure_asset_dir()
    generate_hud_screenshot()
    generate_radar_sample()
    generate_mission_patterns_plot()
    generate_dual_camera_comparison()
