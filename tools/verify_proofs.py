"""
AeroCombat - Kilitlenme Kanıtı ve Kriptografik Mühür Denetleyici (Proof Auditor CLI)

Bu araç, 'proofs/' klasöründeki kilitlenme kayıtlarını ve 'proof_manifest.json'
manifestolarını tarayarak:
  1. Kriptografik SHA-256 hash zinciri ve Merkle ağacı bütünlüğünü
  2. Sayısal HMAC imzasının geçerliliğini
  3. TEKNOFEST 4.0 saniye kesintisiz kilitlenme kuralını
  4. Ekran alanı >= %5 hedef boyutu kuralını
  5. Hedef merkez toleransını (ekran merkezine <= %35 ofset)
denetler ve hakem heyetine sunulabilir detaylı bir denetim raporu üretir.
"""

import os
import sys
import json
import glob
import hmac
import hashlib
import argparse
from typing import Dict, Any, List, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from referee.proof_chain import CryptographicProofChain


def verify_manifest_file(manifest_path: str, secret_key: str = "AeroCombat-TEKNOFEST-2026-ProofKey") -> Dict[str, Any]:
    """Tek bir manifest dosyasını baştan sona kriptografik ve kural denetiminden geçirir."""
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    lock_id = data.get("lock_id", "UNKNOWN")
    team_id = data.get("team_id", 0)
    duration = data.get("duration_s", 0.0)
    declared_merkle = data.get("merkle_root", "")
    declared_signature = data.get("digital_signature", "")
    declared_final_hash = data.get("final_chain_hash", "")
    records = data.get("records", [])

    errors = []
    warnings = []

    # 1. Kayıt Sayısı Kontrolü
    if not records:
        return {
            "lock_id": lock_id,
            "status": "FAIL",
            "score": 0.0,
            "errors": ["Kayıt dizisi boş (No frames in record)"],
            "warnings": warnings,
            "frames": 0,
            "duration": duration
        }

    # 2. Sıralı Hash Zinciri Doğrulaması
    recalculated_hashes = []
    current_hash = ""

    for idx, r in enumerate(records):
        prev_hash = r.get("previous_hash", "")
        frame_idx = r.get("frame_index", 0)
        ts = r.get("timestamp_s", 0.0)
        f_hash = r.get("frame_hash_sha256", "")
        box = r.get("target_box", {})
        tel = r.get("telemetry_summary", {})
        expected_rec_hash = r.get("record_hash", "")

        # İlk kayıt genesis veya zincir başı
        if idx > 0 and prev_hash != current_hash:
            errors.append(f"Zincir kopukluğu (Blok {idx}): previous_hash uyumsuz!")

        payload = f"{prev_hash}|{frame_idx}|{ts:.4f}|{f_hash}|{json.dumps(box, sort_keys=True)}|{json.dumps(tel, sort_keys=True)}".encode("utf-8")
        computed_block_hash = hashlib.sha256(payload).hexdigest()

        if computed_block_hash != expected_rec_hash:
            errors.append(f"Blok {idx} verisi tahrif edilmiş (Tamper detected)! Hash uyumsuz.")

        current_hash = computed_block_hash
        recalculated_hashes.append(computed_block_hash)

    # Son zincir hash kontrolü
    if current_hash != declared_final_hash:
        errors.append("Son zincir hash değeri declared_final_hash ile uyuşmuyor.")

    # 3. Merkle Ağacı Kök Doğrulaması
    computed_merkle = CryptographicProofChain.compute_merkle_root(recalculated_hashes)
    if computed_merkle != declared_merkle:
        errors.append(f"Merkle kökü geçersiz! Hesaplanan: {computed_merkle[:12]}..., Beyan: {declared_merkle[:12]}...")

    # 4. Sayısal İmza Doğrulaması
    key_bytes = secret_key.encode("utf-8")
    sig_payload = f"{lock_id}|{team_id}|{duration:.3f}|{computed_merkle}|{current_hash}".encode("utf-8")
    expected_sig = hmac.new(key_bytes, sig_payload, hashlib.sha256).hexdigest()

    if expected_sig != declared_signature:
        errors.append("Dijital imza doğrulaması başarısız! Yetkisiz/sahte mühür.")

    # 5. Kural Kontrolleri (TEKNOFEST Şartnamesi)
    if duration < 4.0:
        errors.append(f"Süre kuralı ihlali: {duration:.2f} saniye (< 4.0 saniye)")

    frame_width = 1280
    frame_height = 720
    screen_area = frame_width * frame_height
    cx_screen = frame_width / 2.0
    cy_screen = frame_height / 2.0

    area_violations = 0
    center_violations = 0

    for r in records:
        b = r.get("target_box", {})
        w = max(0.0, b.get("x2", 0) - b.get("x1", 0))
        h = max(0.0, b.get("y2", 0) - b.get("y1", 0))
        box_area = w * h
        if (box_area / screen_area) < 0.05:
            area_violations += 1

        bx = b.get("x1", 0) + w / 2.0
        by = b.get("y1", 0) + h / 2.0
        if (abs(bx - cx_screen) / frame_width > 0.35) or (abs(by - cy_screen) / frame_height > 0.35):
            center_violations += 1

    if area_violations > 0:
        warnings.append(f"{area_violations} karede hedef alanı <%5 tespit edildi.")
    if center_violations > 0:
        warnings.append(f"{center_violations} karede hedef merkez toleransı dışında.")

    is_valid = (len(errors) == 0) and (area_violations == 0) and (center_violations == 0)
    score = 100.0 if is_valid else 0.0

    return {
        "lock_id": lock_id,
        "team_id": team_id,
        "status": "PASS" if is_valid else "FAIL",
        "score": score,
        "errors": errors,
        "warnings": warnings,
        "frames": len(records),
        "duration": duration,
        "merkle_root": computed_merkle[:16] + "..."
    }


def audit_proof_directory(directory_path: str) -> None:
    """Tüm kanıt dizinini tarar ve denetim tablosu yazdırır."""
    print("=" * 78)
    print("      AEROCOMBAT - KRİPTOGRAFİK KİLİTLENME VE HAKEM DENETİM RAPORU      ")
    print("=" * 78)

    search_pattern = os.path.join(directory_path, "**", "proof_manifest.json")
    manifest_files = glob.glob(search_pattern, recursive=True)

    if not manifest_files:
        print(f"[BİLGİ] '{directory_path}' altında incelenecek 'proof_manifest.json' bulunamadı.")
        print("=" * 78)
        return

    print(f"Toplam İncelenen Kanıt Dosyası: {len(manifest_files)}\n")
    print(f"{'DURUM':<8} | {'KİLİT ID':<16} | {'SÜRE(s)':<8} | {'KARE':<6} | {'PUAN':<6} | {'AÇIKLAMA'}")
    print("-" * 78)

    total_score = 0.0
    passed_count = 0

    for m_file in manifest_files:
        res = verify_manifest_file(m_file)
        status = res["status"]
        if status == "PASS":
            passed_count += 1
            total_score += res["score"]

        note = "Kural Uygun" if status == "PASS" else "; ".join(res["errors"][:2])
        print(f"{status:<8} | {res['lock_id'][:16]:<16} | {res['duration']:<8.2f} | {res['frames']:<6} | {res['score']:<6.0f} | {note}")

    print("-" * 78)
    print(f">> ÖZET: {passed_count}/{len(manifest_files)} Geçerli Kilitlenme | Toplam Hakem Puanı: {total_score:.0f}")
    print("=" * 78)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TEKNOFEST Kilitlenme Kanıtı Kriptografik Denetleyici")
    parser.add_argument("--proof-dir", type=str, default="proofs", help="Kanıt dosyaları ana dizini")
    parser.add_argument("--file", type=str, default=None, help="Doğrudan belirli bir proof_manifest.json dosyası")
    args = parser.parse_args()

    if args.file:
        res = verify_manifest_file(args.file)
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        audit_proof_directory(args.proof_dir)
