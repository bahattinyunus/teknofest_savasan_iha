# 🌍 Küresel Çaptaki Benzer Yarışmalar, Rakip Programlar ve Kaynak Repolar

Bu doküman; TEKNOFEST Savaşan İHA yarışmasının küresel ölçekteki benzerlerini (ABD, Avrupa, Asya, BAE), uluslararası askeri ve akademik hava muharebe programlarını ve açık kaynaklı en iyi referans GitHub projelerini detaylı olarak inceler.

---

## 🏆 1. Küresel Çaptaki Benzer ve Eşdeğer Yarışmalar

### 1. DARPA ACE (Air Combat Evolution) & AlphaDogfight Trials (ABD)
* **Kategori:** Askeri & Otonom Hava-Hava Muharebesi (Dogfight)
* **Organizasyon:** DARPA (U.S. Defense Advanced Research Projects Agency) & U.S. Air Force
* **Konsept:** İnsan pilotların yerine yapay zeka algoritmalarının görüş menzili içi (Within-Visual-Range / WVR) hava muharebesi yürütmesi. 2020 AlphaDogfight turnuvasında Heron Systems tarafından geliştirilen yapay zeka ajanı, F-16 simülatöründe deneyimli bir F-16 pilotunu **5 - 0** mağlup etmiştir. Program günümüzde modifiye edilmiş otonom **X-62A VISTA (F-16)** jetiyle gerçek gökyüzünde test edilmektedir.
* **TEKNOFEST ile Benzerliği:** TEKNOFEST Savaşan İHA kategorisinin dünyadaki en doğrudan ve en ileri seviye askeri karşılığıdır. Temel Savaş Manevraları (BFM - Basic Fighter Maneuvers), rakibin arkasına geçme ve kilitlenme geometrisi doğrudan bu konseptten esinlenmiştir.

---

### 2. MBZIRC - Mohamed Bin Zayed International Robotics Challenge (Abu Dhabi / BAE)
* **Kategori:** Rogue Drone Interception & Aerial Pursuit (Kaçak İHA Avlama ve Kovalama)
* **Organizasyon:** Khalifa University & ASPIRE
* **Konsept:** Dünyanın en yüksek bütçeli uluslararası robotik yarışmalarından biridir. MBZIRC Challenge 1 etabında otonom insansız hava araçları; havada yüksek hızla manevra yapan kaçak bir hedef İHA'yı ve gökyüzündeki hedefleri (balonlar vb.) GPS'in kısıtlı olduğu dinamik ortamda tespit edip otonom kovalamak ve yakalamak/etkisiz hale getirmek zorundadır.
* **TEKNOFEST ile Benzerliği:** Hareketli bir hava hedefini gerçek zamanlı kamera akışıyla takip etme (Visual Servoing) ve havada temas/kilitlenme kurma mantığı birebir örtüşür.

---

### 3. AUVSI SUAS - Student Unmanned Aerial Systems Competition (ABD / Maryland)
* **Kategori:** Otonom Seyrüsefer, Hedef Tanıma ve Hakem Sunucusu Haberleşmesi
* **Organizasyon:** RoboNation & AUVSI (Association for Unmanned Vehicle Systems International)
* **Konsept:** Dünyanın üniversiteler düzeyindeki en prestijli otonom İHA yarışmasıdır. Takımlar sabit kanatlı İHA'larıyla otonom seyrüsefer, engellerden kaçınma (Sense and Avoid) ve yer hedeflerini otonom sınıflandırma görevlerini icra eder.
* **TEKNOFEST ile Benzerliği:** TEKNOFEST'teki **Merkezi Hakem Sistemi (MHS) REST API** yapısı, doğrudan AUVSI SUAS'ın **"Interoperability (Interop) Server"** altyapısıyla neredeyse aynı mantıkta çalışır (JSON telemetri akışı, zaman senkronizasyonu, görev bildirimleri).

---

### 4. IMAV - International Micro Air Vehicle Conference and Competition (Avrupa)
* **Kategori:** Mikro İHA Otonom İt Dalaşı ve Engelden Kaçınma
* **Organizasyon:** Avrupa MAV Konsorsiyumu (TU Delft, ISAE-Supaero vb.)
* **Konsept:** Drone'ların açık ve kapalı alanda havada asılı veya hareketli hedeflere otonom kilitlenmesi, hava-hava manevraları ve otonom balon patlatma it dalaşı görevleri.

---

### 5. DJI RoboMaster University AI Challenge (Çin / Küresel)
* **Kategori:** Otonom Hedef Tespiti, Zırh Takibi ve Kilitlenme
* **Organizasyon:** DJI
* **Konsept:** Karasal ve hava robotlarının zırh plakalarını yüksek hızlı bilgisayarlı görüyle tespit edip gimbal/kamera merkezinde tutarak sürekli ateş/kilit kurması.
* **TEKNOFEST ile Benzerliği:** Kamera görüntüsündeki hedefin merkezlenmesi, bounding box stabilizasyonu ve milisaniye bazlı kilitlenme sayacı mantığı çok benzerdir.

---

## 💻 2. İncelenmesi Gereken Açık Kaynak GitHub Repoları

AeroCombat'ı daha da ileriye taşımak ve dünya standartlarında algoritmalar entegre etmek için incelenmesi gereken en güçlü açık kaynak repolar:

### A. Hava Muharebesi ve İt Dalaşı Simülasyon Ortamları
1. **[`snu-larr/CloseAirCombat`](https://github.com/snu-larr/CloseAirCombat)**
   * **Açıklama:** Seul Ulusal Üniversitesi Robotik Laboratuvarı tarafından geliştirilen, JSBSim uçuş dinamiği motorunu kullanan 1v1 ve 2v2 hava muharebesi (dogfight) Gymnasium ortamı.
   * **Neden Önemli?** Rakip İHA'nın arkasına geçme manevralarını Reinforcement Learning (PPO, SAC) ile eğitmek için dünyadaki en iyi açık kaynak temeldir.
2. **[`JSBSim-Team/jsbsim`](https://github.com/JSBSim-Team/jsbsim)**
   * **Açıklama:** C++ ile yazılmış, havacılık endüstrisinin 6 serbestlik dereceli (6-DOF) en gelişmiş açık kaynak uçuş dinamiği modeli. DARPA ACE simülasyonlarında da alt motor olarak kullanılmıştır.
3. **[`mrwangyou/DBRL`](https://github.com/mrwangyou/DBRL)**
   * **Açıklama:** Derin pekiştirmeli öğrenme (Deep Reinforcement Learning) tabanlı taktiksel hava muharebesi ve BFM manevra kütüphanesi.

### B. Otonom Önleme (Interception), Görsel Güdüm ve İHA Takibi
4. **[`NadavCherry/SpeckLock`](https://github.com/NadavCherry/SpeckLock)**
   * **Açıklama:** NVIDIA Isaac Sim üzerinde test edilmiş; hareketli kameradan yalnızca 3-15 piksel boyutundaki minik İHA'ları dahi tespit edip Proportional Navigation (PN) ile kovalayan görsel kilitlenme algoritması.
   * **Neden Önemli?** %5 kuralına yaklaşırken uzak mesafedeki hedefleri kaçırmamak için piksel bazlı hareket filtresi tekniği içerir.
5. **[`doguilmak/Drone-Detection-YOLOv11x`](https://github.com/doguilmak/Drone-Detection-YOLOv11x)**
   * **Açıklama:** Gökyüzündeki İHA'ları tespit etmek için özel eğitilmiş yüksek hassasiyetli YOLOv11 model mimarisi ve ağırlıkları.
6. **[`Lexicon121/Strix-Interceptor`](https://github.com/Lexicon121/Strix-Interceptor)**
   * **Açıklama:** Pixhawk otopilotu ile hava hedeflerini otonom olarak yakalayıp etkisiz hale getiren C-UAS (Counter-UAS) açık kaynak avcı drone yazılımı.
7. **[`Gor-Ren/gym-jsbsim`](https://github.com/Gor-Ren/gym-jsbsim)**
   * **Açıklama:** JSBSim ile OpenAI Gym entegrasyonu sağlayan ve otonom seyrüsefer ajanları eğiten referans kütüphane.

---

## 📊 3. Karşılaştırma Matrisi

| Kriter | TEKNOFEST Savaşan İHA | DARPA ACE (AlphaDogfight) | MBZIRC (Drone Intercept) | AUVSI SUAS |
| :--- | :--- | :--- | :--- | :--- |
| **Ana Görev** | Otonom Kamera Kilitlenmesi (4s, %5 alan) | Otonom 1v1 WVR İt Dalaşı (F-16 BFM) | Kaçak İHA'yı Havada Kovalama & Yakalama | Otonom Seyrüsefer, Nesne Sınıflandırma |
| **Platform Tipi** | Sabit Kanat / Döner Kanat | Gerçek/Simüle Savaş Jeti | Yüksek Hızlı Multirotor | Sabit Kanat / VTOL İHA |
| **Hedef Boyutu** | Ekran alanının en az %5'i | Görsel Görüş Hattı (VFR/WVR) | Fiziksel İHA / Balon | Yer Hedefleri (Harf/Şekil) |
| **Hakem Sunucusu** | Var (MHS REST API 1-5 Hz) | Askeri Taktiksel C2 Ağı | Yarışma Hakem Telemetrisi | Var (Interop Server REST API) |
| **Güdüm Yöntemi** | Görüntü İşleme + PN / Visual Servoing | DRL Ajanı (PPO/SAC) + 6-DOF FDM | IBVS + EKF Yörünge Tahmini | GPS Waypoint Navigasyonu |

---

## 💡 4. Küresel Sistemlerden Projemize Uyarlanabilecek Taktikler

1. **Delayed Kalman Filter (DKF) Entegrasyonu:**
   * Kamera sensörü ile model çıkarımı arasındaki 20-40 ms gecikmeyi telafi etmek için MBZIRC takımlarının kullandığı gecikme kompanzasyonlu Kalman filtresi takip algoritmamıza eklenebilir.
2. **Synthetic Data Augmentation (Isaac Sim / Gazebo):**
   * DARPA ve SUAS takımları gibi farklı bulut, güneş açısı ve gökyüzü koşullarını simüle eden sentetik veri setleriyle YOLO modelinin güneş yansımasına karşı bağışıklığı artırılabilir.
3. **Pekiştirmeli Öğrenme ile Agresif Kaçış & Kovalamaca:**
   * `CloseAirCombat` ve `gym-jsbsim` kullanılarak otopilotumuzun GUIDED moduna sadece takip değil, kilitlenilmeye çalışıldığında arkasını vermeyen kaçış manevraları (Break Turn, High Yo-Yo) öğretilebilir.
