import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import numpy as np


@dataclass
class MeshPacket:
    """Sürü İHA'lar arası taktik veri bağı paketi."""
    sender_id: int
    sequence_num: int
    timestamp_s: float
    pos_ned_m: Tuple[float, float, float]
    vel_ned_mps: Tuple[float, float, float]
    allocated_target_id: Optional[int] = None
    bid_scores: Dict[int, float] = field(default_factory=dict)
    ttl_hops: int = 2


@dataclass
class TriangulatedTarget3D:
    """Çoklu İHA kamera doğrultu ışınlarının (bearing rays) 3D kesişimiyle bulunan hedef."""
    target_id: int
    estimated_pos_ned_m: Tuple[float, float, float]
    triangulation_error_m: float
    observing_uav_ids: List[int]


@dataclass
class SwarmAllocationResult:
    """CBBA (Consensus-Based Bundle Algorithm) hedef tahsis sonucu."""
    uav_to_target: Dict[int, int]
    target_to_uav: Dict[int, int]
    total_swarm_utility: float
    consensus_iterations: int


class TacticalMeshDatalink:
    """Taktik Sürü Mesh Veri Bağı, 3D Pasif Nirengi ve CBBA Hedef Tahsis Motoru."""

    def __init__(
        self,
        own_uav_id: int = 1,
        max_comm_range_m: float = 1500.0,
        base_packet_loss_rate: float = 0.02,
        seed: int = 42
    ):
        self.own_uav_id = own_uav_id
        self.max_comm_range_m = float(max_comm_range_m)
        self.base_packet_loss_rate = float(base_packet_loss_rate)
        self.rng = np.random.default_rng(seed)
        self._seq_counter = 0
        self.peer_states: Dict[int, MeshPacket] = {}

    def compute_link_quality(
        self,
        pos_a_ned: Tuple[float, float, float],
        pos_b_ned: Tuple[float, float, float],
        jamming_intensity: float = 0.0
    ) -> float:
        """İki İHA arasındaki mesafe (FSPL) ve elektronik karıştırmaya göre link kalitesi [0..1]."""
        dist = math.dist(pos_a_ned, pos_b_ned)
        if dist >= self.max_comm_range_m:
            return 0.0
        dist_factor = 1.0 - (dist / self.max_comm_range_m) ** 1.6
        ew_factor = max(0.0, 1.0 - float(jamming_intensity))
        return round(float(max(0.0, min(1.0, dist_factor * ew_factor))), 4)

    def broadcast_state(
        self,
        pos_ned_m: Tuple[float, float, float],
        vel_ned_mps: Tuple[float, float, float],
        bid_scores: Optional[Dict[int, float]] = None,
        allocated_target_id: Optional[int] = None,
        timestamp_s: float = 0.0
    ) -> MeshPacket:
        self._seq_counter += 1
        pkt = MeshPacket(
            sender_id=self.own_uav_id,
            sequence_num=self._seq_counter,
            timestamp_s=timestamp_s,
            pos_ned_m=pos_ned_m,
            vel_ned_mps=vel_ned_mps,
            allocated_target_id=allocated_target_id,
            bid_scores=bid_scores or {}
        )
        self.peer_states[self.own_uav_id] = pkt
        return pkt

    def receive_peer_packet(
        self,
        packet: MeshPacket,
        own_pos_ned: Tuple[float, float, float],
        jamming_intensity: float = 0.0
    ) -> bool:
        """Gelen paketi link kalitesine göre kabul eder veya düşürür."""
        quality = self.compute_link_quality(own_pos_ned, packet.pos_ned_m, jamming_intensity)
        if quality <= 0.05:
            return False
        effective_loss = self.base_packet_loss_rate + (1.0 - quality) * 0.35
        if self.rng.random() < effective_loss:
            return False
        prev = self.peer_states.get(packet.sender_id)
        if prev is None or packet.sequence_num >= prev.sequence_num:
            self.peer_states[packet.sender_id] = packet
        return True

    @staticmethod
    def triangulate_target_3d(
        target_id: int,
        observer_positions_ned: List[Tuple[float, float, float]],
        bearing_unit_vectors_ned: List[Tuple[float, float, float]],
        observer_ids: Optional[List[int]] = None
    ) -> TriangulatedTarget3D:
        """İki veya daha fazla İHA'nın 3D kamera doğrultu vektörlerinden (LOS rays)
        en küçük kareler (Least-Squares Line Intersection) yöntemiyle pasif 3D hedef konumu çözer.

        Her i gözlemcisi için ışın: P_i + t_i * d_i (||d_i|| = 1).
        Hedef noktası X için toplam dikey uzaklık karesini minimize eden doğrusal sistem:
          [ sum(I - d_i d_i^T) ] X = sum( (I - d_i d_i^T) P_i )
        """
        n_obs = len(observer_positions_ned)
        if n_obs < 2 or len(bearing_unit_vectors_ned) != n_obs:
            raise ValueError("3D nirengi icin en az 2 gozlemci IHA ve dogrultu vektoru gereklidir.")

        A = np.zeros((3, 3), dtype=np.float64)
        b = np.zeros(3, dtype=np.float64)
        eye3 = np.eye(3, dtype=np.float64)

        norm_dirs = []
        pts = []
        for pos, vec in zip(observer_positions_ned, bearing_unit_vectors_ned):
            p = np.array(pos, dtype=np.float64)
            d = np.array(vec, dtype=np.float64)
            norm = float(np.linalg.norm(d))
            if norm < 1e-8:
                continue
            d = d / norm
            proj = eye3 - np.outer(d, d)
            A += proj
            b += proj @ p
            pts.append(p)
            norm_dirs.append(d)

        try:
            est_x = np.linalg.solve(A + 1e-6 * eye3, b)
        except np.linalg.LinAlgError:
            est_x, _, _, _ = np.linalg.lstsq(A, b, rcond=None)

        # Işınlara olan ortalama dikey uzaklık (triangulation residual error)
        errors = []
        for p, d in zip(pts, norm_dirs):
            diff = est_x - p
            perp = diff - np.dot(diff, d) * d
            errors.append(float(np.linalg.norm(perp)))
        mean_err = float(np.mean(errors)) if errors else 0.0

        obs_ids = observer_ids if observer_ids is not None else list(range(1, n_obs + 1))

        return TriangulatedTarget3D(
            target_id=target_id,
            estimated_pos_ned_m=(round(float(est_x[0]), 2), round(float(est_x[1]), 2), round(float(est_x[2]), 2)),
            triangulation_error_m=round(mean_err, 3),
            observing_uav_ids=obs_ids
        )

    @staticmethod
    def run_cbba_target_allocation(
        uav_positions_ned: Dict[int, Tuple[float, float, float]],
        uav_velocities_ned: Dict[int, Tuple[float, float, float]],
        target_positions_ned: Dict[int, Tuple[float, float, float]],
        target_priorities: Optional[Dict[int, float]] = None
    ) -> SwarmAllocationResult:
        """CBBA (Consensus-Based Bundle Algorithm) ile çoklu İHA-Hedef açık artırma tahsisi.

        Aynı hedefe iki dost İHA'nın çakışarak kilitlenmesini engeller ve sürü toplam
        kilitlenme faydasını (mesafe + boresight açısı + hedef önceliği) maksimize eder.
        """
        uav_ids = sorted(uav_positions_ned.keys())
        tgt_ids = sorted(target_positions_ned.keys())

        if not uav_ids or not tgt_ids:
            return SwarmAllocationResult({}, {}, 0.0, 0)

        # 1. Her (İHA i, Hedef j) çifti için taktik fayda (bid) matrisini hesapla
        utility_matrix: Dict[Tuple[int, int], float] = {}
        for uid in uav_ids:
            upos = np.array(uav_positions_ned[uid], dtype=np.float64)
            uvel = np.array(uav_velocities_ned.get(uid, (20.0, 0.0, 0.0)), dtype=np.float64)
            uspeed = float(np.linalg.norm(uvel)) + 1e-6

            for tid in tgt_ids:
                tpos = np.array(target_positions_ned[tid], dtype=np.float64)
                los = tpos - upos
                dist = float(np.linalg.norm(los)) + 1e-6
                cos_ata = float(np.dot(uvel, los) / (uspeed * dist))
                cos_ata = max(-1.0, min(1.0, cos_ata))

                # Mesafe skoru (35m-80m arası yüksek, çok uzakta düşük)
                dist_score = 100.0 * math.exp(-dist / 140.0)
                # Yönelim skoru (hedef burnumuzun önündeyse yüksek)
                angle_score = 45.0 * ((cos_ata + 1.0) / 2.0)
                prio = float(target_priorities.get(tid, 1.0)) if target_priorities else 1.0

                utility_matrix[(uid, tid)] = round((dist_score + angle_score) * prio, 3)

        # 2. Dağıtık Açık Artırma ve Uzlaşı (Consensus Auction Loop)
        uav_to_target: Dict[int, int] = {}
        target_to_uav: Dict[int, int] = {}
        winning_bids: Dict[int, float] = {tid: -1.0 for tid in tgt_ids}

        unassigned_uavs = list(uav_ids)
        iterations = 0
        max_iters = len(uav_ids) * len(tgt_ids) + 3

        while unassigned_uavs and iterations < max_iters:
            iterations += 1
            uid = unassigned_uavs.pop(0)

            # Bu İHA için en yüksek net kazanç sağlayan hedefi bul
            best_tid = None
            best_margin = -1e9
            for tid in tgt_ids:
                bid = utility_matrix[(uid, tid)]
                margin = bid - winning_bids[tid]
                if margin > best_margin and margin > 0.01:
                    best_margin = margin
                    best_tid = tid

            if best_tid is not None:
                prev_owner = target_to_uav.get(best_tid)
                if prev_owner is not None and prev_owner != uid:
                    del uav_to_target[prev_owner]
                    if len(uav_to_target) < len(tgt_ids):
                        unassigned_uavs.append(prev_owner)

                uav_to_target[uid] = best_tid
                target_to_uav[best_tid] = uid
                winning_bids[best_tid] = utility_matrix[(uid, best_tid)] + 0.05

        total_utility = sum(utility_matrix[(u, t)] for u, t in uav_to_target.items())

        return SwarmAllocationResult(
            uav_to_target=uav_to_target,
            target_to_uav=target_to_uav,
            total_swarm_utility=round(float(total_utility), 2),
            consensus_iterations=iterations
        )
