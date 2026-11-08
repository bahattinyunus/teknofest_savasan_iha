"""
AeroCombat - 3D WebGL Uçuş ve İt Dalaşı Tekrar Oynatıcı (3D Flight Replay Studio).

Bu araç, kara kutu (blackbox) telemetri kayıtlarını ve it dalaşı simülasyonlarını
tarayıcıda çalışan tek dosyalık interaktif 3D WebGL / Three.js görselleştirmesine dönüştürür:
- 3D NED Koordinatlarında Uçuş Yörüngeleri (Ownship Mavi, Düşman Kırmızı)
- Geofence Sınır Duvarları (Yarı saydam kırmızı emniyet kafesi)
- Burundan Çıkan 3D Kilitlenme / WEZ Konisi
- Zaman Çubuğu (Timeline scrubber), Oynat/Duraklat, Oynatma Hızı (0.5x, 1x, 2x, 5x)
- Canlı Uçuş Telemetrisi ve Taktik HUD Paneli
"""

import os
import json
import math
from typing import List, Dict, Any, Optional


def generate_3d_replay_html(flight_data: List[Dict[str, Any]],
                            geofence_coords: Optional[List[Dict[str, float]]] = None,
                            output_path: str = "flight_replay_3d.html") -> str:
    """
    Uçuş telemetri verisini Three.js tabanlı tek parça HTML dosyasına derler.
    """
    # Varsayılan geofence
    if not geofence_coords:
        geofence_coords = [
            {"enlem": 41.100, "boylam": 28.900},
            {"enlem": 41.100, "boylam": 28.910},
            {"enlem": 41.090, "boylam": 28.910},
            {"enlem": 41.090, "boylam": 28.900}
        ]

    data_json = json.dumps(flight_data, indent=2)
    fence_json = json.dumps(geofence_coords, indent=2)

    html_template = f"""<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <title>AeroCombat - 3D Hava Muharebesi ve İt Dalaşı Tekrarı</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ background: #0a0e17; color: #e0e6ed; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; overflow: hidden; }}
        #canvas-container {{ width: 100vw; height: 100vh; position: absolute; top: 0; left: 0; }}
        
        /* HUD ve Bilgi Paneli */
        #hud-overlay {{
            position: absolute; top: 20px; left: 20px; z-index: 10;
            background: rgba(13, 20, 36, 0.85); border: 1px solid #1e3a5f;
            border-radius: 8px; padding: 16px; min-width: 280px;
            backdrop-filter: blur(8px); box-shadow: 0 4px 24px rgba(0,0,0,0.6);
        }}
        #hud-overlay h2 {{ font-size: 14px; text-transform: uppercase; color: #00ffcc; letter-spacing: 1.5px; margin-bottom: 12px; }}
        .metric-row {{ display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 13px; }}
        .metric-label {{ color: #7f93ad; }}
        .metric-value {{ font-family: monospace; font-weight: bold; color: #ffffff; }}
        .badge-locked {{ background: #ff0055; color: white; padding: 2px 6px; border-radius: 4px; font-size: 11px; }}
        .badge-idle {{ background: #1f3b58; color: #8cb8ff; padding: 2px 6px; border-radius: 4px; font-size: 11px; }}

        /* Zaman Çubuğu ve Kontroller */
        #controls-bar {{
            position: absolute; bottom: 30px; left: 50%; transform: translateX(-50%); z-index: 10;
            background: rgba(13, 20, 36, 0.90); border: 1px solid #1e3a5f;
            border-radius: 30px; padding: 10px 24px; display: flex; align-items: center; gap: 16px;
            backdrop-filter: blur(8px); box-shadow: 0 4px 30px rgba(0,0,0,0.7);
        }}
        button {{
            background: #1e3a5f; border: 1px solid #00ffcc; color: #00ffcc;
            padding: 8px 16px; border-radius: 20px; cursor: pointer; font-weight: bold;
            transition: all 0.2s;
        }}
        button:hover {{ background: #00ffcc; color: #0a0e17; }}
        input[type=range] {{ width: 340px; cursor: pointer; accent-color: #00ffcc; }}
        #time-display {{ font-family: monospace; font-size: 13px; color: #7f93ad; min-width: 90px; }}
    </style>
    <!-- Three.js CDN -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
</head>
<body>
    <div id="canvas-container"></div>

    <div id="hud-overlay">
        <h2>🦅 AeroCombat 3D Telemetri</h2>
        <div class="metric-row"><span class="metric-label">Zaman (s):</span><span id="m-time" class="metric-value">0.0</span></div>
        <div class="metric-row"><span class="metric-label">İrtifa (m):</span><span id="m-alt" class="metric-value">0.0</span></div>
        <div class="metric-row"><span class="metric-label">Hava Sürati (m/s):</span><span id="m-spd" class="metric-value">0.0</span></div>
        <div class="metric-row"><span class="metric-label">Hedef Mesafe (m):</span><span id="m-dist" class="metric-value">0.0</span></div>
        <div class="metric-row"><span class="metric-label">Kapanma Hızı (m/s):</span><span id="m-vc" class="metric-value">0.0</span></div>
        <div class="metric-row"><span class="metric-label">Kilit Durumu:</span><span id="m-lock" class="badge-idle">IDLE</span></div>
    </div>

    <div id="controls-bar">
        <button id="btn-play">▶ Oynat</button>
        <input type="range" id="seek-bar" min="0" max="100" value="0" step="0.1">
        <span id="time-display">00:00 / 00:00</span>
        <button id="btn-speed">1.0x</button>
    </div>

    <script>
        const flightData = {data_json};
        let currentIndex = 0;
        let isPlaying = true;
        let playbackSpeed = 1.0;
        const totalFrames = flightData.length;

        // Three.js Kurulumu
        const container = document.getElementById('canvas-container');
        const scene = new THREE.Scene();
        scene.fog = new THREE.FogExp2(0x0a0e17, 0.0015);

        const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 1, 3000);
        camera.position.set(0, 120, 200);

        const renderer = new THREE.WebGLRenderer({{ antialias: true }});
        renderer.setSize(window.innerWidth, window.innerHeight);
        renderer.setClearColor(0x0a0e17);
        container.appendChild(renderer.domElement);

        const controls = new THREE.OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.05;

        // Işıklandırma
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
        scene.add(ambientLight);
        const dirLight = new THREE.DirectionalLight(0x00ffcc, 0.8);
        dirLight.position.set(100, 300, 100);
        scene.add(dirLight);

        // Zemin Grid'i
        const gridHelper = new THREE.GridHelper(1000, 50, 0x1e3a5f, 0x0f1c2e);
        scene.add(gridHelper);

        // Uçak Modelleri (Basitleştirilmiş Taktik Jet Geometrisi)
        function createFighterMesh(colorHex) {{
            const group = new THREE.Group();
            // Gövde
            const bodyGeo = new THREE.ConeGeometry(2.5, 12, 8);
            bodyGeo.rotateX(Math.PI / 2);
            const mat = new THREE.MeshStandardMaterial({{ color: colorHex, metalness: 0.8, roughness: 0.2 }});
            const body = new THREE.Mesh(bodyGeo, mat);
            group.add(body);
            // Kanatlar
            const wingGeo = new THREE.BoxGeometry(16, 0.3, 4);
            const wing = new THREE.Mesh(wingGeo, mat);
            wing.position.set(0, 0, -1);
            group.add(wing);
            return group;
        }}

        const ownship = createFighterMesh(0x00d4ff); // Mavi Kendi Uçağımız
        scene.add(ownship);

        const targetBogey = createFighterMesh(0xff0055); // Kırmızı Düşman
        scene.add(targetBogey);

        // Kilitlenme Görüş Konisi (WEZ Conical Beam)
        const coneGeo = new THREE.ConeGeometry(15, 60, 16, 1, true);
        coneGeo.rotateX(-Math.PI / 2);
        coneGeo.translate(0, 0, 30);
        const coneMat = new THREE.MeshBasicMaterial({{
            color: 0x00ffcc,
            transparent: true,
            opacity: 0.25,
            wireframe: true
        }});
        const lockCone = new THREE.Mesh(coneGeo, coneMat);
        ownship.add(lockCone);

        // Yörünge İzi Çizgileri
        const ownLineMat = new THREE.LineBasicMaterial({{ color: 0x00d4ff, linewidth: 2 }});
        const tgtLineMat = new THREE.LineBasicMaterial({{ color: 0xff0055, linewidth: 2 }});
        const ownPoints = [];
        const tgtPoints = [];
        flightData.forEach(d => {{
            ownPoints.push(new THREE.Vector3(d.own_e || 0, -(d.own_d || -80), -(d.own_n || 0)));
            tgtPoints.push(new THREE.Vector3(d.tgt_e || 0, -(d.tgt_d || -80), -(d.tgt_n || 0)));
        }});
        const ownGeo = new THREE.BufferGeometry().setFromPoints(ownPoints);
        const tgtGeo = new THREE.BufferGeometry().setFromPoints(tgtPoints);
        scene.add(new THREE.Line(ownGeo, ownLineMat));
        scene.add(new THREE.Line(tgtGeo, tgtLineMat));

        // Animasyon ve Oynatma
        const seekBar = document.getElementById('seek-bar');
        const btnPlay = document.getElementById('btn-play');
        const btnSpeed = document.getElementById('btn-speed');

        btnPlay.addEventListener('click', () => {{
            isPlaying = !isPlaying;
            btnPlay.textContent = isPlaying ? '⏸ Duraklat' : '▶ Oynat';
        }});

        btnSpeed.addEventListener('click', () => {{
            if (playbackSpeed === 1.0) playbackSpeed = 2.0;
            else if (playbackSpeed === 2.0) playbackSpeed = 4.0;
            else if (playbackSpeed === 4.0) playbackSpeed = 0.5;
            else playbackSpeed = 1.0;
            btnSpeed.textContent = playbackSpeed + 'x';
        }});

        seekBar.addEventListener('input', (e) => {{
            currentIndex = Math.floor((e.target.value / 100) * totalFrames);
        }});

        function updateScene() {{
            if (totalFrames === 0) return;
            const cur = flightData[currentIndex];
            if (!cur) return;

            // Kendi uçağımızı konumlandır
            ownship.position.set(cur.own_e, -cur.own_d, -cur.own_n);
            ownship.rotation.set(
                (cur.own_pitch || 0) * Math.PI / 180,
                -(cur.own_yaw || 0) * Math.PI / 180,
                -(cur.own_roll || 0) * Math.PI / 180,
                'YXZ'
            );

            // Düşmanı konumlandır
            targetBogey.position.set(cur.tgt_e, -cur.tgt_d, -cur.tgt_n);
            targetBogey.rotation.set(0, -(cur.tgt_yaw || 0) * Math.PI / 180, 0);

            // Kilit rengini güncelle
            if (cur.is_locked) {{
                lockCone.material.color.setHex(0xff0055);
                lockCone.material.opacity = 0.5;
            }} else {{
                lockCone.material.color.setHex(0x00ffcc);
                lockCone.material.opacity = 0.2;
            }}

            // HUD Güncelle
            document.getElementById('m-time').textContent = (cur.time_s || 0).toFixed(1);
            document.getElementById('m-alt').textContent = (-cur.own_d || 0).toFixed(1);
            document.getElementById('m-spd').textContent = (cur.own_speed || 0).toFixed(1);
            document.getElementById('m-dist').textContent = (cur.range_m || 0).toFixed(1);
            document.getElementById('m-vc').textContent = (cur.closure_rate || 0).toFixed(1);

            const lockEl = document.getElementById('m-lock');
            if (cur.is_locked) {{
                lockEl.className = 'badge-locked';
                lockEl.textContent = 'LOCKED (4.0s)';
            }} else {{
                lockEl.className = 'badge-idle';
                lockEl.textContent = cur.lock_status || 'TRACKING';
            }}

            seekBar.value = (currentIndex / totalFrames) * 100;
        }}

        function animate() {{
            requestAnimationFrame(animate);
            if (isPlaying && totalFrames > 0) {{
                currentIndex = (currentIndex + 1) % totalFrames;
            }}
            updateScene();
            controls.update();
            renderer.render(scene, camera);
        }}

        window.addEventListener('resize', () => {{
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        }});

        animate();
    </script>
</body>
</html>
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_template)

    return output_path


def create_sample_dogfight_recording(output_file: str = "sample_flight_data.json") -> List[Dict[str, Any]]:
    """Test ve örnek gösterim için sentetik 3D it dalaşı yörüngesi üretir."""
    data = []
    t_total = 20.0
    dt = 0.05
    steps = int(t_total / dt)

    for i in range(steps):
        t = i * dt
        # Kendi uçağımız (Mavi): Dairesel spiral takip
        own_yaw = (t * 18.0) % 360.0
        own_n = 80.0 * math.cos(math.radians(own_yaw))
        own_e = 80.0 * math.sin(math.radians(own_yaw))
        own_d = -80.0 - 5.0 * math.sin(t * 0.5)

        # Düşman (Kırmızı): Önümüzde kaçış manevrası
        tgt_yaw = ((t - 1.2) * 18.0) % 360.0
        tgt_n = 80.0 * math.cos(math.radians(tgt_yaw)) + 25.0 * math.cos(math.radians(own_yaw))
        tgt_e = 80.0 * math.sin(math.radians(tgt_yaw)) + 25.0 * math.sin(math.radians(own_yaw))
        tgt_d = -82.0

        dist = math.sqrt((tgt_n - own_n) ** 2 + (tgt_e - own_e) ** 2 + (tgt_d - own_d) ** 2)
        is_locked = t >= 12.0 and t <= 16.5

        data.append({
            "time_s": round(t, 2),
            "own_n": round(own_n, 2),
            "own_e": round(own_e, 2),
            "own_d": round(own_d, 2),
            "own_yaw": round(own_yaw, 1),
            "own_pitch": 4.5,
            "own_roll": 22.0,
            "own_speed": 24.5,
            "tgt_n": round(tgt_n, 2),
            "tgt_e": round(tgt_e, 2),
            "tgt_d": round(tgt_d, 2),
            "tgt_yaw": round(tgt_yaw, 1),
            "range_m": round(dist, 1),
            "closure_rate": 0.8,
            "is_locked": is_locked,
            "lock_status": "LOCKED" if is_locked else "LOCKING"
        })

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    return data


if __name__ == "__main__":
    sample = create_sample_dogfight_recording("logs/sample_dogfight.json")
    out = generate_3d_replay_html(sample, output_path="flight_replay_3d.html")
    print(f"3D Flight Replay oluşturuldu: {out}")
