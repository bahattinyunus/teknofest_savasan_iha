import time
import math
from typing import Dict, Any, List
from datetime import datetime
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field


app = FastAPI(
    title="TEKNOFEST Savaşan İHA Mock Hakem Sunucusu",
    description="Yarışma şartnamesine birebir uyumlu yerel test ve simülasyon sunucusu",
    version="2.0.0"
)

# Bellekte tutulan durumlar
aktif_oturumlar: Dict[str, Dict[str, Any]] = {}
takim_telemetrileri: Dict[int, Dict[str, Any]] = {}
kilitlenme_kayitlari: List[Dict[str, Any]] = []
skorlar: Dict[int, int] = {}


# Pydantic Şemaları
class GirisIstegi(BaseModel):
    kullanici_adi: str
    sifre: str


class ZamanSemasi(BaseModel):
    saat: int
    dakika: int
    saniye: int
    milisaniye: int


class TelemetriIstegi(BaseModel):
    takim_numarasi: int
    IHA_enlem: float
    IHA_boylam: float
    IHA_irtifa: float
    IHA_dikilme: float
    IHA_yonelme: float
    IHA_yatis: float
    IHA_hiz: float
    IHA_batarya: int
    IHA_otonom: int
    IHA_kilitlenme: int
    Hedef_merkez_X: int
    Hedef_merkez_Y: int
    Hedef_genislik: int
    Hedef_yukseklik: int
    GPSSaati: ZamanSemasi


class KilitlenmeIstegi(BaseModel):
    kilitlenmeBaslangicZamani: ZamanSemasi
    kilitlenmeBitisZamani: ZamanSemasi
    otonom_kilitlenme: int = 1


def get_current_server_time() -> Dict[str, int]:
    dt = datetime.now()
    return {
        "gun": dt.day,
        "saat": dt.hour,
        "dakika": dt.minute,
        "saniye": dt.second,
        "milisaniye": int(dt.microsecond / 1000)
    }


def generate_mock_rivals(current_team: int) -> List[Dict[str, Any]]:
    """Yarışma havası yaratmak için sanal rakip İHA konumları üretir."""
    t = time.time()
    rivals = []
    
    # Sanal 2 rakip takım (Takım 2 ve Takım 3)
    for tid in [2, 3]:
        if tid == current_team:
            continue
        
        offset = (tid * 1.57)
        radius = 0.003  # Yaklaşık 300m daire yarıçapı
        center_lat = 41.1040
        center_lon = 48.9050
        
        lat = center_lat + radius * math.sin(t * 0.1 + offset)
        lon = center_lon + radius * math.cos(t * 0.1 + offset)
        alt = 85.0 + 15.0 * math.sin(t * 0.2 + offset)
        yaw = float(int((math.degrees(t * 0.1 + offset)) % 360))
        
        rivals.append({
            "takim_numarasi": tid,
            "IHA_enlem": round(lat, 6),
            "IHA_boylam": round(lon, 6),
            "IHA_irtifa": round(alt, 1),
            "IHA_dikilme": 1.2,
            "IHA_yonelme": yaw,
            "IHA_yatis": 5.0,
            "zaman_farki": 45  # 45 ms sanal gecikme
        })
    return rivals


@app.post("/api/giris", status_code=status.HTTP_200_OK)
def giris(payload: GirisIstegi):
    """Takım oturumu açma uç noktası."""
    token = f"token_{payload.kullanici_adi}_{int(time.time())}"
    aktif_oturumlar[payload.kullanici_adi] = {
        "token": token,
        "giris_zamani": time.time()
    }
    return {
        "mesaj": "Giris basarili",
        "token": token,
        "sunucusaati": get_current_server_time()
    }


@app.get("/api/sunucusaati")
def sunucusaati():
    """Sunucu saati sorgulama uç noktası (Zaman senkronizasyonu için)."""
    return get_current_server_time()


@app.post("/api/telemetri_gonder")
def telemetri_gonder(payload: TelemetriIstegi):
    """İHA telemetri alma ve rakip İHA konumlarını dönme uç noktası."""
    takim_telemetrileri[payload.takim_numarasi] = {
        "telemetri": payload.model_dump(),
        "son_alma": time.time()
    }
    
    # Rakipleri üret
    rivals = generate_mock_rivals(payload.takim_numarasi)
    
    return {
        "sunucusaati": get_current_server_time(),
        "konumBilgileri": rivals
    }


@app.post("/api/kilitlenme_bilgisi", status_code=status.HTTP_200_OK)
def kilitlenme_bilgisi(payload: KilitlenmeIstegi):
    """Otonom 4 sn kilitlenme bildirimi uç noktası."""
    # Başlangıç ve bitiş arasındaki süreyi hesapla
    t_start = (
        payload.kilitlenmeBaslangicZamani.saat * 3600 +
        payload.kilitlenmeBaslangicZamani.dakika * 60 +
        payload.kilitlenmeBaslangicZamani.saniye +
        payload.kilitlenmeBaslangicZamani.milisaniye / 1000.0
    )
    t_end = (
        payload.kilitlenmeBitisZamani.saat * 3600 +
        payload.kilitlenmeBitisZamani.dakika * 60 +
        payload.kilitlenmeBitisZamani.saniye +
        payload.kilitlenmeBitisZamani.milisaniye / 1000.0
    )
    
    fark = t_end - t_start
    if fark < 3.8:  # 4.0 sn şartı toleransıyla
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Kilitlenme suresi yetersiz: {fark:.2f} sn. Minimum 4.0 sn gereklidir."
        )

    kayit = {
        "kayit_zamani": datetime.now().isoformat(),
        "sure_sn": round(fark, 2),
        "veri": payload.model_dump()
    }
    kilitlenme_kayitlari.append(kayit)
    
    # Puan ekle (+100)
    skorlar[1] = skorlar.get(1, 0) + 100

    return {
        "durum": "ONAYLANDI",
        "mesaj": "Tebrikler! 4.0 saniye kilitlenme basariyla kabul edildi.",
        "hesaplanan_sure_sn": round(fark, 2),
        "guncel_skor": skorlar[1]
    }


@app.get("/api/cikis")
def cikis():
    """Oturum kapatma uç noktası."""
    return {"mesaj": "Cikis islemi basariyla gerceklestirildi."}


@app.get("/", response_class=HTMLResponse)
def index_dashboard():
    """Görsel canlı hakem paneli."""
    html_content = f"""
    <!DOCTYPE html>
    <html lang="tr">
    <head>
        <meta charset="UTF-8">
        <title>TEKNOFEST Savaşan İHA Hakem Simülatörü</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 24px; }}
            h1 {{ color: #38bdf8; margin-bottom: 4px; }}
            .card {{ background: #1e293b; border-radius: 8px; padding: 20px; margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.2); }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
            th, td {{ text-align: left; padding: 10px; border-bottom: 1px solid #334155; }}
            th {{ background: #0f172a; color: #94a3b8; font-size: 13px; text-transform: uppercase; }}
            .badge {{ display: inline-block; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 12px; }}
            .badge-success {{ background: #059669; color: white; }}
            .badge-info {{ background: #0284c7; color: white; }}
        </style>
    </head>
    <body>
        <h1>TEKNOFEST Savaşan İHA - Hakem Sunucusu İzleme Paneli</h1>
        <p style="color: #94a3b8;">Yerel Simülasyon ve Test Ortamı (Port: 8000)</p>
        
        <div class="card">
            <h2>Aktif Takım Telemetrileri</h2>
            <table>
                <thead>
                    <tr>
                        <th>Takım No</th>
                        <th>İrtifa</th>
                        <th>Hız</th>
                        <th>Batarya</th>
                        <th>Mod</th>
                        <th>Kilit Durumu</th>
                    </tr>
                </thead>
                <tbody>
    """
    for tid, tdata in takim_telemetrileri.items():
        tel = tdata["telemetri"]
        kilit_badge = '<span class="badge badge-success">KİLİTLENDİ</span>' if tel['IHA_kilitlenme'] else '<span>YOK</span>'
        mod_badge = '<span class="badge badge-info">OTONOM</span>' if tel['IHA_otonom'] else '<span>MANUEL</span>'
        html_content += f"""
                    <tr>
                        <td><strong>Takım {tid}</strong></td>
                        <td>{tel['IHA_irtifa']:.1f} m</td>
                        <td>{tel['IHA_hiz']:.1f} m/s</td>
                        <td>%{tel['IHA_batarya']}</td>
                        <td>{mod_badge}</td>
                        <td>{kilit_badge}</td>
                    </tr>
        """
    if not takim_telemetrileri:
        html_content += "<tr><td colspan='6' style='text-align:center; color:#64748b;'>Henüz telemetri gönderen takım yok.</td></tr>"

    html_content += f"""
                </tbody>
            </table>
        </div>

        <div class="card">
            <h2>Onaylanan Kilitlenmeler ({len(kilitlenme_kayitlari)})</h2>
            <table>
                <thead>
                    <tr>
                        <th>Zaman</th>
                        <th>Süre (sn)</th>
                        <th>Başlangıç</th>
                        <th>Bitiş</th>
                        <th>Durum</th>
                    </tr>
                </thead>
                <tbody>
    """
    for k in reversed(kilitlenme_kayitlari):
        v = k["veri"]
        s = v["kilitlenmeBaslangicZamani"]
        e = v["kilitlenmeBitisZamani"]
        html_content += f"""
                    <tr>
                        <td>{k['kayit_zamani']}</td>
                        <td><strong>{k['sure_sn']} s</strong></td>
                        <td>{s['saat']:02d}:{s['dakika']:02d}:{s['saniye']:02d}.{s['milisaniye']:03d}</td>
                        <td>{e['saat']:02d}:{e['dakika']:02d}:{e['saniye']:02d}.{e['milisaniye']:03d}</td>
                        <td><span class="badge badge-success">+100 PUAN</span></td>
                    </tr>
        """
    if not kilitlenme_kayitlari:
        html_content += "<tr><td colspan='5' style='text-align:center; color:#64748b;'>Henüz onaylanan kilitlenme yok.</td></tr>"

    html_content += """
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("mock_server.app:app", host="127.0.0.1", port=8000, reload=True)
