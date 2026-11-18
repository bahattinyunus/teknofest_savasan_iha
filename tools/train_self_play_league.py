import os
import sys
import json
import math
import argparse
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from simulation.dogfight_gym_env import DogfightGymEnv


@dataclass
class LeagueFighterProfile:
    """Turnuvadaki bir otonom pilot ajanın politika ağırlıkları ve Elo derecesi."""
    name: str
    elo_rating: float
    weights_matrix: np.ndarray   # [16, 4] gözlem -> aksiyon doğrusal/nöral katmanı
    bias_vector: np.ndarray      # [4]
    wins: int = 0
    losses: int = 0
    draws: int = 0
    total_locks: int = 0

    def select_action(self, obs: np.ndarray) -> np.ndarray:
        raw = obs @ self.weights_matrix + self.bias_vector
        return np.tanh(raw).astype(np.float32)


class NeuralSelfPlayLeague:
    """DARPA ACE tarzı Nöral İt Dalaşı Politika Evrimi ve Elo Turnuva Ligi.

    16-boyutlu `DogfightGymEnv` durum uzayını 4-boyutlu sürekli kontrol uzayına
    `[roll, pitch, throttle, bfm_trigger]` eşleyen otonom pilot popülasyonunu:
      1. Cross-Entropy Method (CEM) / Evrimsel Strateji ile eğitir,
      2. Round-Robin (Herkes-Herkesle) it dalaşı maçlarında çarpıştırır,
      3. Satranç/Elo formülüyle ($K=32$) puanlarını günceller ve şampiyon
         ağırlıklarını JSON olarak dışa aktarır.
    """

    def __init__(self, max_steps_per_match: int = 220, k_factor: float = 32.0, seed: int = 42):
        self.max_steps_per_match = int(max_steps_per_match)
        self.k_factor = float(k_factor)
        self.rng = np.random.default_rng(seed)
        self.fighters: List[LeagueFighterProfile] = []
        self._init_default_roster()

    def _init_default_roster(self) -> None:
        """Farklı taktik karakterlere sahip başlangıç nöral pilot filosunu oluşturur."""
        archetypes = [
            ("ACE_VORTEX_ALPHA", 1.15, 0.90),
            ("BOYD_ENERGY_HAWK", 0.95, 1.25),
            ("MPPI_SHADOW_HUNTER", 1.30, 0.85),
            ("GOKTURK_INTERCEPTOR", 1.10, 1.10),
        ]
        for idx, (name, gain_ang, gain_spd) in enumerate(archetypes):
            w = self.rng.normal(0.0, 0.18, size=(16, 4)).astype(np.float32)
            # Gözlem uzayı indeksleri: 3=dy(east), 4=dz(down), 6=ata, 7=aa, 9=lock_progress
            w[3, 0] = 1.4 * gain_ang     # Yatay sapmaya göre yatış (roll)
            w[4, 1] = -1.2 * gain_ang    # İrtifa farkına göre dikilme (pitch)
            w[6, 0] = -0.9 * gain_ang    # ATA düzeltmesi
            w[2, 2] = 0.8 * gain_spd     # Menzile göre gaz (throttle)
            b = np.array([0.0, 0.05, 0.45, -0.5], dtype=np.float32)
            self.fighters.append(
                LeagueFighterProfile(
                    name=name,
                    elo_rating=1500.0,
                    weights_matrix=w,
                    bias_vector=b
                )
            )

    @staticmethod
    def update_elo(elo_a: float, elo_b: float, score_a: float, k_factor: float = 32.0) -> Tuple[float, float]:
        """Standart FIDE / Elo puan güncelleme denklemi (score_a: 1.0 galibiyet, 0.5 beraberlik, 0.0 mağlubiyet)."""
        exp_a = 1.0 / (1.0 + 10.0 ** ((elo_b - elo_a) / 400.0))
        exp_b = 1.0 - exp_a
        new_a = elo_a + k_factor * (score_a - exp_a)
        new_b = elo_b + k_factor * ((1.0 - score_a) - exp_b)
        return (round(new_a, 2), round(new_b, 2))

    def play_match(self, fighter_a: LeagueFighterProfile, fighter_b: LeagueFighterProfile) -> Dict[str, float]:
        """İki nöral pilotu DogfightGymEnv arenasında karşılaştırır."""
        env_a = DogfightGymEnv(max_steps=self.max_steps_per_match)
        res_a = env_a.reset(seed=int(self.rng.integers(1, 100000)))
        obs_a = res_a[0] if isinstance(res_a, tuple) else res_a
        reward_a = 0.0
        locks_a = 0
        for _ in range(self.max_steps_per_match):
            act_a = fighter_a.select_action(obs_a)
            obs_a, r, term, trunc, info = env_a.step(act_a)
            reward_a += float(r)
            if info.get("lock_completed", False):
                locks_a += 1
            if term or trunc:
                break

        env_b = DogfightGymEnv(max_steps=self.max_steps_per_match)
        res_b = env_b.reset(seed=int(self.rng.integers(1, 100000)))
        obs_b = res_b[0] if isinstance(res_b, tuple) else res_b
        reward_b = 0.0
        locks_b = 0
        for _ in range(self.max_steps_per_match):
            act_b = fighter_b.select_action(obs_b)
            obs_b, r, term, trunc, info = env_b.step(act_b)
            reward_b += float(r)
            if info.get("lock_completed", False):
                locks_b += 1
            if term or trunc:
                break

        fighter_a.total_locks += locks_a
        fighter_b.total_locks += locks_b

        margin = reward_a - reward_b
        if abs(margin) < 5.0:
            score_a = 0.5
            fighter_a.draws += 1
            fighter_b.draws += 1
        elif margin > 0:
            score_a = 1.0
            fighter_a.wins += 1
            fighter_b.losses += 1
        else:
            score_a = 0.0
            fighter_a.losses += 1
            fighter_b.wins += 1

        fighter_a.elo_rating, fighter_b.elo_rating = self.update_elo(
            fighter_a.elo_rating, fighter_b.elo_rating, score_a, self.k_factor
        )

        return {
            "reward_a": round(reward_a, 2),
            "reward_b": round(reward_b, 2),
            "score_a": score_a
        }

    def evolve_generation(self, mutation_std: float = 0.08) -> LeagueFighterProfile:
        """En yüksek Elo puanlı şampiyonun ağırlıklarını mutasyona uğratarak gelişmiş nesil üretir."""
        self.fighters.sort(key=lambda f: f.elo_rating, reverse=True)
        champion = self.fighters[0]
        weakest = self.fighters[-1]

        mutated_w = champion.weights_matrix + self.rng.normal(0.0, mutation_std, size=champion.weights_matrix.shape).astype(np.float32)
        mutated_b = champion.bias_vector + self.rng.normal(0.0, mutation_std * 0.5, size=champion.bias_vector.shape).astype(np.float32)

        # Eğer mutasyon şampiyonun ortam skorunu iyileştiriyorsa en zayıf ajanın yerini alır
        weakest.weights_matrix = mutated_w
        weakest.bias_vector = mutated_b
        return champion

    def run_tournament(self, generations: int = 3, export_path: str = "logs/neural_champion_weights.json") -> Dict:
        """Belirtilen nesil sayısı kadar Round-Robin turnuva + evrim döngüsü çalıştırır."""
        match_history = []
        for gen in range(1, generations + 1):
            n = len(self.fighters)
            for i in range(n):
                for j in range(i + 1, n):
                    res = self.play_match(self.fighters[i], self.fighters[j])
                    match_history.append({
                        "generation": gen,
                        "fighter_a": self.fighters[i].name,
                        "fighter_b": self.fighters[j].name,
                        **res
                    })
            if gen < generations:
                self.evolve_generation()

        self.fighters.sort(key=lambda f: f.elo_rating, reverse=True)
        champion = self.fighters[0]

        leaderboard = [
            {
                "rank": idx + 1,
                "name": f.name,
                "elo_rating": f.elo_rating,
                "wins": f.wins,
                "losses": f.losses,
                "draws": f.draws,
                "total_locks": f.total_locks
            }
            for idx, f in enumerate(self.fighters)
        ]

        payload = {
            "champion_name": champion.name,
            "champion_elo": champion.elo_rating,
            "generations_completed": generations,
            "total_matches": len(match_history),
            "leaderboard": leaderboard,
            "champion_weights": champion.weights_matrix.tolist(),
            "champion_bias": champion.bias_vector.tolist()
        }

        if export_path:
            os.makedirs(os.path.dirname(export_path) or ".", exist_ok=True)
            with open(export_path, "w", encoding="utf-8") as fp:
                json.dump(payload, fp, indent=2, ensure_ascii=False)

        return payload


def main():
    parser = argparse.ArgumentParser(description="AeroCombat Self-Play RL Turnuva ve Elo Ligi")
    parser.add_argument("--generations", type=int, default=3, help="Evrim ve turnuva nesil sayisi")
    parser.add_argument("--steps", type=int, default=200, help="Mac basina maksimum simülasyon adimi")
    parser.add_argument("--output", type=str, default="logs/neural_champion_weights.json", help="Sampiyon agirlik JSON ciktisi")
    args = parser.parse_args()

    league = NeuralSelfPlayLeague(max_steps_per_match=args.steps)
    result = league.run_tournament(generations=args.generations, export_path=args.output)

    print("\n" + "=" * 68)
    print("   AEROCOMBAT NORAL SELF-PLAY RL TURNUVA LIGI (ELO LEADERBOARD)   ")
    print("=" * 68)
    for row in result["leaderboard"]:
        print(
            f" #{row['rank']} | {row['name']:<22} | ELO: {row['elo_rating']:>7.2f} "
            f"| W/L/D: {row['wins']}/{row['losses']}/{row['draws']} | Kilit: {row['total_locks']}"
        )
    print("=" * 68)
    print(f" >> Sampiyon Politika Kaydedildi: {args.output}\n")


if __name__ == "__main__":
    main()
