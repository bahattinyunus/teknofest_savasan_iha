# TEKNOFEST Savaşan İHA Haberleşme Protokolü & JSON Şemaları

Bu doküman, Hakem Sunucusu (Merkezi Hakem Sistemi - MHS) ile Yer Kontrol İstasyonu arasındaki HTTP REST API protokolünü ve JSON veri yapılarını detaylandırır.

---

## 1. Uç Noktalar (Endpoints) Özeti

| Metot | Uç Nokta | Açıklama | Beklenen HTTP Kodu |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/giris` | Takım oturumu açma | `200 OK` |
| `GET` | `/api/sunucusaati` | Sunucu saati sorgusu (NTP eşitleme) | `200 OK` |
| `POST` | `/api/telemetri_gonder` | Uçak anlık telemetrisi (1 - 5 Hz) | `200 OK` / `204 Format Yanlış` |
| `POST` | `/api/kilitlenme_bilgisi` | 4.0 saniyelik başarılı kilitlenme bildirimi | `200 OK` / `400 Hatalı Süre` |
| `GET` | `/api/cikis` | Uçuş görevi bitişinde oturumu kapatma | `200 OK` |

---

## 2. Detaylı JSON Şemaları

### A. Oturum Açma (`POST /api/giris`)
```json
{
  "kullanici_adi": "takim1",
  "sifre": "sifre123"
}
```

### B. Sunucu Saati Sorgusu (`GET /api/sunucusaati`)
```json
{
  "gun": 15,
  "saat": 14,
  "dakika": 30,
  "saniye": 22,
  "milisaniye": 450
}
```

### C. Telemetri Gönderimi (`POST /api/telemetri_gonder`)
Bu paket İHA uçuş halindeyken saniyede 1 ila 5 kez (örn. 3 Hz) hakem sunucusuna iletilir:
```json
{
  "takim_numarasi": 1,
  "IHA_enlem": 41.104250,
  "IHA_boylam": 28.905120,
  "IHA_irtifa": 85.4,
  "IHA_dikilme": 2.1,
  "IHA_yonelme": 185.0,
  "IHA_yatis": 1.2,
  "IHA_hiz": 18.5,
  "IHA_batarya": 88,
  "IHA_otonom": 1,
  "IHA_kilitlenme": 0,
  "Hedef_merkez_X": 640,
  "Hedef_merkez_Y": 360,
  "Hedef_genislik": 220,
  "Hedef_yukseklik": 160,
  "GPSSaati": {
    "saat": 14,
    "dakika": 30,
    "saniye": 22,
    "milisaniye": 480
  }
}
```

#### Sunucu Yanıtı:
Sunucu bu isteğe karşılık güncel sunucu saatini ve havadaki rakip İHA'ların bilinen koordinatlarını döner:
```json
{
  "sunucusaati": {
    "saat": 14,
    "dakika": 30,
    "saniye": 22,
    "milisaniye": 485
  },
  "konumBilgileri": [
    {
      "takim_numarasi": 2,
      "IHA_enlem": 41.106500,
      "IHA_boylam": 28.907800,
      "IHA_irtifa": 92.0,
      "IHA_dikilme": 0.0,
      "IHA_yonelme": 120.0,
      "IHA_yatis": 4.0,
      "zaman_farki": 45
    }
  ]
}
```

---

### D. Kilitlenme Bildirimi (`POST /api/kilitlenme_bilgisi`)
Kilitlenme motoru 4.0 saniyeyi başarıyla tamamladığında en geç 2 saniye içinde sunucuya iletilir:
```json
{
  "kilitlenmeBaslangicZamani": {
    "saat": 14,
    "dakika": 30,
    "saniye": 15,
    "milisaniye": 200
  },
  "kilitlenmeBitisZamani": {
    "saat": 14,
    "dakika": 30,
    "saniye": 19,
    "milisaniye": 250
  },
  "otonom_kilitlenme": 1
}
```

---

## 3. Olası HTTP Hata Kodları ve Çözümleri

* **`204 NO CONTENT (Format Yanlış)`**: JSON anahtarlarında eksiklik veya veri tiplerinde uyuşmazlık vardır (örneğin string yerine int gönderilmesi). Bu repodaki `TelemetriPaketi` dataclass yapısı bu hatayı tamamen engeller.
* **`400 BAD REQUEST`**: Kilitlenme süresi 4.0 saniyenin altında kaldığında veya zaman damgaları geriye doğru olduğunda sunucu isteği reddeder.
* **`401 UNAUTHORIZED`**: Oturum açılmamış veya token süresi dolmuştur. `RefereeClient` otomatik olarak yeniden giriş yapar.
