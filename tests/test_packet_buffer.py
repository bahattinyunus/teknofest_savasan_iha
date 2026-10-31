import pytest
from core.models import TelemetriPaketi, ZamanBilgisi
from referee.packet_buffer import TelemetryPacketBuffer, BufferedPacket


def make_dummy_telem(seq=1):
    return TelemetriPaketi(
        takim_numarasi=1, IHA_enlem=41.100 + seq*0.001, IHA_boylam=28.900, IHA_irtifa=100.0,
        IHA_dikilme=0.0, IHA_yonelme=0.0, IHA_yatis=0.0, IHA_hiz=20.0,
        IHA_batarya=90, IHA_otonom=1, IHA_kilitlenme=0,
        Hedef_merkez_X=0, Hedef_merkez_Y=0, Hedef_genislik=0, Hedef_yukseklik=0,
        GPSSaati=ZamanBilgisi.now()
    )


def test_packet_buffer_enqueue_and_crc():
    buf = TelemetryPacketBuffer(max_buffer_size=10)
    telem = make_dummy_telem(1)
    packet = buf.enqueue(telem)

    assert packet.seq_id == 1
    assert packet.is_valid() is True
    assert buf.peek() is not None
    assert buf.peek().seq_id == 1


def test_packet_buffer_fifo_order_and_mark_sent():
    buf = TelemetryPacketBuffer(max_buffer_size=10)
    p1 = buf.enqueue(make_dummy_telem(1))
    p2 = buf.enqueue(make_dummy_telem(2))

    assert buf.peek().seq_id == p1.seq_id
    buf.mark_sent(p1)
    assert buf.peek().seq_id == p2.seq_id
    buf.mark_sent(p2)
    assert buf.peek() is None


def test_packet_buffer_retry_and_drop():
    buf = TelemetryPacketBuffer(max_buffer_size=5, max_retries=2)
    p1 = buf.enqueue(make_dummy_telem(1))

    buf.mark_failed(p1)
    assert p1.retry_count == 1
    assert buf.peek() is not None

    buf.mark_failed(p1)
    assert p1.retry_count == 2
    assert buf.peek() is not None

    # 3. hata (max_retries aşımı) -> paket düşürülmeli
    buf.mark_failed(p1)
    assert buf.peek() is None
    health = buf.get_network_health()
    assert health["total_dropped"] == 1
