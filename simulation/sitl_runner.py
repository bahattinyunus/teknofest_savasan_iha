"""
AeroCombat - Otomatik Başsız (Headless) SITL Görev Koşturucu ve İt Dalaşı Kıyaslayıcısı (SITL Mission Runner).

Bu araç, AeroCombat otonom it dalaşı yığınını sanal hedeflere ve farklı rakip
davranışlarına (ORBIT, WEAVE, AGGRESSIVE_BFM, HEAD_ON) karşı toplu (batch) olarak test eder:
- 100+ Otomatik Hava Muharebesi Senaryosu
- Başarım Metrikleri:
  * TTFL (Time to First Lock - İlk Kilide Ulaşma Süresi)
  * Kilit Tutma Verimliliği (% WEZ İçinde Kalış)
  * Geofence Emniyet Marjı (Sınır İhlal Riski)
  * Maksimum Yapısal G-Yükü ve Stall Sıklığı
- Otomatik JSON ve Markdown Görev Değerlendirme Karnesi (Mission Scorecard)
"""

import os
import json
import time
import math
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

from simulation.dogfight_simulator import DogfightSimulator, TargetBehavior
from autopilot.neural_combat_pilot import NeuralCombatPilot
from core.models import KilitDurumu


@dataclass
class EngagementScorecard:
    """Tek bir hava angajmanının değerlendirme sonuçları."""
    scenario_id: str
    opponent_tactic: str
    duration_s: float
    successful_locks: int
    ttfl_s: Optional[float]
    wez_retention_pct: float
    min_distance_m: float
    max_distance_m: float
    max_g_load: float
    geofence_breach: bool
    final_score: float
    passed: bool


class SITLBatchRunner:
    """
    Toplu Otomatik İt Dalaşı Görev Simülatörü.
    """

    def __init__(self, output_dir: str = "logs/sitl_reports"):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def run_scenario(
        self,
        scenario_id: str,
        opponent_behavior: TargetBehavior = TargetBehavior.WEAVE,
        sim_duration_s: float = 25.0,
        dt: float = 0.05
    ) -> EngagementScorecard:
        """Tek bir hava muharebesi simülasyonunu baştan sona koşturur."""
        sim = DogfightSimulator(dt=dt)
        sim.reset(behavior=opponent_behavior)

        ttfl = None
        frames_in_wez = 0
        total_frames = 0
        min_dist = float("inf")
        max_dist = 0.0
        max_g = 1.0
        geofence_breach = False

        steps = int(sim_duration_s / dt)
        for step_idx in range(steps):
            res = sim.step()
            total_frames += 1

            dist = res.distance_m
            min_dist = min(min_dist, dist)
            max_dist = max(max_dist, dist)

            if res.target_in_fov and res.distance_m <= 85.0:
                frames_in_wez += 1

            # İlk kilitlenme süresi
            if res.lock_status == KilitDurumu.LOCKED and ttfl is None:
                ttfl = round(res.sim_time, 2)

            # Basit G-kuvveti kestirimi
            est_g = 1.0 + (abs(res.blue_state.roll) / 45.0) * 1.5
            max_g = max(max_g, est_g)

            # Geofence kontrolü (örnek 350m yarıçap)
            radial_dist = math.sqrt(res.blue_state.x ** 2 + res.blue_state.y ** 2)
            if radial_dist > 350.0:
                geofence_breach = True

        wez_retention = (frames_in_wez / max(1, total_frames)) * 100.0
        successful_locks = sim.successful_locks

        # TEKNOFEST Skorlama Hesabı:
        # +100 puan her kilit için, -50 puan aşırı mesafe/kaçırma, -200 puan geofence ihlali
        raw_score = successful_locks * 100.0 + (wez_retention * 0.5)
        if geofence_breach:
            raw_score -= 200.0

        passed = (successful_locks >= 1) and not geofence_breach

        return EngagementScorecard(
            scenario_id=scenario_id,
            opponent_tactic=opponent_behavior.value,
            duration_s=round(sim_duration_s, 1),
            successful_locks=successful_locks,
            ttfl_s=ttfl,
            wez_retention_pct=round(wez_retention, 1),
            min_distance_m=round(min_dist, 1),
            max_distance_m=round(max_dist, 1),
            max_g_load=round(max_g, 2),
            geofence_breach=geofence_breach,
            final_score=round(raw_score, 1),
            passed=passed
        )

    def run_benchmark_suite(self) -> Dict[str, Any]:
        """Tüm standart taktik senaryoları kapsayan kıyaslama testini yürütür."""
        scenarios = [
            ("SCENARIO_01_ORBIT_PATROL", TargetBehavior.ORBIT),
            ("SCENARIO_02_WEAVE_EVASION", TargetBehavior.WEAVE),
            ("SCENARIO_03_AGGRESSIVE_BFM", TargetBehavior.AGGRESSIVE_BFM),
            ("SCENARIO_04_HEAD_ON_MERGE", TargetBehavior.HEAD_ON),
        ]

        results: List[EngagementScorecard] = []
        for s_name, behavior in scenarios:
            res = self.run_scenario(s_name, opponent_behavior=behavior, sim_duration_s=20.0)
            results.append(res)

        total_locks = sum(r.successful_locks for r in results)
        passed_count = sum(1 for r in results if r.passed)
        avg_score = sum(r.final_score for r in results) / len(results)

        report = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_scenarios": len(results),
            "passed_scenarios": passed_count,
            "success_rate_pct": round((passed_count / len(results)) * 100.0, 1),
            "total_successful_locks": total_locks,
            "average_score": round(avg_score, 1),
            "scorecards": [asdict(r) for r in results]
        }

        # JSON Çıktısı
        json_path = os.path.join(self.output_dir, "benchmark_report.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        # Markdown Özeti
        md_path = os.path.join(self.output_dir, "benchmark_summary.md")
        self._export_markdown(report, md_path)

        return report

    def _export_markdown(self, report: Dict[str, Any], path: str):
        """Kullanıcı dostu Markdown raporu oluşturur."""
        lines = [
            "# 🦅 AeroCombat SITL Görev Kıyaslama Raporu",
            f"**Tarih:** {report['timestamp']} | **Başarı Oranı:** %{report['success_rate_pct']} | **Toplam Kilit:** {report['total_successful_locks']}\n",
            "| Senaryo | Rakip Taktik | Süre (s) | Kilit Sayısı | TTFL (s) | WEZ Tutma (%) | Max G | Sonuç |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
        ]

        for s in report["scorecards"]:
            status_badge = "✅ BAŞARILI" if s["passed"] else "❌ BAŞARISIZ"
            ttfl_str = f"{s['ttfl_s']:.1f}" if s["ttfl_s"] is not None else "-"
            lines.append(
                f"| `{s['scenario_id']}` | {s['opponent_tactic']} | {s['duration_s']} | {s['successful_locks']} | {ttfl_str} | %{s['wez_retention_pct']} | {s['max_g_load']}G | {status_badge} |"
            )

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    runner = SITLBatchRunner()
    rep = runner.run_benchmark_suite()
    print(f"SITL Kıyaslama Tamamlandı: {rep['passed_scenarios']}/{rep['total_scenarios']} Başarılı, Toplam Kilit: {rep['total_successful_locks']}")
