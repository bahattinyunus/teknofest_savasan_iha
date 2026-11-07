"""
Kriptografik Kilit Kanıt Zinciri ve Hakem Denetim Aracı Birim Testleri
"""

import os
import shutil
import tempfile
import pytest
import numpy as np

from referee.proof_chain import CryptographicProofChain
from tools.verify_proofs import verify_manifest_file
from core.models import HedefKutusu, TelemetriPaketi, ProofChainManifest


class TestProofChain:

    @pytest.fixture
    def temp_dir(self):
        d = tempfile.mkdtemp()
        yield d
        shutil.rmtree(d, ignore_errors=True)

    @pytest.fixture
    def chain(self):
        return CryptographicProofChain(secret_key="Test-Secret-Key-12345")

    def test_proof_chain_creation_and_sealing(self, chain, temp_dir):
        chain.start_chain(lock_id="LOCK_TEST_001", team_id=1, timestamp_s=1000.0)
        assert chain.is_active is True

        dummy_frame = np.zeros((720, 1280, 3), dtype=np.uint8)

        # 20 karelik kilitlenme kaydı ekle (kurala uygun: %5 alan ve merkez toleransında)
        # 1280 x 720 -> alan = 921600. %5 = 46080 -> 250 x 200 = 50000 (> %5)
        # Merkez: (640, 360) -> Box: [515, 260, 765, 460]
        box = HedefKutusu(x1=515, y1=260, x2=765, y2=460, conf=0.92, track_id=42)
        tel = TelemetriPaketi(
            takim_numarasi=1,
            IHA_enlem=41.100,
            IHA_boylam=28.900,
            IHA_irtifa=60.0,
            IHA_dikilme=2.0,
            IHA_yonelme=90.0,
            IHA_yatis=0.0,
            IHA_hiz=25.0,
            IHA_batarya=95,
            IHA_otonom=1,
            IHA_kilitlenme=1
        )

        for i in range(20):
            ts = 1000.0 + i * 0.22  # Toplam süre 19 * 0.22 = 4.18 saniye (>= 4.0s)
            rec = chain.add_frame_proof(
                frame_index=i,
                frame=dummy_frame,
                target_box=box,
                telemetry=tel,
                timestamp_s=ts
            )
            assert rec.record_hash != ""

        # Mühürle
        manifest = chain.seal_and_export_manifest(
            output_dir=temp_dir,
            end_timestamp_s=1004.25,
            frame_width=1280,
            frame_height=720
        )

        assert isinstance(manifest, ProofChainManifest)
        assert manifest.is_valid_rule_lock is True
        assert manifest.score_earned == 100.0
        assert manifest.duration_s >= 4.0
        assert os.path.exists(os.path.join(temp_dir, "proof_manifest.json"))

        # CLI denetleyici ile doğrula
        audit_res = verify_manifest_file(
            os.path.join(temp_dir, "proof_manifest.json"),
            secret_key="Test-Secret-Key-12345"
        )
        assert audit_res["status"] == "PASS"
        assert audit_res["score"] == 100.0
        assert len(audit_res["errors"]) == 0

    def test_proof_tamper_detection(self, chain, temp_dir):
        chain.start_chain(lock_id="LOCK_TAMPER_001", team_id=1, timestamp_s=100.0)
        dummy_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        box = HedefKutusu(x1=515, y1=260, x2=765, y2=460, conf=0.9, track_id=1)

        for i in range(16):
            chain.add_frame_proof(frame_index=i, frame=dummy_frame, target_box=box, timestamp_s=100.0 + i * 0.26)

        manifest = chain.seal_and_export_manifest(output_dir=temp_dir, end_timestamp_s=104.5)
        manifest_path = os.path.join(temp_dir, "proof_manifest.json")

        # Dosyayı bilerek tahrif et (hedef koordinatını değiştir)
        import json
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        data["records"][5]["target_box"]["x1"] = 999.0  # Tahrifat!

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        # Denetleyici tahrifatı yakalamalı
        audit_res = verify_manifest_file(manifest_path, secret_key="Test-Secret-Key-12345")
        assert audit_res["status"] == "FAIL"
        assert any("tahrif" in e for e in audit_res["errors"])
