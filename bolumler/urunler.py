"""Urun ve varyant tanimlari.

Bu sektorde ayni urun onlarca renk/dekor varyantiyla durur (ayni profil 4 renk,
ayni kapak 40 dekor). Bu yuzden stok urun degil, VARYANT seviyesinde tutulur.
"""

import re
import sqlite3

from flask import (Blueprint, abort, flash, g, redirect, render_template,
                   request, url_for)

import db
from auth import giris_gerekli, rol_gerekli

bp = Blueprint("urunler", __name__, url_prefix="/urunler")


def _slug(metin: str) -> str:
    donusum = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    metin = (metin or "").translate(donusum)
    metin = re.sub(r"[^A-Za-z0-9]+", "-", metin).strip("-").upper()
    return metin[:20]


def _sku_uret(urun_kod: str, renk: str, olcu: str) -> str:
    parcalar = [urun_kod.upper()]
    if renk:
        parcalar.append(_slug(renk))
    if olcu:
        parcalar.append(_slug(olcu))
    taban = "-".join(p for p in parcalar if p) or urun_kod.upper()
    aday, sayac = taban, 1
    while db.sorgu("SELECT 1 FROM varyantlar WHERE sku = ?", (aday,), tek=True):
        sayac += 1
        aday = f"{taban}-{sayac}"
    return aday


@bp.route("/")
@giris_gerekli
def liste():
    arama = (request.args.get("q") or "").strip()
    kategori_id = request.args.get("kategori", type=int)
    pasif = request.args.get("pasif") == "1"

    kosullar = [] if pasif else ["u.aktif = 1"]
    params = []
    if arama:
        sutunlar = ["u.ad", "u.kod"]
        kosullar.append(db.arama_kosulu(sutunlar))
        params.extend([f"%{arama}%"] * len(sutunlar))
    if kategori_id:
        kosullar.append("u.kategori_id = ?")
        params.append(kategori_id)
    nerede = (" WHERE " + " AND ".join(kosullar)) if kosullar else ""

    urunler = db.sorgu(
        f"""SELECT u.*, k.ad AS kategori_ad, t.ad AS tedarikci_ad,
                   (SELECT COUNT(*) FROM varyantlar v
                     WHERE v.urun_id = u.id AND v.aktif = 1) AS varyant_sayisi,
                   (SELECT COALESCE(SUM(s.miktar),0) FROM v_stok s
                     JOIN varyantlar v2 ON v2.id = s.varyant_id
                     WHERE v2.urun_id = u.id) AS toplam_stok
            FROM urunler u
            LEFT JOIN kategoriler  k ON k.id = u.kategori_id
            LEFT JOIN tedarikciler t ON t.id = u.tedarikci_id
            {nerede}
            ORDER BY u.ad""", tuple(params))

    return render_template("urun_liste.html", urunler=urunler,
                           kategoriler=db.kategori_listesi(), arama=arama,
                           secili_kategori=kategori_id, pasif=pasif)


@bp.route("/<int:urun_id>")
@giris_gerekli
def detay(urun_id):
    urun = db.sorgu(
        """SELECT u.*, k.ad AS kategori_ad, t.ad AS tedarikci_ad, t.teslim_gun
           FROM urunler u
           LEFT JOIN kategoriler  k ON k.id = u.kategori_id
           LEFT JOIN tedarikciler t ON t.id = u.tedarikci_id
           WHERE u.id = ?""", (urun_id,), tek=True)
    if urun is None:
        abort(404)

    varyantlar = db.sorgu(
        """SELECT v.*,
                  COALESCE((SELECT SUM(miktar) FROM v_stok s
                             WHERE s.varyant_id = v.id), 0) AS stok,
                  COALESCE((SELECT SUM(miktar) FROM v_rezerve r
                             WHERE r.varyant_id = v.id), 0) AS rezerve
           FROM varyantlar v WHERE v.urun_id = ?
           ORDER BY v.aktif DESC, v.renk_dekor, v.olcu""", (urun_id,))

    return render_template("urun_detay.html", urun=urun, varyantlar=varyantlar)


@bp.route("/yeni", methods=("GET", "POST"))
@rol_gerekli("depo")
def yeni():
    if request.method == "POST":
        hata = _urun_kaydet(None)
        if hata is None:
            return redirect(url_for("urunler.detay", urun_id=g.son_urun_id))
        flash(hata, "hata")

    return render_template("urun_form.html", urun=None,
                           kategoriler=db.kategori_listesi(),
                           tedarikciler=db.tedarikci_listesi())


@bp.route("/<int:urun_id>/duzenle", methods=("GET", "POST"))
@rol_gerekli("depo")
def duzenle(urun_id):
    urun = db.sorgu("SELECT * FROM urunler WHERE id = ?", (urun_id,), tek=True)
    if urun is None:
        abort(404)

    if request.method == "POST":
        hata = _urun_kaydet(urun_id)
        if hata is None:
            flash("Ürün güncellendi.", "basari")
            return redirect(url_for("urunler.detay", urun_id=urun_id))
        flash(hata, "hata")

    return render_template("urun_form.html", urun=urun,
                           kategoriler=db.kategori_listesi(),
                           tedarikciler=db.tedarikci_listesi())


def _urun_kaydet(urun_id):
    f = request.form
    kod = (f.get("kod") or "").strip().upper()
    ad = (f.get("ad") or "").strip()
    if not kod:
        return "Ürün kodu zorunlu."
    if not ad:
        return "Ürün adı zorunlu."

    katsayi = f.get("birim_katsayi", type=float)
    ikincil = (f.get("ikincil_birim") or "").strip() or None
    if ikincil and not katsayi:
        return "İkincil birim seçtiyseniz çevrim katsayısı da girmelisiniz."

    veri = (
        kod, ad,
        f.get("kategori_id", type=int) or None,
        f.get("tedarikci_id", type=int) or None,
        f.get("ana_birim") or "adet",
        ikincil, katsayi,
        (f.get("aciklama") or "").strip() or None,
        1 if f.get("aktif") else 0,
    )

    try:
        if urun_id is None:
            g.son_urun_id = db.calistir(
                """INSERT INTO urunler
                   (kod, ad, kategori_id, tedarikci_id, ana_birim,
                    ikincil_birim, birim_katsayi, aciklama, aktif)
                   VALUES (?,?,?,?,?,?,?,?,?)""", veri)
            db.log_yaz(g.kullanici, "urun_ekle", f"{kod} - {ad}")
        else:
            db.calistir(
                """UPDATE urunler SET kod=?, ad=?, kategori_id=?, tedarikci_id=?,
                          ana_birim=?, ikincil_birim=?, birim_katsayi=?,
                          aciklama=?, aktif=?
                   WHERE id=?""", veri + (urun_id,))
            db.log_yaz(g.kullanici, "urun_guncelle", f"{kod} - {ad}")
    except sqlite3.IntegrityError:
        return f"'{kod}' kodu başka bir üründe kullanılıyor."
    return None


# ------------------------------------------------------------------ varyantlar
@bp.route("/<int:urun_id>/varyant/yeni", methods=("GET", "POST"))
@rol_gerekli("depo")
def varyant_yeni(urun_id):
    urun = db.sorgu("SELECT * FROM urunler WHERE id = ?", (urun_id,), tek=True)
    if urun is None:
        abort(404)

    if request.method == "POST":
        hata = _varyant_kaydet(urun, None)
        if hata is None:
            flash("Varyant eklendi.", "basari")
            if request.form.get("devam"):
                return redirect(url_for("urunler.varyant_yeni", urun_id=urun_id))
            return redirect(url_for("urunler.detay", urun_id=urun_id))
        flash(hata, "hata")

    return render_template("varyant_form.html", urun=urun, varyant=None)


@bp.route("/varyant/<int:varyant_id>/duzenle", methods=("GET", "POST"))
@rol_gerekli("depo")
def varyant_duzenle(varyant_id):
    varyant = db.sorgu("SELECT * FROM varyantlar WHERE id = ?", (varyant_id,), tek=True)
    if varyant is None:
        abort(404)
    urun = db.sorgu("SELECT * FROM urunler WHERE id = ?",
                    (varyant["urun_id"],), tek=True)

    if request.method == "POST":
        hata = _varyant_kaydet(urun, varyant_id)
        if hata is None:
            flash("Varyant güncellendi.", "basari")
            return redirect(url_for("urunler.detay", urun_id=urun["id"]))
        flash(hata, "hata")

    return render_template("varyant_form.html", urun=urun, varyant=varyant)


def _varyant_kaydet(urun, varyant_id):
    f = request.form
    renk = (f.get("renk_dekor") or "").strip() or None
    olcu = (f.get("olcu") or "").strip() or None
    sku = (f.get("sku") or "").strip().upper()
    if not sku:
        sku = _sku_uret(urun["kod"], renk or "", olcu or "")

    veri = (
        sku, renk, olcu,
        (f.get("barkod") or "").strip() or None,
        f.get("min_stok", type=float) or 0,
        f.get("birim_fiyat", type=float) or 0,
        1 if f.get("aktif") else 0,
    )

    try:
        if varyant_id is None:
            db.calistir(
                """INSERT INTO varyantlar
                   (urun_id, sku, renk_dekor, olcu, barkod, min_stok,
                    birim_fiyat, aktif)
                   VALUES (?,?,?,?,?,?,?,?)""", (urun["id"],) + veri)
            db.log_yaz(g.kullanici, "varyant_ekle", f"{sku} ({urun['ad']})")
        else:
            db.calistir(
                """UPDATE varyantlar SET sku=?, renk_dekor=?, olcu=?, barkod=?,
                          min_stok=?, birim_fiyat=?, aktif=?
                   WHERE id=?""", veri + (varyant_id,))
            db.log_yaz(g.kullanici, "varyant_guncelle", sku)
    except sqlite3.IntegrityError:
        return f"'{sku}' stok kodu zaten kullanılıyor."
    return None


@bp.route("/varyant/<int:varyant_id>/durum", methods=("POST",))
@rol_gerekli("depo")
def varyant_durum(varyant_id):
    """Varyanti pasife alir / geri acar. Hareket gecmisi korunur, silinmez."""
    varyant = db.sorgu("SELECT * FROM varyantlar WHERE id = ?", (varyant_id,), tek=True)
    if varyant is None:
        abort(404)
    yeni_durum = 0 if varyant["aktif"] else 1
    db.calistir("UPDATE varyantlar SET aktif = ? WHERE id = ?", (yeni_durum, varyant_id))
    db.log_yaz(g.kullanici, "varyant_durum",
               f"{varyant['sku']} -> {'aktif' if yeni_durum else 'pasif'}")
    flash("Varyant " + ("aktifleştirildi." if yeni_durum else "pasife alındı."), "basari")
    return redirect(url_for("urunler.detay", urun_id=varyant["urun_id"]))
