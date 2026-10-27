import cv2
import time
import json
import threading
from typing import Optional
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse, StreamingResponse
import numpy as np

from core.models import TelemetriPaketi, KilitDurumu
from core.logger import logger
from core.event_bus import bus, EVENT_FRAME_PROCESSED, EVENT_TELEMETRY_UPDATED


web_app = FastAPI(title="AeroCombat Web GCS", description="Web Tabanlı Canlı Yer Kontrol İstasyonu")

# Küresel paylaşılan son durumlar
_latest_frame: Optional[np.ndarray] = None
_latest_telemetry: Optional[dict] = None
_latest_lock_status: str = "IDLE"
_lock_duration: float = 0.0
_lock_count: int = 0


def _on_frame(frame, durum, sure, **kwargs):
    global _latest_frame, _latest_lock_status, _lock_duration
    _latest_frame = frame
    _latest_lock_status = durum.value if hasattr(durum, 'value') else str(durum)
    _lock_duration = sure


def _on_telem(telemetri: TelemetriPaketi, **kwargs):
    global _latest_telemetry
    _latest_telemetry = telemetri.to_dict()


bus.subscribe(EVENT_FRAME_PROCESSED, _on_frame)
bus.subscribe(EVENT_TELEMETRY_UPDATED, _on_telem)


def generate_mjpeg_stream():
    """Tarayıcılar için canlı MJPEG video akışı üretici."""
    global _latest_frame
    while True:
        if _latest_frame is not None:
            # JPEG sıkıştırma
            ret, buffer = cv2.imencode('.jpg', _latest_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if ret:
                frame_bytes = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(0.04)  # ~25 FPS


@web_app.get("/video_feed")
def video_feed():
    """Canlı kamera akışını MJPEG formatında döner."""
    return StreamingResponse(
        generate_mjpeg_stream(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )


@web_app.get("/api/state")
def get_state():
    """Anlık telemetri ve kilit durumunu JSON olarak döner."""
    return {
        "telemetry": _latest_telemetry,
        "lock_status": _latest_lock_status,
        "lock_duration": round(_lock_duration, 2),
        "lock_count": _lock_count
    }


@web_app.get("/", response_class=HTMLResponse)
def index():
    html = """
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AeroCombat - Web Yer Kontrol İstasyonu</title>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
            body { background: #0b0f19; color: #e2e8f0; padding: 16px; }
            header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #1e293b; padding-bottom: 12px; margin-bottom: 16px; }
            h1 { font-size: 20px; color: #38bdf8; }
            .grid { display: grid; grid-template-columns: 2fr 1fr; gap: 16px; }
            .card { background: #131b2e; border: 1px solid #1e293b; border-radius: 8px; padding: 16px; }
            .video-container { position: relative; width: 100%; border-radius: 6px; overflow: hidden; background: #000; border: 1px solid #334155; }
            .video-container img { width: 100%; height: auto; display: block; }
            .badge { display: inline-block; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 13px; }
            .badge-locked { background: #059669; color: white; }
            .badge-locking { background: #d97706; color: white; }
            .badge-idle { background: #0284c7; color: white; }
            .dial-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 12px; }
            .dial { background: #1e293b; padding: 12px; border-radius: 6px; text-align: center; }
            .dial-val { font-size: 22px; font-weight: bold; color: #38bdf8; }
            .dial-lbl { font-size: 12px; color: #94a3b8; text-transform: uppercase; margin-top: 4px; }
            .btn { display: inline-block; width: 100%; padding: 10px; margin-top: 8px; border: none; border-radius: 6px; font-weight: bold; cursor: pointer; color: white; }
            .btn-danger { background: #dc2626; }
            .btn-primary { background: #2563eb; }
            .progress-bar { width: 100%; height: 12px; background: #334155; border-radius: 6px; overflow: hidden; margin-top: 8px; }
            .progress-fill { height: 100%; background: #38bdf8; width: 0%; transition: width 0.1s; }
        </style>
    </head>
    <body>
        <header>
            <h1>🦅 AeroCombat - Web Görev Kontrol İstasyonu</h1>
            <span id="conn-badge" class="badge badge-idle">CANLI AKIŞ AKTİF</span>
        </header>

        <div class="grid">
            <div class="card">
                <h3>CANLI KAMERA AKIŞI & HEDEF KİLİTLENME HUD</h3>
                <div class="video-container" style="margin-top: 10px;">
                    <img src="/video_feed" alt="Canlı Kamera">
                </div>
                <div style="margin-top: 12px; display: flex; justify-content: space-between; align-items: center;">
                    <div>Kilit Durumu: <span id="lock-state" class="badge badge-idle">IDLE</span></div>
                    <div id="lock-time" style="font-weight: bold;">0.00s / 4.0s</div>
                </div>
                <div class="progress-bar">
                    <div id="lock-bar" class="progress-fill"></div>
                </div>
            </div>

            <div class="card">
                <h3>UÇUŞ TELEMETRİSİ</h3>
                <div class="dial-grid">
                    <div class="dial"><div id="val-alt" class="dial-val">0.0 m</div><div class="dial-lbl">İrtifa</div></div>
                    <div class="dial"><div id="val-spd" class="dial-val">0.0 m/s</div><div class="dial-lbl">Yer Hızı</div></div>
                    <div class="dial"><div id="val-yaw" class="dial-val">000°</div><div class="dial-lbl">Yönelim (Heading)</div></div>
                    <div class="dial"><div id="val-bat" class="dial-val">%100</div><div class="dial-lbl">Batarya</div></div>
                </div>

                <div style="margin-top: 20px;">
                    <h3>GÖREV KOMUTLARI</h3>
                    <button class="btn btn-danger" onclick="alert('Acil RTL Komutu İletildi!')">ACİL RTL (EVE DÖN)</button>
                    <button class="btn btn-primary" onclick="alert('Otonom Mod Değiştirildi!')">OTONOM / MANUEL MOD</button>
                </div>
            </div>
        </div>

        <script>
            setInterval(async () => {
                try {
                    const res = await fetch('/api/state');
                    const data = await res.json();
                    
                    const stateEl = document.getElementById('lock-state');
                    stateEl.innerText = data.lock_status;
                    if (data.lock_status === 'LOCKED') {
                        stateEl.className = 'badge badge-locked';
                    } else if (data.lock_status === 'LOCKING') {
                        stateEl.className = 'badge badge-locking';
                    } else {
                        stateEl.className = 'badge badge-idle';
                    }

                    document.getElementById('lock-time').innerText = `${data.lock_duration.toFixed(2)}s / 4.0s`;
                    const pct = Math.min(100, (data.lock_duration / 4.0) * 100);
                    document.getElementById('lock-bar').style.width = pct + '%';

                    if (data.telemetry) {
                        document.getElementById('val-alt').innerText = `${data.telemetry.IHA_irtifa.toFixed(1)} m`;
                        document.getElementById('val-spd').innerText = `${data.telemetry.IHA_hiz.toFixed(1)} m/s`;
                        document.getElementById('val-yaw').innerText = `${Math.round(data.telemetry.IHA_yonelme)}°`;
                        document.getElementById('val-bat').innerText = `%${data.telemetry.IHA_batarya}`;
                    }
                } catch(e) {}
            }, 200);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


def start_web_dashboard(host: str = "0.0.0.0", port: int = 8080):
    """Web GCS sunucusunu arka planda ayağa kaldırır."""
    import uvicorn
    thread = threading.Thread(
        target=lambda: uvicorn.run(web_app, host=host, port=port, log_level="warning"),
        daemon=True,
        name="WebDashboardThread"
    )
    thread.start()
    logger.info(f"AeroCombat Web GCS Görev Kontrol İstasyonu başlatıldı -> http://127.0.0.1:{port}")
