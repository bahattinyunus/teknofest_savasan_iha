import pytest
from core.audio_announcer import (
    ProceduralToneGenerator,
    CockpitVoiceAnnouncer,
    CockpitAudioEvent
)


def test_procedural_wav_synthesis():
    # 1000 Hz saf sinüs dalgası
    wav_bytes = ProceduralToneGenerator.generate_tone_wav([1000.0], duration_sec=0.1, waveform="sine")
    assert isinstance(wav_bytes, bytes)
    assert len(wav_bytes) > 44  # WAV başlığı + PCM veri
    assert wav_bytes[:4] == b"RIFF"
    assert wav_bytes[8:12] == b"WAVE"


def test_cockpit_announcer_events_and_cache():
    announcer = CockpitVoiceAnnouncer(enable_sound=False)

    for event in CockpitAudioEvent:
        wav = announcer.get_wav_bytes(event)
        assert wav is not None
        assert len(wav) > 100
        assert wav.startswith(b"RIFF")


def test_cockpit_announcer_rate_limiting():
    announcer = CockpitVoiceAnnouncer(enable_sound=False)

    # İlk anons başarılı
    res1 = announcer.announce(CockpitAudioEvent.LOCK_CONFIRMED)
    assert res1 is True

    # Hemen peşinden yapılan 2. çağrı aralık filtresine takılmalı
    res2 = announcer.announce(CockpitAudioEvent.LOCK_CONFIRMED, force=False)
    assert res2 is False

    # Force=True ile aralık yok sayılabilmeli
    res3 = announcer.announce(CockpitAudioEvent.LOCK_CONFIRMED, force=True)
    assert res3 is True
