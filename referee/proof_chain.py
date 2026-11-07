"""
AeroCombat - Kriptografik Kilitlenme Kanıt Zinciri (Cryptographic Proof Chain)

TEKNOFEST Savaşan İHA yarışmasında otonom kilitlenme kanıtlarının sonradan manipüle
edilmediğini ve 4.0 saniye, %5 alan, merkez toleransı kurallarını eksiksiz sağladığını
matematiksel ve kriptografik olarak ispatlayan SHA-256 / HMAC Merkle blok zinciri mimarisi.
"""

import os
import json
import time
import hmac
import hashlib
from typing import List, Dict, Any, Optional
import numpy as np

from core.models import HedefKutusu, TelemetriPaketi, ProofRecord, ProofChainManifest
from core.logger import logger


class CryptographicProofChain:
    """
    Her kilitlenme oturumu için kurcalamaya karşı korumalı (tamper-evident)
    sıralı kriptografik hash zinciri ve Merkle ağacı üreticisi.
    """

    def __init__(self, secret_key: str = "AeroCombat-TEKNOFEST-2026-ProofKey"):
        self.secret_key = secret_key.encode("utf-8")
        self.is_active = False
        self.lock_id: str = ""
        self.team_id: int = 1
        self.start_time: float = 0.0
        self.records: List[ProofRecord] = []
        self._current_hash: str = ""

    def start_chain(self, lock_id: str, team_id: int = 1, timestamp_s: Optional[float] = None) -> None:
        """Yeni bir kilitlenme için Genesis (başlangıç) bloğu ile zinciri açar."""
        self.lock_id = lock_id
        self.team_id = team_id
        self.start_time = timestamp_s if timestamp_s is not None else time.time()
        self.records = []

        genesis_payload = f"GENESIS:{lock_id}:{team_id}:{self.start_time:.6f}".encode("utf-8")
        self._current_hash = hmac.new(self.secret_key, genesis_payload, hashlib.sha256).hexdigest()
        self.is_active = True

    def add_frame_proof(
        self,
        frame_index: int,
        frame: np.ndarray,
        target_box: HedefKutusu,
        telemetry: Optional[TelemetriPaketi] = None,
        timestamp_s: Optional[float] = None
    ) -> ProofRecord:
        """Kilitlenme anındaki kareyi ve telemetriyi zincire yeni bir kriptografik halka olarak ekler."""
        if not self.is_active:
            raise RuntimeError("Proof chain aktif değil. Önce start_chain() çağrılmalı.")

        ts = timestamp_s if timestamp_s is not None else time.time()

        # Kare baytlarının SHA-256 özeti
        frame_bytes = frame.tobytes()
        frame_hash = hashlib.sha256(frame_bytes).hexdigest()

        # Hedef kutusu özeti
        box_dict = {
            "x1": round(float(target_box.x1), 2),
            "y1": round(float(target_box.y1), 2),
            "x2": round(float(target_box.x2), 2),
            "y2": round(float(target_box.y2), 2),
            "conf": round(float(target_box.conf), 3),
            "track_id": target_box.track_id
        }

        # Telemetri özeti
        tel_dict = {}
        if telemetry is not None:
            tel_dict = {
                "lat": round(float(telemetry.IHA_enlem), 6),
                "lon": round(float(telemetry.IHA_boylam), 6),
                "alt": round(float(telemetry.IHA_irtifa), 2),
                "yaw": round(float(telemetry.IHA_yonelme), 1),
                "speed": round(float(telemetry.IHA_hiz), 1)
            }

        prev_hash = self._current_hash
        block_payload = f"{prev_hash}|{frame_index}|{ts:.4f}|{frame_hash}|{json.dumps(box_dict, sort_keys=True)}|{json.dumps(tel_dict, sort_keys=True)}".encode("utf-8")
        block_hash = hashlib.sha256(block_payload).hexdigest()

        record = ProofRecord(
            frame_index=frame_index,
            timestamp_s=ts,
            frame_hash_sha256=frame_hash,
            target_box=box_dict,
            telemetry_summary=tel_dict,
            previous_hash=prev_hash,
            record_hash=block_hash
        )

        self._current_hash = block_hash
        self.records.append(record)
        return record

    @staticmethod
    def compute_merkle_root(hash_list: List[str]) -> str:
        """Kayıtların yaprak hash'lerinden Merkle Kökü (Merkle Root) üretir."""
        if not hash_list:
            return hashlib.sha256(b"EMPTY_MERKLE_TREE").hexdigest()

        current_level = list(hash_list)
        while len(current_level) > 1:
            next_level = []
            for i in range(0, len(current_level), 2):
                left = current_level[i]
                right = current_level[i + 1] if i + 1 < len(current_level) else left
                combined = hashlib.sha256(f"{left}{right}".encode("utf-8")).hexdigest()
                next_level.append(combined)
            current_level = next_level

        return current_level[0]

    def seal_and_export_manifest(
        self,
        output_dir: str,
        end_timestamp_s: Optional[float] = None,
        frame_width: int = 1280,
        frame_height: int = 720
    ) -> ProofChainManifest:
        """
        Kilitlenme oturumunu sonlandırır, Merkle ağacı ve dijital imzayı hesaplayarak
        'proof_manifest.json' dosyasını oluşturur.
        """
        end_time = end_timestamp_s if end_timestamp_s is not None else time.time()
        duration = max(0.0, end_time - self.start_time)
        self.is_active = False

        record_hashes = [r.record_hash for r in self.records]
        merkle_root = self.compute_merkle_root(record_hashes)

        # Sayısal imza (HMAC-SHA256)
        signature_payload = f"{self.lock_id}|{self.team_id}|{duration:.3f}|{merkle_root}|{self._current_hash}".encode("utf-8")
        digital_signature = hmac.new(self.secret_key, signature_payload, hashlib.sha256).hexdigest()

        # Kural Uygunluğu Doğrulaması (TEKNOFEST Şartnamesi)
        is_duration_valid = duration >= 4.0
        is_frame_count_valid = len(self.records) >= 15

        area_valid_all = True
        center_valid_all = True
        screen_area = frame_width * frame_height
        cx_screen = frame_width / 2.0
        cy_screen = frame_height / 2.0

        for r in self.records:
            b = r.target_box
            w = max(0.0, b["x2"] - b["x1"])
            h = max(0.0, b["y2"] - b["y1"])
            box_area = w * h
            if (box_area / screen_area) < 0.05:
                area_valid_all = False

            bx = b["x1"] + w / 2.0
            by = b["y1"] + h / 2.0
            offset_x = abs(bx - cx_screen) / frame_width
            offset_y = abs(by - cy_screen) / frame_height
            if offset_x > 0.35 or offset_y > 0.35:
                center_valid_all = False

        is_valid = is_duration_valid and is_frame_count_valid and area_valid_all and center_valid_all
        score = 100.0 if is_valid else 0.0

        manifest = ProofChainManifest(
            lock_id=self.lock_id,
            team_id=self.team_id,
            start_time_iso=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.start_time)),
            end_time_iso=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(end_time)),
            total_frames=len(self.records),
            duration_s=round(duration, 3),
            merkle_root=merkle_root,
            final_chain_hash=self._current_hash,
            digital_signature=digital_signature,
            is_valid_rule_lock=is_valid,
            score_earned=score,
            records=self.records
        )

        os.makedirs(output_dir, exist_ok=True)
        manifest_path = os.path.join(output_dir, "proof_manifest.json")

        # JSON olarak diske kaydet
        manifest_data = {
            "lock_id": manifest.lock_id,
            "team_id": manifest.team_id,
            "start_time_iso": manifest.start_time_iso,
            "end_time_iso": manifest.end_time_iso,
            "total_frames": manifest.total_frames,
            "duration_s": manifest.duration_s,
            "merkle_root": manifest.merkle_root,
            "final_chain_hash": manifest.final_chain_hash,
            "digital_signature": manifest.digital_signature,
            "is_valid_rule_lock": manifest.is_valid_rule_lock,
            "score_earned": manifest.score_earned,
            "records": [
                {
                    "frame_index": r.frame_index,
                    "timestamp_s": r.timestamp_s,
                    "frame_hash_sha256": r.frame_hash_sha256,
                    "target_box": r.target_box,
                    "telemetry_summary": r.telemetry_summary,
                    "previous_hash": r.previous_hash,
                    "record_hash": r.record_hash
                }
                for r in manifest.records
            ]
        }

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)

        logger.info(f"[PROOF] Kilit kanıt manifestosu mühürlendi: {manifest_path} (Geçerli: {is_valid}, Puan: {score})")
        return manifest
