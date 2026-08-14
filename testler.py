"""Duman testi: tum ekranlar aciliyor mu, temel is akislari dogru calisiyor mu?

Gecici bir veritabani uzerinde calisir, gercek veriye dokunmaz.

    python testler.py
"""

import contextlib
import io
import os
import sys
import tempfile

import db
from app import uygulama_olustur
from guvenlik import sifre_hashle

BASARILI, BASARISIZ = [], []


def kontrol(baslik, kosul, detay=""):
    if kosul:
        BASARILI.append(baslik)
        print(f"  ✓ {baslik}")
    else:
        BASARISIZ.append((baslik, detay))
        print(f"  ✗ {baslik}  {detay}")


def sayfa(istemci, yol, beklenen=200, baslik=None):
    yanit = istemci.get(yol)
    kontrol(baslik or f"GET {yol}", yanit.status_code == beklenen,
            f"(durum {yanit.status_code}, beklenen {beklenen})")
    return yanit


def main():
    tutamac, gecici_yol = tempfile.mkstemp(suffix=".db")
    os.close(tutamac)
    os.remove(gecici_yol)

    uygulama = uygulama_olustur({"VERITABANI": gecici_yol, "TESTING": True,
                                 "WTF_CSRF_ENABLED": False})
    db.sema_kur(uygulama)

    with uygulama.app_context():
        # -------------------------------------------------- baslangic verisi
        db.calistir("INSERT INTO kullanicilar (kullanici_adi, ad_soyad, sifre_hash, rol)"
                    " VALUES ('admin','Test Yönetici',?, 'yonetici')", (sifre_hashle("1234"),))
        db.calistir("INSERT INTO kullanicilar (kullanici_adi, ad_soyad, sifre_hash, rol)"
                    " VALUES ('usta','Test Usta',?, 'usta')", (sifre_hashle("1234"),))
        db.calistir("INSERT INTO kategoriler (ad) VALUES ('Panel / Levha')")
        db.calistir("INSERT INTO depolar (ad) VALUES ('Ana Depo')")
        db.calistir("INSERT INTO depolar (ad) VALUES ('Atölye')")
        db.calistir("INSERT INTO tedarikciler (ad, teslim_gun) VALUES ('Test Tedarik', 5)")
        db.calistir("""INSERT INTO urunler (kod, ad, kategori_id, tedarikci_id, ana_birim,
                                            ikincil_birim, birim_katsayi)
                       VALUES ('MDF-18','MDF Levha 18mm',1,1,'adet','m2',5.04)""")
        db.calistir("""INSERT INTO varyantlar (urun_id, sku, renk_dekor, olcu, min_stok, birim_fiyat)
                       VALUES (1,'MDF-18-BEYAZ','Beyaz Lamine','2100x2800mm',10,780)""")
        db.calistir("""INSERT INTO varyantlar (urun_id, sku, renk_dekor, min_stok, birim_fiyat)
                       VALUES (1,'MDF-18-CEVIZ','Ceviz H1145',5,820)""")
        db.calistir("""INSERT INTO varyantlar (urun_id, sku, renk_dekor, min_stok, birim_fiyat)
                       VALUES (1,'MDF-18-MESE','Meşe Sonoma',5,760)""")
        db.calistir("INSERT INTO projeler (kod, musteri, tip) VALUES ('2026-001','Test Müşteri','mutfak')")

    istemci = uygulama.test_client()

    print("\n1) Giriş ve yetki")
    print("-" * 50)
    yanit = istemci.get("/panel", follow_redirects=False)
    kontrol("Girişsiz erişim engelleniyor", yanit.status_code == 302,
            f"(durum {yanit.status_code})")

    yanit = istemci.post("/giris", data={"kullanici_adi": "admin", "sifre": "yanlis"})
    kontrol("Yanlış şifre reddediliyor", "hatalı" in yanit.get_data(as_text=True))

    yanit = istemci.post("/giris", data={"kullanici_adi": "admin", "sifre": "1234"},
                         follow_redirects=True)
    kontrol("Doğru şifreyle giriş", "Depo Paneli" in yanit.get_data(as_text=True))

    print("\n2) Tüm ekranlar açılıyor mu?")
    print("-" * 50)
    for yol in ["/panel", "/stok/", "/stok/varyant/1", "/urunler/", "/urunler/1",
                "/urunler/yeni", "/urunler/1/duzenle", "/urunler/1/varyant/yeni",
                "/urunler/varyant/1/duzenle", "/hareket/", "/hareket/yeni?tip=giris",
                "/hareket/yeni?tip=sarf", "/hareket/yeni?tip=fire", "/hareket/transfer",
                "/projeler/", "/projeler/1", "/projeler/yeni", "/projeler/1/duzenle",
                "/sayim/", "/raporlar/", "/raporlar/stok-degeri", "/raporlar/fire",
                "/raporlar/siparis", "/raporlar/hareket-ozet", "/raporlar/proje-maliyet",
                "/tanimlar/depolar", "/tanimlar/kategoriler", "/tanimlar/tedarikciler",
                "/tanimlar/kullanicilar", "/tanimlar/gecmis", "/sifre-degistir",
                "/barkod/", "/aktarim/urun"]:
        sayfa(istemci, yol)
    sayfa(istemci, "/olmayan-sayfa", 404)

    print("\n3) Mal girişi ve stok hesabı")
    print("-" * 50)
    istemci.post("/hareket/yeni", data={
        "tip": "giris", "depo_id": "1", "tarih": "2026-08-01", "belge_no": "IRS-1001",
        "tedarikci_id": "1", "varyant_id": ["1", "2"], "miktar": ["100", "50"],
        "birim_fiyat": ["800", "830"], "satir_aciklama": ["", ""]}, follow_redirects=True)
    with uygulama.app_context():
        kontrol("Giriş sonrası stok 100", db.varyant_stok(1, 1) == 100,
                f"(bulunan {db.varyant_stok(1, 1)})")
        fiyat = db.tek_deger("SELECT birim_fiyat FROM varyantlar WHERE id=1")
        kontrol("Alış fiyatı varyanta işlendi", fiyat == 800, f"(bulunan {fiyat})")

    print("\n4) Stok yetersizken çıkış engelleniyor mu?")
    print("-" * 50)
    yanit = istemci.post("/hareket/yeni", data={
        "tip": "sarf", "depo_id": "1", "tarih": "2026-08-02",
        "varyant_id": ["1"], "miktar": ["500"], "satir_aciklama": [""]},
        follow_redirects=True)
    kontrol("Yetersiz stokta çıkış reddedildi",
            "çıkış yapılamaz" in yanit.get_data(as_text=True))
    with uygulama.app_context():
        kontrol("Stok değişmedi", db.varyant_stok(1, 1) == 100)

    print("\n5) Üretim sarfı")
    print("-" * 50)
    istemci.post("/hareket/yeni", data={
        "tip": "sarf", "depo_id": "1", "tarih": "2026-08-03", "proje_id": "1",
        "varyant_id": ["1"], "miktar": ["30"], "satir_aciklama": [""]},
        follow_redirects=True)
    with uygulama.app_context():
        kontrol("Sarf sonrası stok 70", db.varyant_stok(1, 1) == 70,
                f"(bulunan {db.varyant_stok(1, 1)})")

    print("\n6) Depo transferi")
    print("-" * 50)
    istemci.post("/hareket/transfer", data={
        "kaynak_depo": "1", "hedef_depo": "2", "tarih": "2026-08-04",
        "varyant_id": ["1"], "miktar": ["20"]}, follow_redirects=True)
    with uygulama.app_context():
        kontrol("Kaynak depo 50", db.varyant_stok(1, 1) == 50, f"(bulunan {db.varyant_stok(1, 1)})")
        kontrol("Hedef depo 20", db.varyant_stok(1, 2) == 20, f"(bulunan {db.varyant_stok(1, 2)})")
        kontrol("Toplam stok korundu", db.varyant_stok(1) == 70, f"(bulunan {db.varyant_stok(1)})")

    yanit = istemci.post("/hareket/transfer", data={
        "kaynak_depo": "1", "hedef_depo": "1", "tarih": "2026-08-04",
        "varyant_id": ["1"], "miktar": ["5"]}, follow_redirects=True)
    kontrol("Aynı depoya transfer engellendi",
            "aynı olamaz" in yanit.get_data(as_text=True))

    print("\n7) Proje rezervasyonu")
    print("-" * 50)
    istemci.post("/projeler/1/rezerve", data={
        "varyant_id": "1", "depo_id": "1", "miktar": "40"}, follow_redirects=True)
    with uygulama.app_context():
        kontrol("Rezerve 40", db.varyant_rezerve(1, 1) == 40, f"(bulunan {db.varyant_rezerve(1, 1)})")
        kullanilabilir = db.varyant_stok(1, 1) - db.varyant_rezerve(1, 1)
        kontrol("Kullanılabilir stok 10", kullanilabilir == 10, f"(bulunan {kullanilabilir})")

    yanit = istemci.post("/projeler/1/rezerve", data={
        "varyant_id": "1", "depo_id": "1", "miktar": "30"}, follow_redirects=True)
    kontrol("Kullanılabilirden fazla rezervasyon engellendi",
            "rezerve edilemez" in yanit.get_data(as_text=True))

    istemci.post("/projeler/rezervasyon/1/cikis", data={"tip": "sarf"}, follow_redirects=True)
    with uygulama.app_context():
        kontrol("Rezervasyon çıkışı sonrası stok 10", db.varyant_stok(1, 1) == 10,
                f"(bulunan {db.varyant_stok(1, 1)})")
        kontrol("Rezervasyon kapandı", db.varyant_rezerve(1, 1) == 0)

    print("\n8) Sayım")
    print("-" * 50)
    istemci.post("/sayim/yeni", data={"depo_id": "1", "kapsam": "hepsi"},
                 follow_redirects=True)
    with uygulama.app_context():
        satir = db.sorgu("SELECT * FROM sayim_satirlari WHERE varyant_id=1", tek=True)
        kontrol("Sayım satırları oluştu", satir is not None)
        satir_id = satir["id"] if satir else 0
        sayfa_metni = istemci.get("/sayim/1").get_data(as_text=True)
        kontrol("Açık sayımda sistem miktarı gizli", "Sistem</th>" not in sayfa_metni)

    istemci.post("/sayim/1/kaydet", data={f"sayilan_{satir_id}": "7"}, follow_redirects=True)
    istemci.post("/sayim/1/tamamla", follow_redirects=True)
    with uygulama.app_context():
        kontrol("Sayım farkı stoğa işlendi", db.varyant_stok(1, 1) == 7,
                f"(bulunan {db.varyant_stok(1, 1)})")
        duzeltme = db.sorgu("SELECT * FROM hareketler WHERE tip='sayim'", tek=True)
        kontrol("Sayım düzeltme hareketi kaydedildi", duzeltme is not None)
        kontrol("Düzeltme miktarı -3", duzeltme and round(duzeltme["miktar"], 2) == -3.0,
                f"(bulunan {duzeltme['miktar'] if duzeltme else '-'})")

    print("\n9) Hareket iptali (ters kayıt)")
    print("-" * 50)
    with uygulama.app_context():
        hareket = db.sorgu("SELECT * FROM hareketler WHERE tip='giris' AND varyant_id=2",
                           tek=True)
        onceki = db.varyant_stok(2, 1)
    istemci.post(f"/hareket/{hareket['id']}/iptal", follow_redirects=True)
    with uygulama.app_context():
        kontrol("İptal sonrası stok sıfırlandı", db.varyant_stok(2, 1) == onceki - 50,
                f"(bulunan {db.varyant_stok(2, 1)})")
        kontrol("Orijinal kayıt silinmedi",
                db.sorgu("SELECT 1 FROM hareketler WHERE id=?", (hareket["id"],), tek=True)
                is not None)

    print("\n10) Rol kısıtlamaları")
    print("-" * 50)
    istemci.get("/cikis")
    istemci.post("/giris", data={"kullanici_adi": "usta", "sifre": "1234"})
    yanit = istemci.get("/tanimlar/kullanicilar", follow_redirects=True)
    kontrol("Usta kullanıcı yönetimine giremiyor",
            "yetkisi gerekiyor" in yanit.get_data(as_text=True))
    yanit = istemci.get("/hareket/yeni?tip=giris", follow_redirects=True)
    kontrol("Usta mal girişi yapamıyor", "yetkiniz yok" in yanit.get_data(as_text=True))
    yanit = istemci.get("/hareket/yeni?tip=sarf")
    kontrol("Usta üretim sarfı girebiliyor", yanit.status_code == 200)
    yanit = istemci.get("/tanimlar/depolar", follow_redirects=True)
    kontrol("Usta depo tanımına giremiyor",
            "yetkisi gerekiyor" in yanit.get_data(as_text=True))

    print("\n11) Excel çıktısı")
    print("-" * 50)
    istemci.get("/cikis")
    istemci.post("/giris", data={"kullanici_adi": "admin", "sifre": "1234"})
    yanit = istemci.get("/raporlar/disari/stok")
    metin = yanit.get_data(as_text=True)
    kontrol("Stok CSV indi", yanit.status_code == 200 and "Stok Kodu" in metin)
    kontrol("CSV Excel uyumlu (BOM + noktalı virgül)",
            metin.startswith("﻿") and ";" in metin)
    yanit = istemci.get("/raporlar/disari/hareket")
    kontrol("Hareket CSV indi", yanit.status_code == 200)

    print("\n12) Türkçe arama (büyük/küçük harf ve şapka duyarsız)")
    print("-" * 50)
    with uygulama.app_context():
        for terim in ["Meşe", "meşe", "MEŞE", "mese", "MESE", "sonoma"]:
            bulunan = db.stok_listesi(arama=terim)
            kontrol(f"'{terim}' araması Meşe Sonoma'yı buluyor",
                    any(s["sku"] == "MDF-18-MESE" for s in bulunan),
                    f"({len(bulunan)} sonuç)")
        kontrol("Alakasız arama boş dönüyor", len(db.stok_listesi(arama="zzzzz")) == 0)

    yanit = istemci.get("/stok/ara?q=mese")
    kontrol("Hızlı arama ucu (JSON) çalışıyor",
            yanit.status_code == 200 and any(k["sku"] == "MDF-18-MESE"
                                             for k in yanit.get_json()))

    print("\n13) Barkod ve etiket")
    print("-" * 50)
    sayfa(istemci, "/barkod/")
    istemci.post("/barkod/uret", data={"hepsi": "1"}, follow_redirects=True)
    with uygulama.app_context():
        eksik = db.tek_deger(
            "SELECT COUNT(*) FROM varyantlar WHERE aktif=1"
            " AND (barkod IS NULL OR barkod='')", (), 0)
        kontrol("Barkodsuz varyant kalmadı", eksik == 0, f"({eksik} kaldı)")
        kod = db.tek_deger("SELECT barkod FROM varyantlar WHERE id=1", (), "")
        kontrol("Barkod biçimi RD000001", kod == "RD000001", f"(bulunan {kod})")

    yanit = istemci.get("/barkod/oku?kod=RD000001")
    veri = yanit.get_json()
    kontrol("Okutulan barkod ürüne çevriliyor",
            veri.get("bulundu") and veri.get("id") == 1, str(veri))
    veri = istemci.get("/barkod/oku?kod=OLMAYAN-KOD").get_json()
    kontrol("Tanımsız barkod uyarı veriyor", veri.get("bulundu") is False)
    veri = istemci.get("/barkod/oku?kod=MDF-18-BEYAZ").get_json()
    kontrol("Stok kodundan da okunabiliyor", veri.get("bulundu") is True)

    yanit = istemci.post("/barkod/etiket", data={"varyant_id": ["1", "2"], "adet": "2"})
    metin = yanit.get_data(as_text=True)
    kontrol("Etiket sayfası üretildi", yanit.status_code == 200 and "<svg" in metin)
    kontrol("Her kalemden 2 etiket basıldı", metin.count("<svg") == 4,
            f"({metin.count('<svg')} adet)")
    yanit = istemci.get("/barkod/varyant/1.svg")
    kontrol("Tekil barkod görseli üretiliyor",
            yanit.status_code == 200 and b"<svg" in yanit.data)

    print("\n14) Toplu ürün aktarımı")
    print("-" * 50)
    yanit = istemci.get("/aktarim/sablon")
    kontrol("Şablon indiriliyor",
            yanit.status_code == 200 and "Ürün Kodu" in yanit.get_data(as_text=True))

    csv_metni = (
        "Ürün Kodu;Ürün Adı;Kategori;Tedarikçi;Birim;İkincil Birim;Çevrim Katsayısı;"
        "Renk/Dekor;Ölçü;Stok Kodu;Barkod;Min. Stok;Birim Fiyat;Açılış Stoğu;Depo\n"
        "PRF-70;PVC Pencere Profili;PVC Profil;Star PVC;boy;metre;6,5;Beyaz;6.5m;;;15;540;30;Ana Depo\n"
        "PRF-70;PVC Pencere Profili;PVC Profil;Star PVC;boy;metre;6,5;Antrasit;6.5m;;;15;560;12;Ana Depo\n"
        ";Kodsuz Ürün;;;adet;;;;;;;;;;\n"
        "CAM-ISI;Isıcam 4+16+4;Cam;Cam Merkezi;m2;;;Şeffaf;;;;20;385;;\n"
        "SLK-01;Nötr Silikon;Kimyasal;;adet;;;Beyaz;310ml;;;60;78;25;Olmayan Depo\n"
    )
    yanit = istemci.post(
        "/aktarim/urun",
        data={"dosya": (io.BytesIO(csv_metni.encode("utf-8")), "urunler.csv")},
        content_type="multipart/form-data", follow_redirects=True)
    metin = yanit.get_data(as_text=True)
    kontrol("Önizleme açıldı", "Önizleme" in metin)
    kontrol("Kodsuz satır hata olarak işaretlendi", "ürün kodu boş" in metin)
    kontrol("Olmayan depo hata veriyor", "adında depo tanımlı değil" in metin)

    yanit = istemci.post("/aktarim/urun", data={"onayla": "1"}, follow_redirects=True)
    kontrol("Aktarım tamamlandı", "Aktarım tamamlandı" in yanit.get_data(as_text=True))
    with uygulama.app_context():
        urun = db.sorgu("SELECT * FROM urunler WHERE kod='PRF-70'", tek=True)
        kontrol("Yeni ürün açıldı", urun is not None)
        kontrol("Birim çevrimi okundu",
                urun and urun["ikincil_birim"] == "metre" and urun["birim_katsayi"] == 6.5,
                f"({urun['ikincil_birim'] if urun else '-'})")
        varyant_adedi = db.tek_deger(
            "SELECT COUNT(*) FROM varyantlar WHERE urun_id=?", (urun["id"],), 0)
        kontrol("İki varyant tek ürün altında toplandı", varyant_adedi == 2,
                f"({varyant_adedi} varyant)")
        kategori = db.sorgu("SELECT * FROM kategoriler WHERE ad='PVC Profil'", tek=True)
        kontrol("Eksik kategori kendiliğinden açıldı", kategori is not None)
        tedarikci = db.sorgu("SELECT * FROM tedarikciler WHERE ad='Star PVC'", tek=True)
        kontrol("Eksik tedarikçi kendiliğinden açıldı", tedarikci is not None)
        beyaz = db.sorgu("SELECT * FROM varyantlar WHERE renk_dekor='Beyaz'"
                         " AND urun_id=?", (urun["id"],), tek=True)
        kontrol("Açılış stoğu hareket olarak yazıldı",
                db.varyant_stok(beyaz["id"], 1) == 30,
                f"(bulunan {db.varyant_stok(beyaz['id'], 1)})")
        kontrol("SKU otomatik üretildi", beyaz["sku"].startswith("PRF-70"),
                f"({beyaz['sku']})")
        kontrol("Türkçe karakterli ürün de aktarıldı",
                db.sorgu("SELECT 1 FROM urunler WHERE kod='CAM-ISI'", tek=True) is not None)

    print("\n15) Yedekleme")
    print("-" * 50)
    yanit = istemci.get("/tanimlar/yedek")
    kontrol("Yedek dosyası indiriliyor",
            yanit.status_code == 200 and yanit.data[:15] == b"SQLite format 3")
    istemci.get("/cikis")
    istemci.post("/giris", data={"kullanici_adi": "usta", "sifre": "1234"})
    yanit = istemci.get("/tanimlar/yedek", follow_redirects=True)
    kontrol("Usta yedek alamıyor", "yetkisi gerekiyor" in yanit.get_data(as_text=True))
    yanit = istemci.get("/barkod/", follow_redirects=True)
    kontrol("Usta barkod ekranına giremiyor",
            "yetkisi gerekiyor" in yanit.get_data(as_text=True))

    print("\n16) Hareket iptali (transfer, tekrar, eksi stok)")
    print("-" * 50)
    istemci.get("/cikis")
    istemci.post("/giris", data={"kullanici_adi": "admin", "sifre": "1234"})

    with uygulama.app_context():
        d1_once, d2_once = db.varyant_stok(1, 1), db.varyant_stok(1, 2)
    istemci.post("/hareket/transfer", data={
        "kaynak_depo": "1", "hedef_depo": "2", "tarih": "2026-08-05",
        "varyant_id": ["1"], "miktar": ["5"]}, follow_redirects=True)
    with uygulama.app_context():
        kontrol("Transfer uygulandı", db.varyant_stok(1, 2) == d2_once + 5)
        ayak = db.sorgu("SELECT * FROM hareketler WHERE tip='transfer_cikis'"
                        " ORDER BY id DESC", tek=True)
        duz_once = db.tek_deger(
            "SELECT COUNT(*) FROM hareketler WHERE tip='duzeltme'", (), 0)

    yanit = istemci.post(f"/hareket/{ayak['id']}/iptal", follow_redirects=True)
    kontrol("Transferin iki ayağı birlikte iptal edildi",
            "her iki ayağı" in yanit.get_data(as_text=True))
    with uygulama.app_context():
        kontrol("Kaynak depo eski haline döndü", db.varyant_stok(1, 1) == d1_once,
                f"({db.varyant_stok(1, 1)} / beklenen {d1_once})")
        kontrol("Hedef depo eski haline döndü", db.varyant_stok(1, 2) == d2_once,
                f"({db.varyant_stok(1, 2)} / beklenen {d2_once})")
        duz_sonra = db.tek_deger(
            "SELECT COUNT(*) FROM hareketler WHERE tip='duzeltme'", (), 0)
        kontrol("İki adet 'duzeltme' kaydı oluştu", duz_sonra - duz_once == 2,
                f"({duz_sonra - duz_once} kayıt)")

    yanit = istemci.post(f"/hareket/{ayak['id']}/iptal", follow_redirects=True)
    kontrol("Aynı hareket ikinci kez iptal edilemiyor",
            "zaten iptal edilmiş" in yanit.get_data(as_text=True))

    # Malı çıkmış bir girişin iptali stoğu eksiye düşürürdü; engellenmeli
    istemci.post("/hareket/yeni", data={
        "tip": "giris", "depo_id": "1", "tarih": "2026-08-06",
        "varyant_id": ["3"], "miktar": ["10"], "birim_fiyat": [""],
        "satir_aciklama": [""]}, follow_redirects=True)
    with uygulama.app_context():
        giris = db.sorgu("SELECT * FROM hareketler WHERE varyant_id=3 AND tip='giris'"
                         " ORDER BY id DESC", tek=True)
    istemci.post("/hareket/yeni", data={
        "tip": "sarf", "depo_id": "1", "tarih": "2026-08-07",
        "varyant_id": ["3"], "miktar": ["10"], "satir_aciklama": [""]},
        follow_redirects=True)
    yanit = istemci.post(f"/hareket/{giris['id']}/iptal", follow_redirects=True)
    kontrol("Stoğu eksiye düşürecek iptal engellendi",
            "iptal edilemez" in yanit.get_data(as_text=True))
    with uygulama.app_context():
        kontrol("Stok bozulmadı", db.varyant_stok(3, 1) == 0,
                f"({db.varyant_stok(3, 1)})")
        kontrol("Sayım düzeltmesi iptal edilemiyor", True)
    sayim_hareketi = None
    with uygulama.app_context():
        sayim_hareketi = db.sorgu("SELECT * FROM hareketler WHERE tip='sayim'", tek=True)
    yanit = istemci.post(f"/hareket/{sayim_hareketi['id']}/iptal", follow_redirects=True)
    kontrol("Sayım kaydı geri alınamıyor",
            "geri alınamaz" in yanit.get_data(as_text=True))

    print("\n17) Rezervasyondan kısmi çıkış")
    print("-" * 50)
    with uygulama.app_context():
        prf = db.sorgu("SELECT v.id FROM varyantlar v JOIN urunler u ON u.id=v.urun_id"
                       " WHERE u.kod='PRF-70' AND v.renk_dekor='Beyaz'", tek=True)
        prf_id = prf["id"]
    istemci.post("/projeler/1/rezerve", data={
        "varyant_id": str(prf_id), "depo_id": "1", "miktar": "20"},
        follow_redirects=True)
    with uygulama.app_context():
        rez = db.sorgu("SELECT * FROM rezervasyonlar WHERE varyant_id=? AND durum='aktif'",
                       (prf_id,), tek=True)
        kontrol("Rezervasyon açıldı", rez is not None and rez["miktar"] == 20)
        rez_id = rez["id"]

    yanit = istemci.post(f"/projeler/rezervasyon/{rez_id}/cikis",
                         data={"tip": "sarf", "miktar": "8"}, follow_redirects=True)
    kontrol("Kısmi çıkış bildirildi", "rezervasyonda 12 bekliyor" in yanit.get_data(as_text=True))
    with uygulama.app_context():
        rez = db.sorgu("SELECT * FROM rezervasyonlar WHERE id=?", (rez_id,), tek=True)
        kontrol("Rezervasyonda 12 kaldı", rez["miktar"] == 12 and rez["durum"] == "aktif",
                f"({rez['miktar']} / {rez['durum']})")
        kontrol("Depodan 8 düştü", db.varyant_stok(prf_id, 1) == 22,
                f"({db.varyant_stok(prf_id, 1)})")

    yanit = istemci.post(f"/projeler/rezervasyon/{rez_id}/cikis",
                         data={"tip": "sarf", "miktar": "50"}, follow_redirects=True)
    kontrol("Rezervasyondan fazlası çıkarılamıyor",
            "daha fazlası çıkarılamaz" in yanit.get_data(as_text=True))

    istemci.post(f"/projeler/rezervasyon/{rez_id}/cikis", data={"tip": "sarf"},
                 follow_redirects=True)
    with uygulama.app_context():
        rez = db.sorgu("SELECT * FROM rezervasyonlar WHERE id=?", (rez_id,), tek=True)
        kontrol("Kalan çıkınca rezervasyon kapandı", rez["durum"] == "kullanildi")
        kontrol("Depoda 10 kaldı", db.varyant_stok(prf_id, 1) == 10,
                f"({db.varyant_stok(prf_id, 1)})")

    print("\n18) Şifre sıfırlama (komut satırı)")
    print("-" * 50)
    import kurulum
    from guvenlik import sifre_dogrula
    eski_getpass = kurulum.getpass.getpass
    kurulum.getpass.getpass = lambda *a, **k: "yeniSifre1"
    try:
        with uygulama.app_context():
            # Komutun kendi ekrana yazdiklari test ciktisini kirletmesin
            with contextlib.redirect_stdout(io.StringIO()):
                sonuc = kurulum.sifre_sifirla("usta")
                yok_sonuc = kurulum.sifre_sifirla("boyle-biri-yok")
            kontrol("Şifre sıfırlandı", sonuc == 0)
            k = db.sorgu("SELECT * FROM kullanicilar WHERE kullanici_adi='usta'", tek=True)
            kontrol("Yeni şifre geçerli", sifre_dogrula(k["sifre_hash"], "yeniSifre1"))
            kontrol("Eski şifre geçersiz", not sifre_dogrula(k["sifre_hash"], "1234"))
            kontrol("Olmayan kullanıcı reddedildi", yok_sonuc == 1)
    finally:
        kurulum.getpass.getpass = eski_getpass

    os.remove(gecici_yol)

    print("\n" + "=" * 50)
    print(f"  {len(BASARILI)} test geçti, {len(BASARISIZ)} test başarısız")
    print("=" * 50)
    if BASARISIZ:
        for baslik, detay in BASARISIZ:
            print(f"  ✗ {baslik} {detay}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
