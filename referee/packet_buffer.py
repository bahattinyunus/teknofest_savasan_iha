import time
import zlib
import json
from collections import deque
from typing import Optional, Dict, Any, List, Tuple
from core.models import TelemetriPaketi
from core.logger import logger


class BufferedPacket:
    """Sıra numarası ve CRC32 doğrulama kodlu güvenilir telemetri paketi."""
    def __init__(self, seq_id: int, packet_dict: Dict[str, Any]):
        self.seq_id = seq_id
        self.timestamp = time.time()
        self.packet_dict = packet_dict
        self.retry_count = 0
        self.crc32 = self._compute_crc(packet_dict)

    @staticmethod
    def _compute_crc(data: Dict[str, Any]) -> int:
        raw_bytes = json.dumps(data, sort_keys=True).encode("utf-8")
        return zlib.crc32(raw_bytes)

    def is_valid(self) -> bool:
        return self._compute_crc(self.packet_dict) == self.crc32


class TelemetryPacketBuffer:
    """Ağ Kesintisi ve Paket Kaybı Korumalı Telemetri Arabelleği (Anti-Loss Queue).
    
    Özellikler:
    - Ağ koptuğunda telemetri paketlerini sıraya alır (FIFO buffer).
    - Sıra numaralandırma (Sequence ID) ve CRC32 veri bütünlüğü denetimi.
    - Bağlantı geri geldiğinde birikmiş paketleri kronolojik sırada iletir.
    - Ağ sağlığı ve paket kaybı (Packet Loss Ratio) telemetrisi üretir.
    """

    def __init__(self, max_buffer_size: int = 500, max_retries: int = 3):
        self.max_buffer_size = max_buffer_size
        self.max_retries = max_retries
        self._buffer: deque[BufferedPacket] = deque(maxlen=max_buffer_size)
        self._seq_counter = 0

        # Metrikler
        self.total_enqueued = 0
        self.total_sent = 0
        self.total_dropped = 0
        self.total_retries = 0

    def enqueue(self, telemetri: TelemetriPaketi) -> BufferedPacket:
        """Yeni bir telemetri paketini sıra numarası ve sağlama toplamıyla kuyruğa ekler."""
        self._seq_counter += 1
        payload = telemetri.to_dict()
        packet = BufferedPacket(seq_id=self._seq_counter, packet_dict=payload)

        if len(self._buffer) >= self.max_buffer_size:
            # Tampon dolduysa en eski paketi düşür
            dropped = self._buffer.popleft()
            self.total_dropped += 1
            logger.warning(f"Telemetri tamponu dolu! Paket #{dropped.seq_id} düşürüldü.")

        self._buffer.append(packet)
        self.total_enqueued += 1
        return packet

    def peek(self) -> Optional[BufferedPacket]:
        """Tampondaki ilk gönderilecek paketi inceler (kuyruktan silmez)."""
        if self._buffer:
            return self._buffer[0]
        return None

    def mark_sent(self, packet: BufferedPacket):
        """Paket başarıyla sunucuya ulaştığında kuyruktan kaldırır."""
        if self._buffer and self._buffer[0].seq_id == packet.seq_id:
            self._buffer.popleft()
            self.total_sent += 1

    def mark_failed(self, packet: BufferedPacket):
        """Paket iletimi başarısız olduğunda deneme sayacını artırır."""
        packet.retry_count += 1
        self.total_retries += 1
        if packet.retry_count > self.max_retries:
            # Aşırı deneme sınırına ulaştıysa düşür
            if self._buffer and self._buffer[0].seq_id == packet.seq_id:
                dropped = self._buffer.popleft()
                self.total_dropped += 1
                logger.error(f"Paket #{dropped.seq_id} {self.max_retries} deneme sonrası iletilemedi ve düşürüldü!")

    def get_network_health(self) -> Dict[str, Any]:
        """Ağ bağlantı kalitesi ve paket başarı oranını hesaplar."""
        loss_ratio = (self.total_dropped / max(1, self.total_enqueued)) * 100.0
        success_ratio = (self.total_sent / max(1, self.total_enqueued)) * 100.0
        return {
            "buffer_depth": len(self._buffer),
            "total_enqueued": self.total_enqueued,
            "total_sent": self.total_sent,
            "total_dropped": self.total_dropped,
            "total_retries": self.total_retries,
            "loss_ratio_pct": round(loss_ratio, 2),
            "success_ratio_pct": round(success_ratio, 2)
        }

    def clear(self):
        """Tamponu temizler."""
        self._buffer.clear()
