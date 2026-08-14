# Depo Takip Sistemi

Mutfak, kapı ve pencere üretimi yapan bir firmanın deposunu takip etmek için
yazılmış, tarayıcıdan çalışan bir uygulama. Tek bilgisayarda çalışır, internet
gerektirmez, verinin tamamı `veri/depo.db` dosyasında durur.

---

## Çalıştırma

Finder'dan **`calistir.command`** dosyasına çift tıklayın. Uygulama açılır ve
tarayıcı kendiliğinden `http://127.0.0.1:5051` adresine gider.
Durdurmak için açılan Terminal penceresinde `Ctrl+C` yapın.

Terminalden çalıştırmak isterseniz:

```bash
cd ~/Desktop/recedot && ./calistir.command
```

**İlk giriş:** kullanıcı `admin`, şifre `admin123` — girer girmez
_Şifre değiştir_ ekranından bunu değiştirin.

---

## Temel mantık

Sistemin üzerine kurulu olduğu üç kural:

**1. Stok hiçbir yerde sabit sayı olarak tutulmaz.**
Her rakam, `hareketler` tablosundaki giriş ve çıkışların toplamıdır. Bu yüzden
"bu 12 levha nereye gitti" sorusunun cevabı her zaman vardır. Yanlış kayıt
silinmez; yönetici **ters kayıt** (storno) ile iptal eder, ikisi de dökümde kalır.

**2. Stok ürün değil, varyant seviyesinde tutulur.**
Aynı profil 4 renkte, aynı kapak 40 dekorda durur. "MDF Levha 18mm'den 40 adet
var" bilgisi iş görmez; hangi dekordan kaç adet olduğu iş görür. Bu yüzden
hiyerarşi **Ürün → Varyant (renk/ölçü) → Stok** şeklindedir.

**3. Fiziksel stok ile kullanılabilir stok ayrıdır.**
Bir projeye rezerve edilen mal fiziken depoda durur ama başka işe verilemez.

    kullanılabilir = fiziksel stok − aktif rezervasyonlar

---

## Ekranlar

| Ekran | Ne işe yarar |
|---|---|
| **Panel** | Stok değeri, kritik kalemler, son hareketler, fire oranı, açık projeler |
| **Stok Listesi** | Arama ve filtreyle tüm kalemler; Excel'e aktarılabilir |
| **Ürünler** | Ürün ve varyant tanımları, minimum stok seviyeleri |
| **Giriş / Çıkış** | Mal girişi, üretim sarfı, sevkiyat, fire, iadeler — çok satırlı giriş |
| **Depo Transferi** | Depolar arası aktarım; iki kayıt oluşur, toplam stok değişmez |
| **Hareket Dökümü** | Her hareketin kim tarafından ne zaman yapıldığı |
| **Projeler** | İş emirleri, malzeme rezervasyonu, proje malzeme maliyeti |
| **Sayım** | Körlemesine fiziksel sayım ve fark raporu |
| **Raporlar** | Sipariş önerisi, stok değeri, fire analizi, hareket özeti |
| **Barkod / Etiket** | Barkod üretimi ve A4 raf etiketi basımı |
| **Toplu Ürün Aktarımı** | Mevcut ürün listesini Excel'den tek seferde alma |
| **Tanımlar** | Depo, kategori, tedarikçi, kullanıcı, yedekleme, işlem geçmişi |

---

## Roller

| Rol | Yetkiler |
|---|---|
| **Usta / Üretim** | Stoğu görür, sadece üretim sarfı girer |
| **Depo Sorumlusu** | Tüm hareketler, ürün/tanım yönetimi, sayım, transfer |
| **Yönetici** | Hepsi + kullanıcı yönetimi, hareket iptali, işlem geçmişi |

Her hareket, işlemi yapan kullanıcıyla birlikte kaydedilir.

---

## Öne çıkan davranışlar

- **Stok eksiye düşmez.** Depoda olmayan mal çıkışı reddedilir; sadece yönetici
  özel bir onay kutusuyla bu kuralı aşabilir.
- **Sayım körlemesine yapılır.** Sayan kişi sistemdeki miktarı göremez; fark
  ancak sayım kapandığında ortaya çıkar. Görebilseydi çoğu kişi sistemdeki
  sayıyı yazar ve sayım hiçbir işe yaramazdı.
- **Sayım farkı, sayımın açıldığı andaki değil kapandığı andaki stoğa göre**
  hesaplanır — sayım sürerken depoya mal girmiş olabilir.
- **Transferin iki ayağı birlikte iptal edilir.** Transfer iki ayrı hareketten
  oluşur; birini iptal edip diğerini bırakmak stoğu bozardı.
- **Malı çıkmış bir giriş iptal edilemez.** Stoğu eksiye düşürecek iptal
  reddedilir ve düzeltmenin sayımla yapılması istenir — sessizce eksi stok
  oluşmasındansa uyarı vermek doğrudur.
- **Rezervasyondan parça parça çıkış yapılabilir.** Sahada malzeme tek seferde
  alınmaz; miktar yazarsanız o kadarı çıkar, kalan rezervasyonda bekler.
- **Türkçe arama.** "mese", "MEŞE", "Meşe" aynı sonucu verir; şapkalı harf ve
  büyük/küçük harf farkı yok sayılır.
- **Sipariş önerisi**, son 90 günün tüketim hızını tedarikçinin teslim
  süresiyle birleştirir: "bu hızda 4 gün sonra biter, tedarik 5 gün sürüyor →
  şimdi sipariş ver."
- **Excel çıktıları** UTF-8 BOM + noktalı virgüllü CSV'dir; Türkçe Excel'de
  çift tıklayınca düzgün açılır.
- **Birim çevrimi.** Bir ürünün hem ana birimi (levha=adet) hem ikincil birimi
  (m²) tutulabilir: 1 levha = 5,04 m².

---

## İlk kurulum: ürün listenizi aktarma

Yüzlerce kalemi tek tek girmek yerine **Toplu Ürün Aktarımı** ekranını kullanın:

1. _Örnek şablonu indir_ deyin, Excel'de açın.
2. Kendi listenizi bu sütun düzenine göre doldurun. Aynı ürünün farklı renkleri
   için **Ürün Kodu'nu aynı yazıp** Renk/Dekor'u değiştirin — sistem tek ürün
   altında varyant açar.
3. Excel'de _Farklı Kaydet → CSV UTF-8_ seçin.
4. Dosyayı yükleyin. Önce kontrol raporu çıkar, hiçbir şey kaydedilmez;
   hatalı satırlar sebebiyle birlikte listelenir. Onayladığınızda aktarılır.

Kategori ve tedarikçi yoksa kendiliğinden açılır. _Açılış Stoğu_ sütununa yazdığınız
miktar bir **mal girişi hareketi** olarak kaydedilir — böylece açılış stoğunun bile
bir kaydı olur.

---

## Barkod ve etiket

Barkod isteğe bağlıdır; sistem barkodsuz da tam çalışır.

- **Tedarikçinin barkodu varsa** ürün kartındaki Barkod alanına girin, okutunca bulunur.
- **Kendi etiketinizi basacaksanız** _Barkod / Etiket_ ekranından barkod üretin
  (`RD000042` biçiminde), sonra seçtiğiniz kalemler için A4 etiket sayfası bastırın.
  Sayfaya 24 etiket sığar. **Yazdırma penceresinde ölçeklemeyi %100 bırakın**,
  küçültülmüş barkod okunmaz.
- **Okutma:** Mal girişi, çıkış ve transfer ekranlarının üstündeki _Barkod okut_
  kutusuna odaklanıp okutun. El terminali (USB/bluetooth okuyucu) klavye gibi
  davrandığı için sürücü ya da ayar gerekmez. Aynı ürünü ikinci kez okutursanız
  yeni satır açılmaz, miktar bir artar.
- **Sayımda okutma:** Sayım ekranında da bir okutma kutusu var; okutunca o
  kalemin satırına atlar. _Okuttukça 1 artır_ işaretliyse her okutma sayılan
  miktarı bir artırır — tek tek sayılan hırdavat için en hızlı yöntem budur.

---

## Yedekleme

Tüm veri tek dosyada: **`veri/depo.db`**.

En kolayı: yönetici olarak soldaki menüden **Yedek Al** deyin — uygulama açıkken
bile tutarlı bir kopya iner (SQLite'ın kendi yedekleme arayüzü kullanılır, tam o
anda kayıt yazılıyor olsa bile bozuk dosya oluşmaz).

Terminalden almak isterseniz uygulama kapalıyken:

```bash
cp ~/Desktop/recedot/veri/depo.db ~/Desktop/depo-yedek-$(date +%Y%m%d).db
```

Geri yüklemek için dosyayı `veri/depo.db` olarak eski yerine koyun.

---

## Bakım komutları

Sıfırdan kurulum (veritabanı yoksa kendiliğinden çalışır):

```bash
.venv/bin/python kurulum.py
```

Deneme verisiyle kurulum — 17 ürün, 36 varyant, 4 aylık hareket geçmişi:

```bash
.venv/bin/python kurulum.py --ornek-veri
```

Veritabanını silip sıfırdan kurma (onay ister):

```bash
.venv/bin/python kurulum.py --sifirla
```

Şifre unutulduysa (uygulamadan şifre değiştirmek için önce girmiş olmak gerekir;
tek yönetici kilitli kalırsa başka çıkış yolu olmazdı):

```bash
.venv/bin/python kurulum.py --sifre-sifirla admin
```

Testler — tüm ekranları ve iş kurallarını geçici bir veritabanında sınar,
gerçek veriye dokunmaz:

```bash
.venv/bin/python testler.py
```

---

## Dosya düzeni

```
recedot/
├── calistir.command      çift tıklayınca uygulamayı başlatır
├── app.py                uygulama kurulumu, şablon filtreleri
├── db.py                 veritabanı bağlantısı, stok sorguları, Türkçe arama
├── auth.py               giriş/çıkış ve rol kontrolü
├── guvenlik.py           şifre hashleme
├── sabitler.py           roller, hareket tipleri, birimler, kategoriler
├── schema.sql            veritabanı şeması
├── kurulum.py            ilk kurulum ve örnek veri
├── testler.py            duman testleri
├── bolumler/             ekran grupları (panel, stok, hareket, barkod, aktarım…)
├── templates/            HTML şablonları
├── static/               stil.css, uygulama.js
└── veri/depo.db          TÜM VERİ BURADA — yedeklenecek dosya
```

---

## Sonraki adımlar için notlar

- **Telefon kamerasıyla barkod okutma:** tarayıcının kameraya erişmesi için
  HTTPS gerekiyor; yerel ağda `http://192.168...` ile çalışmaz. El terminali
  (USB/bluetooth okuyucu) bu sorunu yaşamaz, şu an desteklenen yöntem odur.
- **Ağdan erişim:** `app.py` içindeki `host="127.0.0.1"` değeri `"0.0.0.0"`
  yapılırsa aynı ağdaki diğer cihazlar da bağlanabilir. Bunu yapmadan önce
  varsayılan `admin` şifresini mutlaka değiştirin.
- **Port:** varsayılan 5051. macOS'ta 5000 portunu AirPlay servisi kullandığı
  için o port tercih edilmedi. Değiştirmek için `PORT` ortam değişkenini verin.
