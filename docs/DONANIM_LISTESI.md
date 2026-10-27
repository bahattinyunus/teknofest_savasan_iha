# TEKNOFEST Savaşan İHA Önerilen Donanım Listesi ve Mimarisi

Bir Savaşan İHA sisteminin uçuş ve kilitlenme başarısı doğrudan donanım bileşenlerinin kararlılığına bağlıdır. Aşağıda dereceye giren takımların kullandığı kanıtlanmış donanım konfigürasyonları yer almaktadır.

---

## 1. Görev Bilgisayarı (Companion Computer)

| Donanım | Avantajları | Önerilen Model Formatı | Güç Tüketimi |
| :--- | :--- | :--- | :--- |
| **NVIDIA Jetson Orin Nano (8GB)** *(Tavsiye Edilen)* | 40 TOPS AI performansı, TensorRT ile 45+ FPS YOLOv8 | TensorRT (.engine) FP16 | 7 - 15 W |
| **NVIDIA Jetson Xavier NX** | Çok kararlı, yüksek CUDA çekirdeği | TensorRT (.engine) | 10 - 15 W |
| **Raspberry Pi 5 (8GB) + Hailo-8 M.2** | Hafif, düşük maliyet, 26 TOPS NPU | Hailo HEF formatı | 5 - 12 W |
| **Intel NUC / Mini PC (Core i5/i7)** | Yüksek x86 işlem gücü, OpenVINO desteği | OpenVINO / ONNX | 25 - 45 W |

---

## 2. Kamera Seçimi

Uçuş ortamında titreşim, yüksek hız ve güneş ışığı faktörleri nedeniyle kamera seçimi çok kritiktir:

* **Tavsiye Edilen Sensör:** Sony IMX296 veya IMX477 (Global Shutter özellikli).
  * *Neden Global Shutter?* Rolling shutter kameralar pervane titreşiminde satır satır tarama yaptığı için görüntüde dalgalanma (jello) yaratır ve hedef kutuları titrer. Global shutter tüm kareyi tek anda yakalar.
* **Lens Açısı (FOV):** 70° - 90° FOV lensler idealdir. (Açı çok geniş olursa hedef %5 boyut şartını sağlayamaz, çok dar olursa hedef kadrajdan anında kaçar).
* **Filtre:** UV / ND Filtresi (Güneş parlamalarını ve aşırı pozlamayı önler).

---

## 3. Otopilot ve Uçuş Kontrol Kartı

* **Cube Orange / Cube Blue:** Çift/Üçlü IMU yedekliliği, ısı kontrollü sensörler.
* **Holybro Pixhawk 6C / 6X:** Güçlü STM32H7 işlemci, MAVLink 2.0 desteği, kararlı ArduPlane / PX4 firmware.
* **GPS & Pusula:** Here 3 / Here 4 RTK GPS (Çok hızlı uydu kilitlenmesi ve pusula kalibrasyonu).

---

## 4. Haberleşme ve Veri Bağı (Datalink)

1. **Uçak $\leftrightarrow$ Yer Kontrol İstasyonu (GCS):**
   * **RFD900x / RFD868x (veya Holybro Sik Telemetry):** Uzun menzil (10+ km), 57600/115200 baud ile MAVLink telemetri aktarımı.
   * **Sik / Ubiquiti Rocket M5 (5.8 GHz):** Canlı yüksek çözünürlüklü video akışı ve companion PC SSH/RTSP erişimi için kablosuz köprü.
2. **Yer Kontrol İstasyonu $\leftrightarrow$ Hakem Sunucusu:**
   * Yarışma çadırında tahsis edilen Gigabit Ethernet RJ45 kablosu.

---

## 5. Güç Dağıtımı ve BEC

Görev bilgisayarı (Jetson) ani akım çekişlerinde voltaj düşmesi yaşarsa yeniden başlar (brownout reset) ve uçuş ortasında kilitlenme sistemi çöker:
* Jetson için mutlaka **ayrılmış (isolated) 5V/5A veya 12V/5A yüksek kaliteli regülatör (BEC)** kullanılmalıdır.
* Motor ESC bataryası ile görev bilgisayarı bataryasının ayrılması veya LC filtre eklenmesi tavsiye edilir.
