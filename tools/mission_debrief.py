import os
import sys
import glob
import json
import argparse
from typing import Optional, Dict, Any, List

# Proje ana dizinini path'e ekle
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def find_latest_session(logs_dir: str = "logs") -> Optional[str]:
    """En son kaydedilen uçuş oturum klasörünü bulur."""
    sessions = glob.glob(os.path.join(logs_dir, "session_*"))
    if not sessions:
        return None
    sessions.sort(key=os.path.getmtime, reverse=True)
    return sessions[0]


def parse_and_print_debrief(session_dir: str, export_html: bool = False) -> Dict[str, Any]:
    """Uçuş oturumundaki CSV, JSONL ve summary dosyalarını analiz ederek debrief raporu basar."""
    print("\n" + "=" * 75)
    print("      TEKNOFEST SAVAŞAN İHA - UÇUŞ SONRASI GÖREV DEĞERLENDİRME (DEBRIEF)     ")
    print("=" * 75 + "\n")

    summary_file = os.path.join(session_dir, "flight_summary.json")
    events_file = os.path.join(session_dir, "events.jsonl")
    telemetry_file = os.path.join(session_dir, "telemetry.csv")

    summary_data = {}
    if os.path.exists(summary_file):
        with open(summary_file, "r", encoding="utf-8") as f:
            summary_data = json.load(f)

    events: List[Dict[str, Any]] = []
    if os.path.exists(events_file):
        with open(events_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

    # Konsol Çıktısı
    print(f" [*] Oturum Klasörü      : {session_dir}")
    print(f" [*] Toplam Uçuş Süresi   : {summary_data.get('ucus_suresi_sn', 0.0):.1f} saniye")
    print(f" [*] Telemetri Veri Noktası: {summary_data.get('toplam_telemetri_noktasi', 0)} adet")
    print(f" [*] İrtifa Aralığı       : {summary_data.get('asgari_irtifa_m', 0.0):.1f}m - {summary_data.get('maksimum_irtifa_m', 0.0):.1f}m")
    print(f" [*] Azami Yer Hızı       : {summary_data.get('maksimum_hiz_m_s', 0.0):.1f} m/s ({summary_data.get('maksimum_hiz_m_s', 0.0)*3.6:.1f} km/h)")
    print(f" [*] Batarya Tüketimi     : %{summary_data.get('baslangic_batarya', 100)} -> %{summary_data.get('bitis_batarya', 100)} (Harcanan: %{summary_data.get('tuketilen_batarya_yuzdesi', 0)})")
    print(f" [*] Başarılı Kilit Sayısı: {summary_data.get('onaylanan_kilitlenme_sayisi', 0)} KİLİT")
    print(f" [*] Tahmini Görev Puanı  : +{summary_data.get('kazanilan_tahmini_puan', 0)} PUAN 🎯")

    print("\n" + "-" * 75)
    print(" KİLİTLENME VE KRİTİK GÖREV OLAYLARI ZAMAN ÇİZELGESİ:")
    print("-" * 75)
    if not events:
        print(" (Bu oturumda kaydedilmiş olay bulunamadı)")
    else:
        for idx, ev in enumerate(events, 1):
            t_str = ev.get("time_str", "").split("T")[-1][:8]
            ev_name = ev.get("event", "")
            data_str = ev.get("data", "")[:45]
            print(f"  {idx:02d}. [{t_str}] {ev_name:<20} | {data_str}")

    print("=" * 75)

    if export_html:
        html_path = os.path.join(session_dir, "debrief_report.html")
        html_content = f"""<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <title>AeroCombat - Uçuş Görev Değerlendirme Raporu</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 24px; }}
        h1 {{ color: #38bdf8; }}
        .card {{ background: #1e293b; border-radius: 8px; padding: 20px; margin-bottom: 20px; }}
        .stat-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-top: 10px; }}
        .stat {{ background: #0f172a; padding: 12px; border-radius: 6px; text-align: center; }}
        .stat-val {{ font-size: 20px; font-weight: bold; color: #38bdf8; }}
        .stat-lbl {{ font-size: 11px; color: #94a3b8; text-transform: uppercase; margin-top: 4px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
        th, td {{ padding: 8px 12px; border-bottom: 1px solid #334155; text-align: left; }}
        th {{ background: #0f172a; color: #94a3b8; }}
    </style>
</head>
<body>
    <h1>🦅 AeroCombat - Uçuş Görev Değerlendirme Raporu</h1>
    <div class="card">
        <h3>Uçuş Özeti ({session_dir})</h3>
        <div class="stat-grid">
            <div class="stat"><div class="stat-val">{summary_data.get('ucus_suresi_sn', 0.0):.1f}s</div><div class="stat-lbl">Uçuş Süresi</div></div>
            <div class="stat"><div class="stat-val">{summary_data.get('onaylanan_kilitlenme_sayisi', 0)}</div><div class="stat-lbl">Onaylanan Kilit</div></div>
            <div class="stat"><div class="stat-val">+{summary_data.get('kazanilan_tahmini_puan', 0)}</div><div class="stat-lbl">Kazanılan Puan</div></div>
            <div class="stat"><div class="stat-val">%{summary_data.get('tuketilen_batarya_yuzdesi', 0)}</div><div class="stat-lbl">Batarya Tüketimi</div></div>
        </div>
    </div>
    <div class="card">
        <h3>Görev Olayları ({len(events)} Olay)</h3>
        <table>
            <thead><tr><th>#</th><th>Zaman</th><th>Olay Adı</th><th>Detay</th></tr></thead>
            <tbody>
        """
        for i, ev in enumerate(events, 1):
            html_content += f"<tr><td>{i}</td><td>{ev.get('time_str', '')}</td><td><strong>{ev.get('event', '')}</strong></td><td><code>{ev.get('data', '')}</code></td></tr>"
        html_content += """
            </tbody>
        </table>
    </div>
</body>
</html>"""
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"\n [✓] HTML Değerlendirme Raporu Oluşturuldu: {html_path}\n")

    return summary_data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TEKNOFEST Savaşan İHA Uçuş Değerlendirme Aracı (Debrief)")
    parser.add_argument("--session", type=str, default="", help="İncelenecek session klasörü (Boşsa en son oturumu seçer)")
    parser.add_argument("--html", action="store_true", help="HTML rapor dosyası oluştur")
    args = parser.parse_args()

    target_session = args.session
    if not target_session:
        target_session = find_latest_session("logs")

    if not target_session or not os.path.exists(target_session):
        print("HATA: Uygun bir uçuş oturum klasörü bulunamadı. Lütfen önce bir uçuş çalıştırın veya --session belirtin.")
        sys.exit(1)

    parse_and_print_debrief(target_session, export_html=args.html)
