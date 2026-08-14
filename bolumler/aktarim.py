"""Excel/CSV'den toplu urun ve acilis stogu aktarimi.

Yeni bir depoyu sisteme gecirirken yuzlerce kalemi tek tek girmek gunler alir.
Bu ekran mevcut listeyi (Excel'den CSV olarak kaydedilmis) tek seferde alir.

Akis: dosya yukle -> onizleme ve hata raporu -> onayla -> aktar.
Hatali satirlar aktarilmaz, dogru satirlar aktarilir; hangi satirda ne oldugu
raporlanir.
"""

import csv
import io
import os
import secrets
import time

from flask import (Blueprint, Response, flash, g, redirect, render_template,
                   request, session, url_for)

import db
from auth import rol_gerekli
from bolumler.urunler import _sku_uret
from sabitler import BIRIMLER

bp = Blueprint("aktarim", __name__, url_prefix="/aktarim")

GECICI_DIZIN = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "veri", "gecici")

BASLIKLAR = ["Ürün Kodu", "Ürün Adı", "Kategori", "Tedarikçi", "Birim",
             "İkincil Birim", "Çevrim Katsayısı", "Renk/Dekor", "Ölçü",
             "Stok Kodu", "Barkod", "Min. Stok", "Birim Fiyat",
             "Açılış Stoğu", "Depo"]

ORNEK_SATIRLAR = [
    ["MDF-18", "MDF Levha 18mm", "Panel / Levha", "Anadolu Ahşap", "adet",
     "m2", "5,04", "Beyaz Lamine", "2100x2800mm", "", "", "10", "780", "45", "Ana Depo"],
    ["MDF-18", "MDF Levha 18mm", "Panel / Levha", "Anadolu Ahşap", "adet",
     "m2", "5,04", "Ceviz H1145", "2100x2800mm", "", "", "10", "790", "12", "Ana Depo"],
    ["MNT-YAVAS", "Yavaş Kapanan Menteşe", "Hırdavat", "Hırdavat Dünyası",
     "adet", "", "", "Tam Bindirmeli", "110°", "", "8690000000018", "200", "42",
     "640", "Ana Depo"],
]


# ------------------------------------------------------------------ yardimcilar
def _sayi(deger, varsayilan=None):
    """'1.234,56' ve '1234.56' bicimlerinin ikisini de okur."""
    metin = (deger or "").strip()
    if not metin:
        return varsayilan
    if "," in metin and "." in metin:
        metin = metin.replace(".", "")      # binlik ayraci
    metin = metin.replace(",", ".")
    try:
        return float(metin)
    except ValueError:
        return None


def _birim_coz(deger):
    """'m2', 'm²', 'Metrekare' gibi girdileri birim koduna cevirir."""
    metin = db.ara_norm(deger)
    if not metin:
        return None
    for kod, ad in BIRIMLER:
        if metin in (db.ara_norm(kod), db.ara_norm(ad)):
            return kod
    # 'm²' gibi yazimlar
    kisaltmalar = {"m2": "m2", "m²": "m2", "mtul": "mtul", "mt": "metre",
                   "ad": "adet", "tk": "takim", "kutu": "kutu", "kg": "kg"}
    return kisaltmalar.get(metin)


def _eski_dosyalari_temizle(saat=24):
    """Yuklenip onaylanmadan birakilmis gecici dosyalari siler."""
    if not os.path.isdir(GECICI_DIZIN):
        return
    sinir = time.time() - saat * 3600
    for ad in os.listdir(GECICI_DIZIN):
        yol = os.path.join(GECICI_DIZIN, ad)
        try:
            if os.path.isfile(yol) and os.path.getmtime(yol) < sinir:
                os.remove(yol)
        except OSError:
            pass


def _ad_ile_bul(tablo, ad):
    """Kategori/tedarikçi/depo adini buyuk-kucuk ve sapka farki gozetmeden arar."""
    if not ad:
        return None
    for satir in db.sorgu(f"SELECT id, ad FROM {tablo}"):
        if db.ara_norm(satir["ad"]) == db.ara_norm(ad):
            return satir["id"]
    return None


# --------------------------------------------------------------------- sablon
@bp.route("/sablon")
@rol_gerekli("depo")
def sablon():
    tampon = io.StringIO()
    yazici = csv.writer(tampon, delimiter=";")
    yazici.writerow(BASLIKLAR)
    yazici.writerows(ORNEK_SATIRLAR)
    return Response(
        "﻿" + tampon.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="urun_sablonu.csv"'})


# ---------------------------------------------------------------------- ekran
@bp.route("/urun", methods=("GET", "POST"))
@rol_gerekli("depo")
def urun():
    if request.method == "GET":
        return render_template("aktarim.html", asama="basla", basliklar=BASLIKLAR)

    # --------------------------------------------------- 2. asama: onay ve aktar
    if request.form.get("onayla"):
        jeton = session.get("aktarim_jeton")
        yol = os.path.join(GECICI_DIZIN, f"{jeton}.csv") if jeton else None
        if not yol or not os.path.exists(yol):
            flash("Yüklenen dosya bulunamadı, lütfen tekrar yükleyin.", "hata")
            return redirect(url_for("aktarim.urun"))
        with open(yol, "r", encoding="utf-8-sig", newline="") as f:
            satirlar, hatalar, ozet = _coz(f.read())
        sonuc = _aktar(satirlar)
        os.remove(yol)
        session.pop("aktarim_jeton", None)
        db.log_yaz(g.kullanici, "toplu_aktarim",
                   f"{sonuc['varyant']} varyant, {sonuc['urun']} ürün")
        return render_template("aktarim.html", asama="bitti", sonuc=sonuc,
                               hatalar=hatalar, basliklar=BASLIKLAR)

    # ------------------------------------------ 1. asama: dosyayi oku ve denetle
    dosya = request.files.get("dosya")
    if not dosya or not dosya.filename:
        flash("Bir CSV dosyası seçmelisiniz.", "hata")
        return redirect(url_for("aktarim.urun"))

    ham = dosya.read()
    for kodlama in ("utf-8-sig", "cp1254", "latin-1"):
        try:
            metin = ham.decode(kodlama)
            break
        except UnicodeDecodeError:
            continue
    else:
        flash("Dosyanın karakter kodlaması okunamadı. Excel'den "
              "'CSV UTF-8' olarak kaydedip tekrar deneyin.", "hata")
        return redirect(url_for("aktarim.urun"))

    satirlar, hatalar, ozet = _coz(metin)
    if not satirlar and not hatalar:
        flash("Dosyada işlenecek satır bulunamadı.", "hata")
        return redirect(url_for("aktarim.urun"))

    os.makedirs(GECICI_DIZIN, exist_ok=True)
    _eski_dosyalari_temizle()
    jeton = secrets.token_hex(8)
    with open(os.path.join(GECICI_DIZIN, f"{jeton}.csv"), "w",
              encoding="utf-8-sig", newline="") as f:
        f.write(metin)
    session["aktarim_jeton"] = jeton

    return render_template("aktarim.html", asama="onizleme", satirlar=satirlar[:200],
                           toplam=len(satirlar), hatalar=hatalar, ozet=ozet,
                           basliklar=BASLIKLAR)


# ------------------------------------------------------------------ cozumleme
def _coz(metin):
    """CSV metnini satir sozluklerine cevirir ve denetler."""
    ilk_satir = metin.split("\n", 1)[0]
    ayrac = ";" if ilk_satir.count(";") >= ilk_satir.count(",") else ","
    okuyucu = csv.reader(io.StringIO(metin), delimiter=ayrac)

    satirlar, hatalar = [], []
    ozet = {"yeni_urun": set(), "yeni_kategori": set(), "yeni_tedarikci": set(),
            "acilis_stok": 0, "mevcut_varyant": 0}
    gorulen_sku = set()

    for no, ham in enumerate(okuyucu, start=1):
        if not any((h or "").strip() for h in ham):
            continue
        if no == 1 and db.ara_norm(ham[0]).startswith("urun"):
            continue  # baslik satiri

        alan = [(h or "").strip() for h in ham] + [""] * (len(BASLIKLAR) - len(ham))
        (urun_kod, urun_ad, kategori, tedarikci, birim, ikincil, katsayi,
         renk, olcu, sku, barkod, min_stok, fiyat, acilis, depo) = alan[:15]

        # engel: satiri aktarilmaz.  uyari: aktarilir ama kullaniciya soylenir.
        engel, uyari = [], []
        if not urun_kod:
            engel.append("ürün kodu boş")
        if not urun_ad:
            engel.append("ürün adı boş")

        birim_kod = _birim_coz(birim) or "adet"
        if birim and not _birim_coz(birim):
            uyari.append(f"'{birim}' bilinmeyen birim, 'adet' varsayıldı")

        ikincil_kod = _birim_coz(ikincil) if ikincil else None
        katsayi_sayi = _sayi(katsayi)
        if ikincil_kod and not katsayi_sayi:
            uyari.append("ikincil birim var ama çevrim katsayısı yok, atlandı")
            ikincil_kod = None

        min_sayi = _sayi(min_stok, 0)
        if min_sayi is None:
            uyari.append(f"'{min_stok}' geçersiz minimum stok, 0 yazıldı")
            min_sayi = 0
        fiyat_sayi = _sayi(fiyat, 0)
        if fiyat_sayi is None:
            uyari.append(f"'{fiyat}' geçersiz birim fiyat, 0 yazıldı")
            fiyat_sayi = 0
        acilis_sayi = _sayi(acilis, 0) or 0
        if acilis_sayi < 0:
            uyari.append("açılış stoğu negatif olamaz, 0 yazıldı")
            acilis_sayi = 0

        depo_id = _ad_ile_bul("depolar", depo) if depo else None
        if acilis_sayi:
            if depo and depo_id is None:
                engel.append(f"'{depo}' adında depo tanımlı değil")
            elif depo_id is None:
                varsayilan = db.sorgu(
                    "SELECT id FROM depolar WHERE aktif=1 ORDER BY id", tek=True)
                if varsayilan is None:
                    engel.append("açılış stoğu var ama sistemde depo yok")
                else:
                    depo_id = varsayilan["id"]
                    uyari.append("depo yazılmamış, ilk depoya girildi")

        # Ayni SKU dosya icinde iki kez ya da veritabaninda zaten var mi?
        hedef_sku = sku.upper() if sku else None
        if hedef_sku:
            if hedef_sku in gorulen_sku:
                engel.append(f"'{hedef_sku}' dosyada birden fazla geçiyor")
            elif db.sorgu("SELECT 1 FROM varyantlar WHERE sku=?", (hedef_sku,), tek=True):
                engel.append(f"'{hedef_sku}' zaten kayıtlı")
                ozet["mevcut_varyant"] += 1
            gorulen_sku.add(hedef_sku)

        kayit = {
            "no": no, "urun_kod": urun_kod.upper(), "urun_ad": urun_ad,
            "kategori": kategori, "tedarikci": tedarikci, "birim": birim_kod,
            "ikincil": ikincil_kod, "katsayi": katsayi_sayi, "renk": renk or None,
            "olcu": olcu or None, "sku": hedef_sku, "barkod": barkod or None,
            "min_stok": min_sayi, "fiyat": fiyat_sayi, "acilis": acilis_sayi,
            "depo_id": depo_id, "uyarilar": uyari, "gecerli": not engel,
        }

        if kayit["gecerli"]:
            if not db.sorgu("SELECT 1 FROM urunler WHERE kod=?", (kayit["urun_kod"],),
                            tek=True):
                ozet["yeni_urun"].add(kayit["urun_kod"])
            if kategori and _ad_ile_bul("kategoriler", kategori) is None:
                ozet["yeni_kategori"].add(kategori)
            if tedarikci and _ad_ile_bul("tedarikciler", tedarikci) is None:
                ozet["yeni_tedarikci"].add(tedarikci)
            if acilis_sayi:
                ozet["acilis_stok"] += 1
            satirlar.append(kayit)
        else:
            hatalar.append({"no": no, "urun": f"{urun_kod} {renk}".strip(),
                            "mesajlar": engel})

    ozet["yeni_urun"] = len(ozet["yeni_urun"])
    ozet["yeni_kategori"] = len(ozet["yeni_kategori"])
    ozet["yeni_tedarikci"] = len(ozet["yeni_tedarikci"])
    return satirlar, hatalar, ozet


# --------------------------------------------------------------------- aktarma
def _aktar(satirlar):
    sonuc = {"urun": 0, "varyant": 0, "kategori": 0, "tedarikci": 0,
             "acilis": 0, "atlanan": 0}
    urun_onbellek = {}

    for k in satirlar:
        # Kategori / tedarikci yoksa olustur
        kategori_id = None
        if k["kategori"]:
            kategori_id = _ad_ile_bul("kategoriler", k["kategori"])
            if kategori_id is None:
                kategori_id = db.calistir(
                    "INSERT INTO kategoriler (ad) VALUES (?)", (k["kategori"],))
                sonuc["kategori"] += 1

        tedarikci_id = None
        if k["tedarikci"]:
            tedarikci_id = _ad_ile_bul("tedarikciler", k["tedarikci"])
            if tedarikci_id is None:
                tedarikci_id = db.calistir(
                    "INSERT INTO tedarikciler (ad) VALUES (?)", (k["tedarikci"],))
                sonuc["tedarikci"] += 1

        # Urun
        urun_id = urun_onbellek.get(k["urun_kod"])
        if urun_id is None:
            mevcut = db.sorgu("SELECT id FROM urunler WHERE kod=?",
                              (k["urun_kod"],), tek=True)
            if mevcut:
                urun_id = mevcut["id"]
            else:
                urun_id = db.calistir(
                    """INSERT INTO urunler (kod, ad, kategori_id, tedarikci_id,
                                            ana_birim, ikincil_birim, birim_katsayi)
                       VALUES (?,?,?,?,?,?,?)""",
                    (k["urun_kod"], k["urun_ad"], kategori_id, tedarikci_id,
                     k["birim"], k["ikincil"], k["katsayi"]))
                sonuc["urun"] += 1
            urun_onbellek[k["urun_kod"]] = urun_id

        # Varyant
        sku = k["sku"] or _sku_uret(k["urun_kod"], k["renk"] or "", k["olcu"] or "")
        if db.sorgu("SELECT 1 FROM varyantlar WHERE sku=?", (sku,), tek=True):
            sonuc["atlanan"] += 1
            continue
        varyant_id = db.calistir(
            """INSERT INTO varyantlar (urun_id, sku, renk_dekor, olcu, barkod,
                                       min_stok, birim_fiyat)
               VALUES (?,?,?,?,?,?,?)""",
            (urun_id, sku, k["renk"], k["olcu"], k["barkod"], k["min_stok"],
             k["fiyat"]))
        sonuc["varyant"] += 1

        # Acilis stogu bir mal girisi hareketi olarak yazilir ki
        # stok yine hareketlerden hesaplanabilsin.
        if k["acilis"] and k["depo_id"]:
            db.calistir(
                """INSERT INTO hareketler (tarih, tip, varyant_id, depo_id, miktar,
                                           birim_fiyat, kullanici_id, aciklama, olusturma)
                   VALUES (?,'giris',?,?,?,?,?,?,?)""",
                (db.bugun(), varyant_id, k["depo_id"], k["acilis"], k["fiyat"],
                 g.kullanici["id"], "toplu aktarım açılış stoğu", db.simdi()))
            sonuc["acilis"] += 1

    return sonuc
