# TEKNOFEST Savaşan İHA MAVLink ve Otopilot Entegrasyon Rehberi

Bu rehber, Pixhawk otopilot kartının (ArduPlane / PX4) ve ArduPilot SITL simülatörünün AeroCombat sistemine nasıl bağlanacağını anlatır.

---

## 1. ArduPilot SITL Simülatörünü Başlatma

Saha uçuşuna çıkmadan önce tüm otonom yönlendirme ve telemetri akışını bilgisayarınızda test edebilirsiniz:

1. **ArduPilot SITL Kurulumu (WSL2 / Linux veya Windows Cygwin):**
```bash
sim_vehicle.py -v ArduPlane --console --map
```
Bu komut varsayılan olarak `tcp:127.0.0.1:5760` portunda bir MAVLink sunucusu açar.

2. **AeroCombat'ı SITL'e Bağlama:**
`config/default_config.yaml` içinde:
```yaml
otopilot:
  baglanti_dizgesi: "tcp:127.0.0.1:5760"
  baud_rate: 115200
  simulasyon: false
```
Artık `main.py` çalıştığında doğrudan SITL'den gerçek uçuş fiziği ve telemetrisi okunur.

---

## 2. Pixhawk / Cube Donanım Bağlantısı

Fiziksel uçuşta Jetson / Companion PC ile Pixhawk genellikle **TELEM 2** portu üzerinden USB-Serial (FTDI) kablosuyla bağlanır:

* **Jetson / Linux Bağlantı Yolu:** `/dev/ttyUSB0` veya `/dev/ttyTHS1`
* **Windows GCS Bağlantı Yolu:** `COM3`, `COM4` vb.

### Mission Planner Üzerinden Ayarlanması Gereken Parametreler:
1. `SERIAL2_PROTOCOL = 2` (MAVLink 2)
2. `SERIAL2_BAUD = 115` (115200 baud)
3. **Telemetri Frekansları (Akış Hızları):**
   * `SR2_POSITION = 5` (GPS koordinatları 5 Hz)
   * `SR2_EXTRA1 = 10` (Attitude: Roll, Pitch, Yaw 10 Hz)
   * `SR2_EXTRA2 = 5` (VFR_HUD: Hız, tırmanma oranı 5 Hz)
   * `SR2_STATUS = 2` (Batarya ve sistem durumu 2 Hz)

---

## 3. Otonom Güdüm (Guided Mode Komutları)

`autopilot/guidance.py` modülü hedef İHA kadrajda merkezde tutulacak şekilde otopilota yönelim komutları üretir:
* Hedef sağdaysa $\rightarrow$ sağa dönüş ve yatış (Roll/Yaw rate)
* Hedef aşağıdaysa $\rightarrow$ dalış açısı (Pitch down)
* Bu komutlar MAVLink üzerinden `SET_ATTITUDE_TARGET` veya `SET_POSITION_TARGET_GLOBAL_INT` mesajlarıyla otopilota iletilir.
