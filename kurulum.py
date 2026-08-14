"""Ilk kurulum: veritabanini olusturur, yonetici hesabini ve temel tanimlari acar.

Kullanim:
    python kurulum.py                        # sema + varsayilan tanimlar + yonetici
    python kurulum.py --ornek-veri           # deneme urunleri ve hareketleri ekler
    python kurulum.py --sifirla              # veritabanini SILER ve sifirdan kurar
    python kurulum.py --sifre-sifirla admin  # unutulan sifreyi degistirir
"""

import argparse
import getpass
import os
import random
import sys
from datetime import datetime, timedelta

from guvenlik import sifre_hashle

import db
from app import uygulama_olustur
from sabitler import VARSAYILAN_DEPOLAR, VARSAYILAN_KATEGORILER

VARSAYILAN_YONETICI = ("admin", "Sistem Yöneticisi", "admin123")


def temel_tanimlar():
    eklenen = {"kategori": 0, "depo": 0}
    for ad, aciklama in VARSAYILAN_KATEGORILER:
        if not db.sorgu("SELECT 1 FROM kategoriler WHERE ad = ?", (ad,), tek=True):
            db.calistir("INSERT INTO kategoriler (ad, aciklama) VALUES (?,?)",
                        (ad, aciklama))
            eklenen["kategori"] += 1
    for ad, aciklama in VARSAYILAN_DEPOLAR:
        if not db.sorgu("SELECT 1 FROM depolar WHERE ad = ?", (ad,), tek=True):
            db.calistir("INSERT INTO depolar (ad, aciklama) VALUES (?,?)", (ad, aciklama))
            eklenen["depo"] += 1
    return eklenen


def yonetici_ac():
    varmi = db.tek_deger("SELECT COUNT(*) FROM kullanicilar", (), 0)
    if varmi:
        return None
    kadi, ad, sifre = VARSAYILAN_YONETICI
    db.calistir(
        """INSERT INTO kullanicilar (kullanici_adi, ad_soyad, sifre_hash, rol, aktif)
           VALUES (?,?,?, 'yonetici', 1)""",
        (kadi, ad, sifre_hashle(sifre)))
    return (kadi, sifre)


# --------------------------------------------------------------- ornek veri
ORNEK_URUNLER = [
    # (kod, ad, kategori, birim, ikincil, katsayi, min, fiyat, [varyantlar])
    ("MDF-18", "MDF Levha 18mm", "Panel / Levha", "adet", "m2", 5.04, 10, 780,
     [("Ham", "2100x2800mm"), ("Beyaz Lamine", "2100x2800mm"), ("Ceviz H1145", "2100x2800mm")]),
    ("SUN-18", "Suntalam 18mm", "Panel / Levha", "adet", "m2", 5.04, 8, 690,
     [("Antrasit", "2100x2800mm"), ("Meşe Sonoma", "2100x2800mm")]),
    ("KPK-LAKE", "Lake Mutfak Kapağı", "Mutfak Kapağı", "adet", None, None, 20, 420,
     [("Mat Beyaz", "716x396mm"), ("Antrasit Gri", "716x396mm"), ("Kaşmir", "716x396mm")]),
    ("KPK-PVC", "PVC Membran Kapak", "Mutfak Kapağı", "adet", None, None, 25, 310,
     [("Beyaz", "716x396mm"), ("Ceviz", "716x396mm")]),
    ("TZG-SUNI", "Suni Mermer Tezgah", "Tezgah", "mtul", None, None, 6, 1250,
     [("Beyaz Mermer Desen", "60cm derinlik"), ("Antrasit", "60cm derinlik")]),
    ("PRF-70", "PVC Pencere Profili 70mm", "PVC Profil", "boy", "metre", 6.5, 15, 540,
     [("Beyaz", "6.5m"), ("Altın Meşe", "6.5m"), ("Antrasit Gri", "6.5m")]),
    ("PRF-KANAT", "PVC Kanat Profili", "PVC Profil", "boy", "metre", 6.5, 12, 480,
     [("Beyaz", "6.5m"), ("Antrasit Gri", "6.5m")]),
    ("ALM-KAPI", "Alüminyum Kapı Profili", "Alüminyum Profil", "boy", "metre", 6.0, 8, 920,
     [("Elektrostatik Beyaz", "6m"), ("Eloksal", "6m")]),
    ("CAM-ISI", "Isıcam Ünitesi 4+16+4", "Cam", "m2", None, None, 20, 385,
     [("Şeffaf", "standart"), ("Low-E", "standart")]),
    ("MNT-YAVAS", "Yavaş Kapanan Menteşe", "Hırdavat", "adet", None, None, 200, 42,
     [("Tam Bindirmeli", "110°"), ("Yarım Bindirmeli", "110°")]),
    ("RAY-TEL", "Teleskopik Çekmece Rayı", "Hırdavat", "takim", None, None, 60, 165,
     [("Frenli", "45cm"), ("Frenli", "50cm")]),
    ("KLP-ALM", "Alüminyum Kulp", "Hırdavat", "adet", None, None, 150, 38,
     [("Mat Siyah", "160mm"), ("Krom", "160mm")]),
    ("ISP-PENC", "Pencere İspanyoleti", "Hırdavat", "takim", None, None, 40, 210,
     [("Standart", "1000-1400mm")]),
    ("BND-PVC", "PVC Kenar Bandı 22mm", "Kenar Bandı", "metre", None, None, 500, 4.2,
     [("Beyaz", "22x0.8mm"), ("Ceviz H1145", "22x0.8mm"), ("Antrasit", "22x0.8mm")]),
    ("TUT-PU", "Poliüretan Tutkal", "Kimyasal", "kg", None, None, 25, 195,
     [("D4", "5kg bidon")]),
    ("SLK-NOTR", "Nötr Silikon", "Kimyasal", "adet", None, None, 60, 78,
     [("Şeffaf", "310ml"), ("Beyaz", "310ml")]),
    ("KPK-SEPET", "Kiler Sepeti", "Aksesuar", "takim", None, None, 10, 1450,
     [("Krom", "40cm"), ("Antrasit", "40cm")]),
]

ORNEK_TEDARIKCILER = [
    ("Anadolu Ahşap Panel A.Ş.", "Murat Kaya", "0212 555 10 20", 10),
    ("Star PVC Profil San.", "Elif Demir", "0216 444 30 40", 14),
    ("Cam Merkezi Ltd.", "Hakan Yıldız", "0232 333 50 60", 5),
    ("Hırdavat Dünyası", "Ayşe Şahin", "0224 222 70 80", 3),
    ("Kimtaş Yapı Kimyasalları", "Serkan Ateş", "0312 111 90 10", 7),
]

ORNEK_PROJELER = [
    ("2026-001", "Mehmet Aydın", "mutfak", "uretimde", "Bahçelievler / İstanbul"),
    ("2026-002", "Zeynep Korkmaz", "pencere", "acik", "Ataşehir / İstanbul"),
    ("2026-003", "Ergün İnşaat Ltd.", "karma", "uretimde", "Beylikdüzü / İstanbul"),
    ("2026-004", "Fatma Öztürk", "dolap", "tamamlandi", "Kadıköy / İstanbul"),
]


def ornek_veri():
    if db.tek_deger("SELECT COUNT(*) FROM urunler", (), 0):
        print("  ! Zaten ürün var, örnek veri atlandı.")
        return

    for ad, yetkili, tel, gun in ORNEK_TEDARIKCILER:
        db.calistir("INSERT INTO tedarikciler (ad, yetkili, telefon, teslim_gun)"
                    " VALUES (?,?,?,?)", (ad, yetkili, tel, gun))

    kategori = {r["ad"]: r["id"] for r in db.sorgu("SELECT id, ad FROM kategoriler")}
    tedarikciler = [r["id"] for r in db.sorgu("SELECT id FROM tedarikciler")]
    depolar = [r["id"] for r in db.sorgu("SELECT id FROM depolar ORDER BY id")]
    ana_depo, atolye = depolar[0], depolar[-1]

    for kod, ad, kat, birim, ikincil, katsayi, min_stok, fiyat, varyantlar in ORNEK_URUNLER:
        urun_id = db.calistir(
            """INSERT INTO urunler (kod, ad, kategori_id, tedarikci_id, ana_birim,
                                    ikincil_birim, birim_katsayi, aktif)
               VALUES (?,?,?,?,?,?,?,1)""",
            (kod, ad, kategori.get(kat), random.choice(tedarikciler), birim,
             ikincil, katsayi))
        for i, (renk, olcu) in enumerate(varyantlar, 1):
            db.calistir(
                """INSERT INTO varyantlar (urun_id, sku, renk_dekor, olcu,
                                           min_stok, birim_fiyat, aktif)
                   VALUES (?,?,?,?,?,?,1)""",
                (urun_id, f"{kod}-{i}", renk, olcu, min_stok,
                 round(fiyat * random.uniform(.9, 1.15), 2)))

    for kod, musteri, tip, durum, adres in ORNEK_PROJELER:
        db.calistir(
            """INSERT INTO projeler (kod, musteri, tip, durum, adres, baslangic, teslim)
               VALUES (?,?,?,?,?,?,?)""",
            (kod, musteri, tip, durum, adres,
             (datetime.now() - timedelta(days=random.randint(10, 60))).strftime("%Y-%m-%d"),
             (datetime.now() + timedelta(days=random.randint(-5, 40))).strftime("%Y-%m-%d")))

    varyantlar = db.sorgu("SELECT id, min_stok, birim_fiyat FROM varyantlar")
    projeler = [r["id"] for r in db.sorgu("SELECT id FROM projeler WHERE durum <> 'iptal'")]
    kullanici = db.sorgu("SELECT * FROM kullanicilar LIMIT 1", tek=True)

    # 120 gunluk gecmis. Hareketler kronolojik simule edilir: cikis hicbir zaman
    # o depoda o an bulunan miktardan fazla olmaz, boylece stok eksiye dusmez.
    kayitlar = []
    stok = {}

    def tarih_yaz(gun_once):
        return (datetime.now() - timedelta(days=gun_once)).strftime("%Y-%m-%d")

    for v in varyantlar:
        taban = max(v["min_stok"] * 4, 20)
        stok[(v["id"], ana_depo)] = 0.0
        stok[(v["id"], atolye)] = 0.0

        acilis = round(taban * random.uniform(1.2, 2.0), 2)
        stok[(v["id"], ana_depo)] += acilis
        kayitlar.append((tarih_yaz(120), "giris", v["id"], ana_depo, acilis,
                         v["birim_fiyat"], f"IRS-{random.randint(10000, 99999)}",
                         None, "açılış stoğu"))

        gunler = sorted(random.sample(range(1, 116), random.randint(5, 14)))
        for gun in gunler:
            tarih = tarih_yaz(gun)
            tip = random.choices(["sarf", "sevk", "fire", "giris", "transfer"],
                                 weights=[38, 22, 10, 20, 10])[0]

            if tip == "giris":
                miktar = round(taban * random.uniform(.4, 1.0), 2)
                stok[(v["id"], ana_depo)] += miktar
                kayitlar.append((tarih, "giris", v["id"], ana_depo, miktar,
                                 v["birim_fiyat"], f"IRS-{random.randint(10000, 99999)}",
                                 None, None))
                continue

            if tip == "transfer":
                mevcut = stok[(v["id"], ana_depo)]
                miktar = round(min(mevcut, taban * random.uniform(.1, .3)), 2)
                if miktar <= 0:
                    continue
                stok[(v["id"], ana_depo)] -= miktar
                stok[(v["id"], atolye)] += miktar
                kayitlar.append((tarih, "transfer_cikis", v["id"], ana_depo,
                                 -miktar, None, None, None, "atölyeye sevk"))
                kayitlar.append((tarih, "transfer_giris", v["id"], atolye,
                                 miktar, None, None, None, "ana depodan geldi"))
                continue

            # Cikis: stogu olan bir depo secilir, miktar mevcudu asamaz
            adaylar = [d for d in (ana_depo, atolye) if stok[(v["id"], d)] > 0]
            if not adaylar:
                continue
            depo = random.choice(adaylar)
            istenen = taban * random.uniform(.05, .2)
            miktar = round(min(stok[(v["id"], depo)] * 0.6, istenen), 2)
            if miktar <= 0:
                continue
            stok[(v["id"], depo)] -= miktar
            kayitlar.append((tarih, tip, v["id"], depo, -miktar, None, None,
                             random.choice(projeler) if tip in ("sarf", "sevk") else None,
                             None))

    # Birkac kalemi bilerek kritik seviyeye dusur ki uyari mekanizmasi gorunsun
    for v in random.sample(varyantlar, min(5, len(varyantlar))):
        mevcut = stok[(v["id"], ana_depo)]
        hedef = v["min_stok"] * random.uniform(.3, .9)
        if mevcut <= hedef:
            continue
        miktar = round(mevcut - hedef, 2)
        stok[(v["id"], ana_depo)] -= miktar
        kayitlar.append((tarih_yaz(random.randint(1, 12)), "sarf", v["id"], ana_depo,
                         -miktar, None, None, random.choice(projeler), None))

    # Tarih sirasina gore yaz ki kayit numaralari da kronolojik olsun
    kayitlar.sort(key=lambda k: k[0])
    for tarih, tip, varyant_id, depo_id, miktar, fiyat, belge, proje, aciklama in kayitlar:
        db.calistir(
            """INSERT INTO hareketler (tarih, tip, varyant_id, depo_id, miktar,
                                       birim_fiyat, belge_no, proje_id, kullanici_id,
                                       aciklama, olusturma)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (tarih, tip, varyant_id, depo_id, miktar, fiyat, belge, proje,
             kullanici["id"], aciklama, db.simdi()))

    # Bir projeye birkac rezervasyon - kullanilabilir stogu asmayacak sekilde
    for v in random.sample(varyantlar, min(6, len(varyantlar))):
        mevcut = stok.get((v["id"], ana_depo), 0)
        miktar = round(mevcut * 0.25, 2)
        if miktar <= 0:
            continue
        db.calistir(
            """INSERT INTO rezervasyonlar (proje_id, varyant_id, depo_id, miktar,
                                           durum, kullanici_id, tarih)
               VALUES (?,?,?,?, 'aktif', ?, ?)""",
            (projeler[0], v["id"], ana_depo, miktar, kullanici["id"], db.simdi()))

    print(f"  ✓ {len(ORNEK_URUNLER)} ürün, {len(varyantlar)} varyant, "
          f"{len(kayitlar)} hareket, {len(ORNEK_PROJELER)} proje eklendi.")


def sifre_sifirla(kullanici_adi):
    """Sifresini unutan yoneticinin sisteme geri girebilmesi icin acil kapi.

    Uygulamanin icinden sifre sifirlamak icin zaten giris yapmis olmak gerekir;
    tek yonetici kilitli kalirsa baska cikis yolu olmazdi.
    """
    k = db.sorgu("SELECT * FROM kullanicilar WHERE kullanici_adi = ?",
                 (kullanici_adi,), tek=True)
    if k is None:
        print(f"  ✗ '{kullanici_adi}' adında bir kullanıcı yok.")
        mevcutlar = db.sorgu("SELECT kullanici_adi, rol FROM kullanicilar ORDER BY rol")
        if mevcutlar:
            print("    Kayıtlı kullanıcılar: "
                  + ", ".join(f"{m['kullanici_adi']} ({m['rol']})" for m in mevcutlar))
        return 1

    yeni = getpass.getpass(f"'{kullanici_adi}' için yeni şifre: ")
    if len(yeni) < 4:
        print("  ✗ Şifre en az 4 karakter olmalı.")
        return 1
    if yeni != getpass.getpass("Yeni şifre (tekrar): "):
        print("  ✗ Şifreler uyuşmadı.")
        return 1

    db.calistir("UPDATE kullanicilar SET sifre_hash = ?, aktif = 1 WHERE id = ?",
                (sifre_hashle(yeni), k["id"]))
    db.log_yaz(None, "sifre_sifirla", f"{kullanici_adi} şifresi komut satırından sıfırlandı")
    print(f"  ✓ '{kullanici_adi}' şifresi güncellendi ve hesap aktifleştirildi.")
    return 0


def main():
    ayristirici = argparse.ArgumentParser(description="Redecor Depo kurulumu")
    ayristirici.add_argument("--ornek-veri", action="store_true",
                             help="deneme amaçlı ürün ve hareket verisi ekler")
    ayristirici.add_argument("--sifirla", action="store_true",
                             help="mevcut veritabanını siler ve sıfırdan kurar")
    ayristirici.add_argument("--sifre-sifirla", metavar="KULLANICI",
                             help="belirtilen kullanıcının şifresini sıfırlar")
    args = ayristirici.parse_args()

    if args.sifre_sifirla:
        uygulama = uygulama_olustur()
        with uygulama.app_context():
            return sifre_sifirla(args.sifre_sifirla)

    if args.sifirla and os.path.exists(db.VERITABANI_YOLU):
        onay = input(f"DİKKAT: {db.VERITABANI_YOLU} silinecek. Emin misiniz? (evet/hayır): ")
        if onay.strip().lower() not in ("evet", "e", "yes"):
            print("Vazgeçildi.")
            return 1
        os.remove(db.VERITABANI_YOLU)
        print("  ✓ Eski veritabanı silindi.")

    uygulama = uygulama_olustur()
    with uygulama.app_context():
        print("Redecor Depo kurulumu")
        print("-" * 46)
        eklenen = temel_tanimlar()
        print(f"  ✓ {eklenen['kategori']} kategori, {eklenen['depo']} depo hazır.")

        hesap = yonetici_ac()
        if hesap:
            print(f"  ✓ Yönetici hesabı açıldı → kullanıcı: {hesap[0]}  şifre: {hesap[1]}")
            print("    ! İlk girişten sonra şifreyi mutlaka değiştirin.")
        else:
            print("  · Kullanıcı zaten tanımlı, yeni hesap açılmadı.")

        if args.ornek_veri:
            ornek_veri()

        print("-" * 46)
        print(f"Veritabanı: {db.VERITABANI_YOLU}")
        print("Başlatmak için:  ./calistir.command   (veya python app.py)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
