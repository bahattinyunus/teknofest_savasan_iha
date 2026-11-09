"""
AeroCombat - Kokpit Sesli Erken Uyarı Sistemi ve Prosedürel Taktik Ses Sentezleyici ("Bitchin' Betty").

Askeri savaş uçaklarındaki (F-16, F-35, Kaan) Cockpit Voice Warning System (CVWS):
1. Taktik Olay Uyarıları:
   - KİLİT BAŞARILI (Lock-On Confirmed - 4.0s Tamamlandı)
   - KİLİT GERİ SAYIM (Artan frekansta radar kilit tonu)
   - İRTİFA PAS GEÇ (Pull-Up / Terrain Warning)
   - GEOFENCE SINIR UYARISI (Boundary Alert)
   - ARKA TEHDİT / RWR ALARMI (Missile / Tail Threat)
   - ELEKTRONİK HARP KARIŞTIRMASI (EW Jamming)
   - DÜŞÜK BATARYA (Battery Critical)
2. Saf Python Prosedürel WAV Ses Üreticisi (Harici kütüphane veya ikili dosya gerektirmez).
3. Thread-safe ses kuyruğu ve asenkron oynatıcı.
"""

import math
import struct
import io
import time
import threading
from enum import Enum
from typing import Optional, Dict, Any, List
from core.logger import logger


class CockpitAudioEvent(Enum):
    LOCK_CONFIRMED = "LOCK_CONFIRMED"   # Kilit tamamlandı (+100 puan)
    LOCK_PROGRESS = "LOCK_PROGRESS"     # Kilitlenme süreci (bip frekansı)
    PULL_UP = "PULL_UP"                 # Kritik alçalma pas geç
    GEOFENCE_ALERT = "GEOFENCE_ALERT"   # Sınır ihlali tehlikesi
    RWR_THREAT = "RWR_THREAT"           # Düşman arkamızda kilitlenmek üzere
    JAMMING = "JAMMING"                 # GNSS/RF karıştırma alarmı
    BATTERY_CRITICAL = "BATTERY_CRITICAL" # %15 altı batarya


class ProceduralToneGenerator:
    """
    Saf Python Standart Kütüphanesi ile 16-bit PCM WAV Ses Sentezleyici.
    """

    SAMPLE_RATE = 22050  # 22.05 kHz CD-quality mono

    @classmethod
    def generate_tone_wav(
        cls,
        frequencies: List[float],
        duration_sec: float = 0.25,
        waveform: str = "sine",  # "sine", "square", "chirp"
        volume: float = 0.8
    ) -> bytes:
        """Verilen frekans veya frekans dizisinden 16-bit Mono WAV baytları sentezler."""
        num_samples = int(cls.SAMPLE_RATE * duration_sec)
        samples = []

        for i in range(num_samples):
            t = i / cls.SAMPLE_RATE
            # Çoklu frekans süperpozisyonu veya chirp
            val = 0.0
            for freq in frequencies:
                phase = 2.0 * math.pi * freq * t
                if waveform == "sine":
                    val += math.sin(phase)
                elif waveform == "square":
                    val += 1.0 if (math.sin(phase) >= 0.0) else -1.0
                elif waveform == "chirp":
                    # Frekans zamanla yükselir
                    f_inst = freq + (freq * 1.5) * (t / duration_sec)
                    val += math.sin(2.0 * math.pi * f_inst * t)

            val = (val / len(frequencies)) * volume
            # 16-bit signed integer [-32768, 32767]
            int_sample = int(np_clip(val * 32767.0, -32767.0, 32767.0))
            samples.append(int_sample)

        # WAV Dosya Başlıkları (RIFF Header)
        byte_stream = io.BytesIO()
        data_bytes = struct.pack(f"<{len(samples)}h", *samples)
        byte_rate = cls.SAMPLE_RATE * 1 * 2  # SampleRate * Channels * BitsPerSample/8
        block_align = 2

        # 1. RIFF Chunk
        byte_stream.write(b"RIFF")
        byte_stream.write(struct.pack("<I", 36 + len(data_bytes)))
        byte_stream.write(b"WAVE")

        # 2. fmt Sub-chunk
        byte_stream.write(b"fmt ")
        byte_stream.write(struct.pack("<I", 16))          # Subchunk1Size (16 for PCM)
        byte_stream.write(struct.pack("<H", 1))           # AudioFormat (1 for PCM)
        byte_stream.write(struct.pack("<H", 1))           # NumChannels (Mono = 1)
        byte_stream.write(struct.pack("<I", cls.SAMPLE_RATE))
        byte_stream.write(struct.pack("<I", byte_rate))
        byte_stream.write(struct.pack("<H", block_align))
        byte_stream.write(struct.pack("<H", 16))          # BitsPerSample

        # 3. data Sub-chunk
        byte_stream.write(b"data")
        byte_stream.write(struct.pack("<I", len(data_bytes)))
        byte_stream.write(data_bytes)

        return byte_stream.getvalue()


def np_clip(v: float, min_val: float, max_val: float) -> float:
    return max(min_val, min(max_val, v))


class CockpitVoiceAnnouncer:
    """
    Kokpit ve Yer Kontrol İstasyonu Sesli Uyarı Yöneticisi.
    """

    def __init__(self, enable_sound: bool = True):
        self.enable_sound = enable_sound
        self._last_announcement_time: Dict[CockpitAudioEvent, float] = {}
        self._min_repeat_interval_sec = 2.0
        self._sound_cache: Dict[CockpitAudioEvent, bytes] = {}
        self._init_sounds()

    def _init_sounds(self):
        """Tüm taktik uyarı ses profillerini önceden sentezleyip önbelleğe alır."""
        # 1. Kilit Başarılı: 3 tonlu zafer fanfarı (880 Hz, 1175 Hz, 1760 Hz)
        self._sound_cache[CockpitAudioEvent.LOCK_CONFIRMED] = (
            ProceduralToneGenerator.generate_tone_wav([880.0, 1175.0, 1760.0], duration_sec=0.55, waveform="chirp")
        )

        # 2. Kilitlenme Devam: Kesik kesik yüksek bip (1400 Hz)
        self._sound_cache[CockpitAudioEvent.LOCK_PROGRESS] = (
            ProceduralToneGenerator.generate_tone_wav([1400.0], duration_sec=0.08, waveform="sine")
        )

        # 3. Pull-Up: Sert ikaz tonu (450 Hz / 800 Hz kare dalga)
        self._sound_cache[CockpitAudioEvent.PULL_UP] = (
            ProceduralToneGenerator.generate_tone_wav([450.0, 800.0], duration_sec=0.40, waveform="square", volume=0.9)
        )

        # 4. Geofence Sınır Uyarısı: Modüleli alarm (600 Hz)
        self._sound_cache[CockpitAudioEvent.GEOFENCE_ALERT] = (
            ProceduralToneGenerator.generate_tone_wav([600.0, 900.0], duration_sec=0.35, waveform="sine")
        )

        # 5. RWR Tehdit: Hızlı testere dişi savaş uyarısı (1800 Hz)
        self._sound_cache[CockpitAudioEvent.RWR_THREAT] = (
            ProceduralToneGenerator.generate_tone_wav([1800.0, 2200.0], duration_sec=0.30, waveform="chirp", volume=0.95)
        )

        # 6. Karıştırma (EW): Düşük parazit dalgası (250 Hz)
        self._sound_cache[CockpitAudioEvent.JAMMING] = (
            ProceduralToneGenerator.generate_tone_wav([250.0, 320.0], duration_sec=0.45, waveform="sine")
        )

        # 7. Kritik Batarya: Alçalan çift ton (700 Hz -> 350 Hz)
        self._sound_cache[CockpitAudioEvent.BATTERY_CRITICAL] = (
            ProceduralToneGenerator.generate_tone_wav([700.0, 350.0], duration_sec=0.50, waveform="sine")
        )

    def announce(self, event: CockpitAudioEvent, force: bool = False) -> bool:
        """
        Belirtilen taktik olayı seslendirir.
        Gereksiz ses karmaşasını önlemek için aralık filtresi uygular.
        """
        now = time.time()
        last_time = self._last_announcement_time.get(event, 0.0)

        # lock progress her 0.3 sn'de bir ötebilir; diğerleri en az 2.0 sn aralıklı olmalıdır
        interval = 0.3 if event == CockpitAudioEvent.LOCK_PROGRESS else self._min_repeat_interval_sec

        if not force and (now - last_time) < interval:
            return False

        self._last_announcement_time[event] = now
        wav_data = self._sound_cache.get(event)

        if not wav_data or not self.enable_sound:
            return True

        # Arka plan iş parçacığında oynat
        threading.Thread(
            target=self._play_wav_bytes,
            args=(wav_data, event.value),
            daemon=True
        ).start()
        return True

    def _play_wav_bytes(self, wav_bytes: bytes, event_name: str):
        """Windows `winsound` veya platform bağımsız ses yürütücüsü."""
        try:
            import winsound
            winsound.PlaySound(wav_bytes, winsound.SND_MEMORY)
        except Exception:
            # Linux / macOS veya başsız ortamlarda sessizce geç
            pass

    def get_wav_bytes(self, event: CockpitAudioEvent) -> Optional[bytes]:
        """Web GCS / WebSocket üzerinden tarayıcıya iletmek için ham WAV verisini döner."""
        return self._sound_cache.get(event)
