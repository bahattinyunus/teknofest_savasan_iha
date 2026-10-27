import os
import cv2
import math
import random
import argparse
import numpy as np
from typing import Tuple


def generate_sky_background(width: int, height: int) -> np.ndarray:
    """Rastgele gökyüzü (mavi, bulutlu, günbatımı) gradyanı ve arka planı üretir."""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    sky_type = random.choice(["clear_blue", "overcast", "sunset"])

    if sky_type == "clear_blue":
        top_color = np.array([235, 170, 70])    # Canlı mavi (BGR)
        bottom_color = np.array([255, 230, 180])
    elif sky_type == "sunset":
        top_color = np.array([120, 80, 200])   # Turuncu/mor gökyüzü
        bottom_color = np.array([60, 150, 255])
    else:
        top_color = np.array([180, 180, 180])   # Bulutlu gri
        bottom_color = np.array([210, 210, 210])

    for y in range(height):
        ratio = y / height
        color = (1.0 - ratio) * top_color + ratio * bottom_color
        img[y, :] = color.astype(np.uint8)

    # Rastgele bulut kümeleri
    num_clouds = random.randint(2, 6)
    for _ in range(num_clouds):
        cx = random.randint(0, width)
        cy = random.randint(int(height * 0.1), int(height * 0.7))
        r = random.randint(40, 100)
        cloud_color = (240, 240, 240) if sky_type != "sunset" else (200, 210, 240)
        cv2.circle(img, (cx, cy), r, cloud_color, -1)
        cv2.circle(img, (cx + int(r * 0.5), cy), int(r * 0.8), cloud_color, -1)

    return img


def draw_synthetic_uav(
    img: np.ndarray,
    cx: int,
    cy: int,
    scale: float,
    bank_angle_deg: float
) -> Tuple[int, int, int, int]:
    """Arka plan üzerine rastgele ölçek ve yatış açısında bir İHA çizer ve bounding box döndürür."""
    wing_span = int(140 * scale)
    fuselage_len = int(90 * scale)
    body_color = random.choice([(45, 45, 45), (70, 80, 75), (90, 90, 90), (30, 30, 40)])

    # Kanat dönüşü
    rad = math.radians(bank_angle_deg)
    cos_a = math.cos(rad)
    sin_a = math.sin(rad)

    # Kanat uçları
    x_w1 = int(cx - (wing_span / 2.0) * cos_a)
    y_w1 = int(cy - (wing_span / 2.0) * sin_a)
    x_w2 = int(cx + (wing_span / 2.0) * cos_a)
    y_w2 = int(cy + (wing_span / 2.0) * sin_a)

    # Gövde burun ve kuyruk
    x_nose = int(cx + (fuselage_len * 0.4) * sin_a)
    y_nose = int(cy - (fuselage_len * 0.4) * cos_a)
    x_tail = int(cx - (fuselage_len * 0.6) * sin_a)
    y_tail = int(cy + (fuselage_len * 0.6) * cos_a)

    # Kanat ve gövdeyi çiz
    thickness = max(2, int(8 * scale))
    cv2.line(img, (x_w1, y_w1), (x_w2, y_w2), body_color, thickness, cv2.LINE_AA)
    cv2.line(img, (x_nose, y_nose), (x_tail, y_tail), body_color, int(thickness * 1.3), cv2.LINE_AA)

    # Kuyruk kanadı
    tail_span = int(wing_span * 0.35)
    x_t1 = int(x_tail - (tail_span / 2.0) * cos_a)
    y_t1 = int(y_tail - (tail_span / 2.0) * sin_a)
    x_t2 = int(x_tail + (tail_span / 2.0) * cos_a)
    y_t2 = int(y_tail + (tail_span / 2.0) * sin_a)
    cv2.line(img, (x_t1, y_t1), (x_t2, y_t2), body_color, max(1, int(thickness * 0.7)), cv2.LINE_AA)

    # Bounding Box hesapla
    pts = np.array([[x_w1, y_w1], [x_w2, y_w2], [x_nose, y_nose], [x_tail, y_tail], [x_t1, y_t1], [x_t2, y_t2]])
    x_min, y_min = np.min(pts, axis=0)
    x_max, y_max = np.max(pts, axis=0)

    # Hafif marjin
    pad = int(8 * scale)
    h_img, w_img = img.shape[:2]
    x1 = max(0, int(x_min - pad))
    y1 = max(0, int(y_min - pad))
    x2 = min(w_img - 1, int(x_max + pad))
    y2 = min(h_img - 1, int(y_max + pad))

    return x1, y1, x2, y2


def generate_synthetic_dataset(
    output_dir: str = "dataset/synthetic_uav",
    num_samples: int = 20,
    width: int = 1280,
    height: int = 720
):
    """YOLO eğitim formatında sentetik İHA görüntüleri ve etiketleri üretir."""
    train_img_dir = os.path.join(output_dir, "images", "train")
    train_lbl_dir = os.path.join(output_dir, "labels", "train")
    val_img_dir = os.path.join(output_dir, "images", "val")
    val_lbl_dir = os.path.join(output_dir, "labels", "val")

    for d in [train_img_dir, train_lbl_dir, val_img_dir, val_lbl_dir]:
        os.makedirs(d, exist_ok=True)

    print(f"Sentetik İHA veri seti üretiliyor: {num_samples} adet örnek -> {output_dir}")

    for i in range(num_samples):
        img = generate_sky_background(width, height)
        is_val = (i % 5 == 0)  # %20 validation ayrımı

        img_save_dir = val_img_dir if is_val else train_img_dir
        lbl_save_dir = val_lbl_dir if is_val else train_lbl_dir

        # Hedef konumu ve ölçeği
        scale = random.uniform(0.5, 1.8)
        bank = random.uniform(-40.0, 40.0)
        cx = random.randint(int(width * 0.2), int(width * 0.8))
        cy = random.randint(int(height * 0.2), int(height * 0.7))

        x1, y1, x2, y2 = draw_synthetic_uav(img, cx, cy, scale, bank)

        # Güneş parlaması efekti
        if random.random() > 0.6:
            flare_x = random.randint(0, width)
            flare_y = random.randint(0, int(height * 0.4))
            cv2.circle(img, (flare_x, flare_y), random.randint(30, 70), (255, 255, 255), -1)

        # Dosyaları kaydet
        filename = f"synthetic_uav_{i:05d}"
        img_path = os.path.join(img_save_dir, f"{filename}.jpg")
        lbl_path = os.path.join(lbl_save_dir, f"{filename}.txt")

        cv2.imwrite(img_path, img)

        # YOLO Etiketi: <class_id> <x_center> <y_center> <width> <height> (0.0 - 1.0 normalize)
        box_w = (x2 - x1) / width
        box_h = (y2 - y1) / height
        box_cx = (x1 + (x2 - x1) / 2.0) / width
        box_cy = (y1 + (y2 - y1) / 2.0) / height

        with open(lbl_path, "w", encoding="utf-8") as f:
            f.write(f"0 {box_cx:.6f} {box_cy:.6f} {box_w:.6f} {box_h:.6f}\n")

    # dataset.yaml dosyasını oluştur
    yaml_content = f"""# Ultralytics YOLO Savaşan İHA Sentetik Veri Seti
path: {os.path.abspath(output_dir)}
train: images/train
val: images/val

names:
  0: iha
"""
    yaml_path = os.path.join(output_dir, "dataset.yaml")
    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write(yaml_content)

    print(f"Tamamlandı! Ultralytics YAML dosyası oluşturuldu: {yaml_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YOLO Savaşan İHA Sentetik Veri Seti Üreticisi")
    parser.add_argument("--count", type=int, default=20, help="Üretilecek görsel sayısı")
    parser.add_argument("--output", type=str, default="dataset/synthetic_uav", help="Çıktı klasörü")
    args = parser.parse_args()

    generate_synthetic_dataset(args.output, args.count)
