import threading
from typing import Callable, Dict, List, Any
from .logger import logger

class EventBus:
    """Thread-safe olay yöneticisi (Publisher-Subscriber).
    
    Farklı alt sistemler (Görüntü, Otopilot, Hakem İstemcisi, YKİ Arayüzü)
    birbirine sıkı sıkıya bağlanmadan olaylar üzerinden haberleşir.
    """
    
    def __init__(self):
        self._subscribers: Dict[str, List[Callable[..., Any]]] = {}
        self._lock = threading.RLock()

    def subscribe(self, event_name: str, handler: Callable[..., Any]) -> None:
        """Belirtilen olaya dinleyici (callback) ekler."""
        with self._lock:
            if event_name not in self._subscribers:
                self._subscribers[event_name] = []
            if handler not in self._subscribers[event_name]:
                self._subscribers[event_name].append(handler)

    def unsubscribe(self, event_name: str, handler: Callable[..., Any]) -> None:
        """Dinleyiciyi olaydan kaldırır."""
        with self._lock:
            if event_name in self._subscribers and handler in self._subscribers[event_name]:
                self._subscribers[event_name].remove(handler)

    def emit(self, event_name: str, **kwargs) -> None:
        """Olayı tetikler ve kayıtlı tüm dinleyicileri çağırır."""
        with self._lock:
            handlers = list(self._subscribers.get(event_name, []))
            
        for handler in handlers:
            try:
                handler(**kwargs)
            except Exception as e:
                logger.error(f"EventBus hata [{event_name}] {handler.__name__}: {e}", exc_info=True)


# Global tekil olay yolu (Singleton)
bus = EventBus()

# Olay İsim Sabitleri
EVENT_FRAME_PROCESSED = "frame_processed"
EVENT_LOCK_STARTED = "lock_started"
EVENT_LOCK_PROGRESS = "lock_progress"
EVENT_LOCK_SUCCESS = "lock_success"
EVENT_LOCK_LOST = "lock_lost"
EVENT_TELEMETRY_UPDATED = "telemetry_updated"
EVENT_RIVALS_UPDATED = "rivals_updated"
EVENT_GEOFENCE_ALERT = "geofence_alert"
EVENT_SERVER_STATUS = "server_status"
