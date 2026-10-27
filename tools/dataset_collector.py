import os
import cv2
import argparse
from core.logger import logger


def extract_frames_from_video(
    video_path: str,
    output_dir: str = "dataset/raw_frames",
    sample_every_n_frames: int = 5
):
    """Uçuş videolarından model eğitimi için kareleri çıkarır."""
    if not os.path.exists(video_path):
        logger.error(f"Video bulunamadı: {video_path}")
        return

    os.makedirs(output_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    count = 0
    saved = 0

    video_name = os.path.splitext(os.path.basename(video_path))[0]
    logger.info(f"Kare çıkarma başlatılıyor: {video_path}")

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        if count % sample_every_n_frames == 0:
            frame_name = f"{video_name}_f{count:06d}.jpg"
            save_path = os.path.join(output_dir, frame_name)
            cv2.imwrite(save_path, frame)
            saved += 1

        count += 1

    cap.release()
    logger.info(f"İşlem tamamlandı! Toplam {saved} adet eğitim karesi kaydedildi -> {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TEKNOFEST Uçuş Videosundan Eğitim Veri Seti Çıkarıcı")
    parser.add_argument("--video", type=str, required=True, help="Video dosya yolu (.mp4)")
    parser.add_argument("--output", type=str, default="dataset/images", help="Çıktı klasörü")
    parser.add_argument("--step", type=int, default=5, help="Kaç karede bir kaydedilsin")
    args = parser.parse_args()

    extract_frames_from_video(args.video, args.output, args.step)
