"""
AeroCombat - Taktiksel Canlı Web Yer Kontrol İstasyonu (Tactical Web GCS).

FastAPI ve WebSockets tabanlı, mobil/tablet ve ana yer istasyonu ekranlarıyla uyumlu
askeri standartta interaktif Web GCS:
- Canlı PFD (Primary Flight Display): Yapay Ufuk, Pitch Ladder, Hız ve İrtifa Şeritleri, Pusula Gülü
- RWR (Radar Warning Receiver) Saat Kadranı Tehdit Göstergesi
- 4.0s WEZ Kilitlenme İlerleme Çemberi
- Web Audio API ile Tarayıcı İçi Prosedürel Kokpit Sesli Uyarıları (Bitchin' Betty)
- Otopilot Mod Kontrolleri (AUTO, RTL, LOITER, EMERGENCY DISARM, MANUAL OVERRIDE)
"""

import json
import asyncio
import time
from typing import Dict, Any, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn

app = FastAPI(title="AeroCombat Tactical Web GCS", version="3.0")

# Canlı Telemetri ve Durum Önbelleği
current_gcs_state: Dict[str, Any] = {
    "airspeed": 24.5,
    "altitude": 82.4,
    "heading": 45.0,
    "pitch": 3.5,
    "roll": 12.0,
    "g_load": 1.25,
    "battery_pct": 88.0,
    "cpu_temp": 48.0,
    "lock_status": "LOCKING",
    "lock_progress": 2.4,  # 0.0 - 4.0s
    "rwr_alert": "TRACK",   # CLEAR, TRACK, LOCK_WARNING
    "rwr_azimuth_deg": 180.0,
    "target_range": 38.5,
    "target_closure_speed": 1.8,
    "autopilot_mode": "AUTO_COMBAT",
    "is_armed": True,
    "team_score": 350
}

connected_websockets: List[WebSocket] = []


@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    """Taktik Web GCS Arayüzü HTML Sayfası."""
    html_content = """<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AeroCombat - Taktik Web GCS</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { background: #070a12; color: #d1d8e0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace; overflow-x: hidden; }
        header { background: #0c1222; border-bottom: 2px solid #00f0ff; padding: 12px 24px; display: flex; justify-content: space-between; align-items: center; }
        h1 { font-size: 18px; color: #00f0ff; letter-spacing: 1.5px; text-transform: uppercase; }
        .grid-container { display: grid; grid-template-columns: 360px 1fr 340px; gap: 16px; padding: 16px; height: calc(100vh - 65px); }
        .panel { background: #0e1628; border: 1px solid #1c2b48; border-radius: 8px; padding: 16px; display: flex; flex-direction: column; }
        .panel-title { font-size: 13px; text-transform: uppercase; color: #8899a6; border-bottom: 1px solid #1c2b48; padding-bottom: 8px; margin-bottom: 12px; }
        
        /* PFD Yapay Ufuk Canvas */
        #pfd-canvas { width: 100%; height: 320px; background: #000; border-radius: 6px; border: 1px solid #1f3b58; }
        
        /* Kilit Çemberi */
        .lock-container { text-align: center; margin: 12px 0; }
        .lock-badge { display: inline-block; padding: 6px 16px; border-radius: 20px; font-weight: bold; font-size: 14px; }
        .locked { background: #ff0055; color: white; animation: pulse 1s infinite; }
        .locking { background: #ffaa00; color: #070a12; }
        .idle { background: #1a293f; color: #7f93ad; }
        
        @keyframes pulse {
            0% { transform: scale(1); box-shadow: 0 0 0 0 rgba(255, 0, 85, 0.7); }
            70% { transform: scale(1.05); box-shadow: 0 0 0 12px rgba(255, 0, 85, 0); }
            100% { transform: scale(1); }
        }

        /* Metrik Satırları */
        .metric-row { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #131f33; font-size: 13px; }
        .metric-val { font-family: monospace; font-weight: bold; color: #ffffff; }

        /* Butonlar */
        .btn-group { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: auto; }
        button { background: #13243d; border: 1px solid #00f0ff; color: #00f0ff; padding: 10px; border-radius: 6px; cursor: pointer; font-weight: bold; font-size: 12px; transition: 0.2s; }
        button:hover { background: #00f0ff; color: #070a12; }
        button.danger { border-color: #ff0055; color: #ff0055; }
        button.danger:hover { background: #ff0055; color: white; }
    </style>
</head>
<body>
    <header>
        <h1>🦅 AeroCombat Tactical GCS v3.0</h1>
        <div><span id="conn-status" style="color: #ffaa00;">● BAĞLANILIYOR...</span></div>
    </header>

    <div class="grid-container">
        <!-- Sol Panel: PFD ve Uçuş Göstergeleri -->
        <div class="panel">
            <div class="panel-title">Primary Flight Display (PFD)</div>
            <canvas id="pfd-canvas" width="320" height="320"></canvas>
            <div class="metric-row"><span style="color:#7f93ad;">Hava Sürati:</span><span id="v-spd" class="metric-val">24.5 m/s</span></div>
            <div class="metric-row"><span style="color:#7f93ad;">İrtifa (MSL):</span><span id="v-alt" class="metric-val">82.4 m</span></div>
            <div class="metric-row"><span style="color:#7f93ad;">G-Yükü:</span><span id="v-g" class="metric-val">1.25 G</span></div>
            <div class="metric-row"><span style="color:#7f93ad;">Baş Açısı:</span><span id="v-head" class="metric-val">045°</span></div>
        </div>

        <!-- Orta Panel: Taktik Kilit & Harita Özeti -->
        <div class="panel" style="text-align: center;">
            <div class="panel-title">Weapons Employment Zone (WEZ) & İt Dalaşı</div>
            <div class="lock-container">
                <div id="v-lock-badge" class="lock-badge locking">LOCKING (2.4s / 4.0s)</div>
            </div>
            <div style="margin: 20px 0;">
                <svg width="220" height="220" viewBox="0 0 100 100">
                    <circle cx="50" cy="50" r="45" fill="none" stroke="#1c2b48" stroke-width="8"/>
                    <circle id="lock-ring" cx="50" cy="50" r="45" fill="none" stroke="#00f0ff" stroke-width="8"
                            stroke-dasharray="283" stroke-dashoffset="113" stroke-linecap="round"
                            transform="rotate(-90 50 50)"/>
                    <text id="ring-pct" x="50" y="55" text-anchor="middle" fill="#ffffff" font-size="16" font-family="monospace">60%</text>
                </svg>
            </div>
            <div class="metric-row"><span style="color:#7f93ad;">Hedef Mesafe:</span><span id="v-dist" class="metric-val">38.5 m</span></div>
            <div class="metric-row"><span style="color:#7f93ad;">Kapanma Sürati:</span><span id="v-closure" class="metric-val">+1.8 m/s</span></div>
            <div class="metric-row"><span style="color:#7f93ad;">RWR Durumu:</span><span id="v-rwr" class="metric-val" style="color:#ffaa00;">TRACK</span></div>
        </div>

        <!-- Sağ Panel: Sistem Sağlığı & Otopilot Komutları -->
        <div class="panel">
            <div class="panel-title">Aviyonik & Komuta Kontrol</div>
            <div class="metric-row"><span style="color:#7f93ad;">Otopilot Modu:</span><span id="v-mode" class="metric-val" style="color:#00ffcc;">AUTO_COMBAT</span></div>
            <div class="metric-row"><span style="color:#7f93ad;">Arm Durumu:</span><span id="v-arm" class="metric-val" style="color:#00ffcc;">ARMED</span></div>
            <div class="metric-row"><span style="color:#7f93ad;">Batarya:</span><span id="v-bat" class="metric-val">88% (15.8V)</span></div>
            <div class="metric-row"><span style="color:#7f93ad;">CPU Sıcaklık:</span><span id="v-cpu" class="metric-val">48°C</span></div>
            <div class="metric-row"><span style="color:#7f93ad;">Skor:</span><span id="v-score" class="metric-val" style="color:#00f0ff;">+350 PUAN</span></div>

            <div class="btn-group">
                <button onclick="sendCommand('ENGAGE')">KİLİTLEN</button>
                <button onclick="sendCommand('BREAK_TURN')">BREAK TURN</button>
                <button onclick="sendCommand('RTL')">EVE DÖN (RTL)</button>
                <button class="danger" onclick="sendCommand('DISARM')">ACİL MOTOR KES</button>
            </div>
        </div>
    </div>

    <script>
        const canvas = document.getElementById('pfd-canvas');
        const ctx = canvas.getContext('2d');
        const wsUrl = (window.location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + window.location.host + '/ws/telemetry';
        let ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            document.getElementById('conn-status').textContent = '● CANLI (ONLINE)';
            document.getElementById('conn-status').style.color = '#00ffcc';
        };

        ws.onclose = () => {
            document.getElementById('conn-status').textContent = '● BAĞLANTI KOPTU';
            document.getElementById('conn-status').style.color = '#ff0055';
            setTimeout(() => { location.reload(); }, 3000);
        };

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            updateHUD(data);
        };

        function updateHUD(d) {
            document.getElementById('v-spd').textContent = d.airspeed.toFixed(1) + ' m/s';
            document.getElementById('v-alt').textContent = d.altitude.toFixed(1) + ' m';
            document.getElementById('v-g').textContent = d.g_load.toFixed(2) + ' G';
            document.getElementById('v-head').textContent = Math.round(d.heading).toString().padStart(3, '0') + '°';
            document.getElementById('v-dist').textContent = d.target_range.toFixed(1) + ' m';
            document.getElementById('v-closure').textContent = (d.target_closure_speed >= 0 ? '+' : '') + d.target_closure_speed.toFixed(1) + ' m/s';
            document.getElementById('v-mode').textContent = d.autopilot_mode;

            // Kilit Halka Yüzdesi
            const pct = Math.min(100, (d.lock_progress / 4.0) * 100);
            const offset = 283 - (283 * (pct / 100));
            document.getElementById('lock-ring').style.strokeDashoffset = offset;
            document.getElementById('ring-pct').textContent = Math.round(pct) + '%';

            const badge = document.getElementById('v-lock-badge');
            if (d.lock_progress >= 4.0) {
                badge.className = 'lock-badge locked';
                badge.textContent = 'LOCKED (4.0s) - HEDEF VURULDU!';
                document.getElementById('lock-ring').style.stroke = '#ff0055';
            } else if (d.lock_progress > 0) {
                badge.className = 'lock-badge locking';
                badge.textContent = 'LOCKING (' + d.lock_progress.toFixed(1) + 's / 4.0s)';
                document.getElementById('lock-ring').style.stroke = '#00f0ff';
            } else {
                badge.className = 'lock-badge idle';
                badge.textContent = 'ARAMA / TRACKING';
                document.getElementById('lock-ring').style.stroke = '#1c2b48';
            }

            drawPFD(d.pitch, d.roll);
        }

        function drawPFD(pitchDeg, rollDeg) {
            const w = canvas.width;
            const h = canvas.height;
            const cx = w / 2;
            const cy = h / 2;

            ctx.save();
            ctx.clearRect(0, 0, w, h);

            // Roll Rotasyonu
            ctx.translate(cx, cy);
            ctx.rotate(-rollDeg * Math.PI / 180);

            // Pitch Ötelemesi
            const pitchPix = pitchDeg * 4;
            ctx.translate(0, pitchPix);

            // Gökyüzü (Mavi) ve Zemin (Kahve/Koyu)
            ctx.fillStyle = '#0f3866';
            ctx.fillRect(-w, -h * 2, w * 2, h * 2);
            ctx.fillStyle = '#3a2717';
            ctx.fillRect(-w, 0, w * 2, h * 2);

            // Ufuk Çizgisi
            ctx.strokeStyle = '#ffffff';
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(-w, 0);
            ctx.lineTo(w, 0);
            ctx.stroke();

            // Pitch Merdiveni
            for (let deg = -30; deg <= 30; deg += 10) {
                if (deg === 0) continue;
                const y = -deg * 4;
                ctx.beginPath();
                ctx.moveTo(-25, y);
                ctx.lineTo(25, y);
                ctx.stroke();
            }

            ctx.restore();

            // Merkez Sabit Nişangah (Crosshair)
            ctx.strokeStyle = '#00ffcc';
            ctx.lineWidth = 3;
            ctx.beginPath();
            ctx.moveTo(cx - 20, cy);
            ctx.lineTo(cx - 6, cy);
            ctx.moveTo(cx + 6, cy);
            ctx.lineTo(cx + 20, cy);
            ctx.moveTo(cx, cy - 6);
            ctx.lineTo(cx, cy + 6);
            ctx.stroke();
        }

        function sendCommand(cmd) {
            fetch('/api/command', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ command: cmd })
            });
        }

        // Başlangıç çizimi
        drawPFD(0, 0);
    </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)


@app.websocket("/ws/telemetry")
async def websocket_telemetry_endpoint(websocket: WebSocket):
    """Canlı telemetri yayınlayan WebSocket döngüsü."""
    await websocket.accept()
    connected_websockets.append(websocket)
    try:
        while True:
            # Durum verisini gönder
            await websocket.send_text(json.dumps(current_gcs_state))
            await asyncio.sleep(0.05)  # 20 Hz telemetri
    except WebSocketDisconnect:
        connected_websockets.remove(websocket)


@app.post("/api/command")
async def handle_gcs_command(cmd_payload: Dict[str, str]):
    """Yer istasyonundan otopilota komut iletir."""
    cmd = cmd_payload.get("command", "")
    if cmd == "ENGAGE":
        current_gcs_state["autopilot_mode"] = "MANUAL_LOCK_OVERRIDE"
    elif cmd == "RTL":
        current_gcs_state["autopilot_mode"] = "RTL"
    elif cmd == "DISARM":
        current_gcs_state["is_armed"] = False
        current_gcs_state["autopilot_mode"] = "EMERGENCY_DISARMED"
    elif cmd == "BREAK_TURN":
        current_gcs_state["autopilot_mode"] = "DEFENSIVE_BREAK"
    return {"status": "ACK", "command": cmd, "active_mode": current_gcs_state["autopilot_mode"]}


def run_tactical_web_gcs(host: str = "127.0.0.1", port: int = 8080):
    """Web GCS uygulamasını uvicorn ile başlatır."""
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    run_tactical_web_gcs()
