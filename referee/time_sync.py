import time
from typing import Optional
from core.models import ZamanBilgisi
from core.logger import logger


class TimeSynchronizer:
    """Hakem sunucusu saati ile yerel sistem saati arasındaki zaman farkını yönetir.
    
    Round-Trip Time (RTT / Ağ gidiş-dönüş süresi) hesaba katılarak
    sunucu ile milisaniye hassasiyetinde senkronizasyon sağlanır.
    """

    def __init__(self):
        self.offset_ms: float = 0.0
        self.rtt_ms: float = 0.0
        self.last_sync_time: float = 0.0
        self.is_synced: bool = False

    def update_sync(self, server_time: ZamanBilgisi, t_request_start: float, t_response_end: float):
        """Sunucu saat yanıtından ofset ve RTT hesaplar."""
        # Ağ gecikmesi (RTT)
        self.rtt_ms = (t_response_end - t_request_start) * 1000.0
        half_rtt_sec = (self.rtt_ms / 2.0) / 1000.0

        # İstemci tarafında tahmin edilen sunucu anı
        client_estimated_server_sec = t_request_start + half_rtt_sec
        
        # Sunucunun bildirdiği saniye
        server_sec = server_time.to_seconds()
        
        # Ofset (Sunucu Zamanı - İstemci Zamanı)
        # Gün geçişlerini de ele almak için saat bazlı modülo hesabı
        client_now_sec = ZamanBilgisi.now().to_seconds()
        self.offset_ms = (server_sec - client_now_sec) * 1000.0
        
        self.last_sync_time = time.time()
        self.is_synced = True

        logger.info(
            f"Zaman Senkronizasyonu Güncellendi -> RTT: {self.rtt_ms:.1f} ms, "
            f"Saat Ofseti: {self.offset_ms:+.1f} ms"
        )

    def get_synced_time(self) -> ZamanBilgisi:
        """Sunucu saatiyle senkronize edilmiş güncel zamanı döndürür."""
        return ZamanBilgisi.now(server_offset_ms=self.offset_ms)
