# TEKNOFEST Savaşan İHA Yarışma Rehberi & Strateji Kılavuzu

Bu doküman, TEKNOFEST Savaşan İHA (Fighter UAV) yarışmasına hazırlanan takımların uçuş günü başarılı olmaları için gereken tüm teknik stratejileri, hakem kurallarını ve sık yapılan hataları derler.

---

## 1. Yarışmanın Amacı ve Puanlama Mantığı

Savaşan İHA müsabakası, İHA'ların tanımlı bir hava sahasında tamamen otonom veya yarı otonom olarak birbirlerini tespit etmesi, takip etmesi ve hava-hava it dalaşı (dogfight) manevralarıyla **kilitlenme (lock-on)** sağlamasını amaçlar.

### Puan Dağılımı ve Temel Kriterler:
* **Geçerli Kilitlenme:** +100 Puan.
* **Hatalı / Geçersiz Kilitlenme:** -50 Puan (Hedef ortada yokken kilit paketi atmak eksi puan yazdırır).
* **Telemetri Kesintisi:** Saniyede -2 Puan (Hakem sunucusuna telemetri gönderilemeyen her saniye ceza puanı uygulanır).
* **Geofence Sınır İhlali:** -200 Puan veya Diskalifiye (Sanal sınırı aşmak acil kırım/RTL gerektirir).

---

## 2. Otonom Kilitlenme Kuralları (%5 Kuralı ve 4 Saniye)

Bir kilitlenmenin hakemler tarafından geçerli sayılması için şu 3 şartın **aynı anda** ve **kesintisiz 4.0 saniye** boyunca sürmesi gerekir:

1. **Kadraj Merkezleme:** Hedef İHA, kameranın görüş açısının (FOV) merkezinde belirlenen tolerans dairesi/kutusu içinde tutulmalıdır.
2. **Hedef Alan Oranı (%5 Kuralı):** Hedef İHA'nın kamera çözünürlüğündeki alanı (Genişlik $\times$ Yükseklik), tüm ekran alanının en az **%5'i** kadar olmalıdır. Hedef çok uzaktaysa (örneğin %1-2 piksel kaplıyorsa) kilitlenme sayacı başlatılamaz.
3. **Zaman Damgası & Bildirim:** Kilitlenme 4.0 saniyeye ulaştığında, en geç **2 saniye içinde** `/api/kilitlenme_bilgisi` uç noktasına sunucu saatine senkronize zaman damgalarıyla iletilmelidir.

---

## 3. Hakem Sunucusu Haberleşme Testi (Pre-Flight Check)

Yarışma sahasında uçuşa çıkmadan önce yapılan teknik kontrolde **Haberleşme Testi** yapılır:
1. Yer kontrol istasyonu, hakem sunucusunun Ethernet ağına bağlanır.
2. `/api/giris` yapılarak oturum token'ı alınır.
3. `/api/sunucusaati` ile sistem saatleri arasındaki ofset milisaniye cinsinden ölçülür.
4. Uçak pistte dururken telemetri paketi gönderilir; sunucunun `HTTP 200` dönüp dönmediği ve format hatası (`HTTP 204`) vermediği kontrol edilir.
5. Simüle kilitlenme paketi iletilip hakem sisteminde skor artışı test edilir.

---

## 4. Saha İpuçları ve Sık Karşılaşılan Hatalar

* **Rolling Shutter vs Global Shutter:** Uçak motorunun ve pervanesinin oluşturduğu titreşim, ucuz kameralarda "Jello effect" (jöle dalgalanması) yaratır ve YOLO tespitini bozar. Mutlaka vibrasyon takozları ve mümkünse **Global Shutter** kamera kullanın.
* **NTP ve Saat Kayması:** Windows/Linux laptop saati ile hakem sunucu saati birkaç saniye farklı olabilir. Kod içerisindeki `TimeSynchronizer` sınıfı RTT hesabı yaparak sunucu saatine dinamik senkronize olur.
* **Güneş Işığı & Bulut:** Gökyüzündeki bulutları veya güneş yansımasını model uçak sanabilir. Model eğitim veri setine mutlaka "negative samples" (boş gökyüzü, kuşlar, bulutlar) eklenmelidir.
* **WiFi / Telemetri Kopması:** Sahada 10-15 takım aynı anda radyo frekansı kullandığından 2.4 GHz WiFi kanalları tıkanabilir. Yer istasyonu ile hakem sunucusu arasına kablolu Ethernet çekilmeli, uçak ile yer istasyonu arasında 5.8 GHz veya 868/915 MHz telemetri tercih edilmelidir.
