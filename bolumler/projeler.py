"""Proje / is emri takibi ve malzeme rezervasyonu.

Rezervasyon = mal fiziken depoda duruyor ama baska bir ise ayrilmis.
Bu yuzden iki ayri rakam tutulur:
    fiziksel stok  : depoda gercekten olan
    kullanilabilir : fiziksel - rezerve  (yeni is icin verilebilecek olan)
"""

import sqlite3

from flask import (Blueprint, abort, flash, g, redirect, render_template,
                   request, url_for)

import db
from auth import giris_gerekli, rol_gerekli
from bolumler.hareketler import hareket_ekle, stok_yeterli_mi
from sabitler import PROJE_DURUMLARI, PROJE_TIPLERI

bp = Blueprint("projeler", __name__, url_prefix="/projeler")


@bp.route("/")
@giris_gerekli
def liste():
    durum = request.args.get("durum") or ""
    arama = (request.args.get("q") or "").strip()

    kosullar, params = ["1=1"], []
    if durum:
        kosullar.append("p.durum = ?")
        params.append(durum)
    else:
        kosullar.append("p.durum IN ('acik','uretimde')")
    if arama:
        sutunlar = ["p.kod", "p.musteri", "p.adres"]
        kosullar.append(db.arama_kosulu(sutunlar))
        params.extend([f"%{arama}%"] * len(sutunlar))

    projeler = db.sorgu(
        f"""SELECT p.*,
                   (SELECT COUNT(*) FROM rezervasyonlar r
                     WHERE r.proje_id = p.id AND r.durum='aktif') AS rezerv_sayisi,
                   (SELECT COUNT(*) FROM hareketler h
                     WHERE h.proje_id = p.id) AS hareket_sayisi,
                   (SELECT COALESCE(SUM(ABS(h.miktar) * IFNULL(v.birim_fiyat,0)), 0)
                      FROM hareketler h JOIN varyantlar v ON v.id = h.varyant_id
                     WHERE h.proje_id = p.id AND h.miktar < 0) AS malzeme_tutari
            FROM projeler p
            WHERE {' AND '.join(kosullar)}
            ORDER BY IFNULL(p.teslim,'9999-99-99'), p.kod""", tuple(params))

    return render_template("proje_liste.html", projeler=projeler, durum=durum,
                           arama=arama, durumlar=PROJE_DURUMLARI)


@bp.route("/<int:proje_id>")
@giris_gerekli
def detay(proje_id):
    proje = db.sorgu("SELECT * FROM projeler WHERE id = ?", (proje_id,), tek=True)
    if proje is None:
        abort(404)

    rezervasyonlar = db.sorgu(
        """SELECT r.*, vv.urun_ad, vv.sku, vv.renk_dekor, vv.olcu, vv.ana_birim,
                  vv.birim_fiyat, d.ad AS depo_ad,
                  COALESCE((SELECT miktar FROM v_stok s
                             WHERE s.varyant_id = r.varyant_id
                               AND s.depo_id = r.depo_id), 0) AS depo_stok
           FROM rezervasyonlar r
           JOIN v_varyant vv ON vv.varyant_id = r.varyant_id
           JOIN depolar   d  ON d.id = r.depo_id
           WHERE r.proje_id = ?
           ORDER BY r.durum = 'aktif' DESC, r.id DESC""", (proje_id,))

    hareketler = db.sorgu(
        """SELECT h.*, vv.urun_ad, vv.sku, vv.renk_dekor, vv.ana_birim,
                  d.ad AS depo_ad, k.ad_soyad AS kullanici_ad,
                  IFNULL(h.birim_fiyat, vv.birim_fiyat) AS efektif_fiyat
           FROM hareketler h
           JOIN v_varyant vv ON vv.varyant_id = h.varyant_id
           JOIN depolar d    ON d.id = h.depo_id
           LEFT JOIN kullanicilar k ON k.id = h.kullanici_id
           WHERE h.proje_id = ?
           ORDER BY h.tarih DESC, h.id DESC""", (proje_id,))

    tuketim_tutari = sum(abs(h["miktar"]) * (h["efektif_fiyat"] or 0)
                         for h in hareketler if h["miktar"] < 0)
    rezerve_tutari = sum(r["miktar"] * (r["birim_fiyat"] or 0)
                         for r in rezervasyonlar if r["durum"] == "aktif")

    return render_template(
        "proje_detay.html", proje=proje, rezervasyonlar=rezervasyonlar,
        hareketler=hareketler, depolar=db.depo_listesi(),
        tuketim_tutari=tuketim_tutari, rezerve_tutari=rezerve_tutari,
        durumlar=PROJE_DURUMLARI)


@bp.route("/yeni", methods=("GET", "POST"))
@giris_gerekli
def yeni():
    if request.method == "POST":
        hata = _kaydet(None)
        if hata is None:
            return redirect(url_for("projeler.detay", proje_id=g.son_proje_id))
        flash(hata, "hata")
    return render_template("proje_form.html", proje=None, tipler=PROJE_TIPLERI,
                           durumlar=PROJE_DURUMLARI, onerilen_kod=_kod_oner())


@bp.route("/<int:proje_id>/duzenle", methods=("GET", "POST"))
@giris_gerekli
def duzenle(proje_id):
    proje = db.sorgu("SELECT * FROM projeler WHERE id = ?", (proje_id,), tek=True)
    if proje is None:
        abort(404)
    if request.method == "POST":
        hata = _kaydet(proje_id)
        if hata is None:
            flash("Proje güncellendi.", "basari")
            return redirect(url_for("projeler.detay", proje_id=proje_id))
        flash(hata, "hata")
    return render_template("proje_form.html", proje=proje, tipler=PROJE_TIPLERI,
                           durumlar=PROJE_DURUMLARI, onerilen_kod=proje["kod"])


def _kod_oner() -> str:
    from datetime import datetime
    yil = datetime.now().strftime("%Y")
    son = db.tek_deger(
        "SELECT COUNT(*) FROM projeler WHERE kod LIKE ?", (f"{yil}-%",), 0)
    return f"{yil}-{son + 1:03d}"


def _kaydet(proje_id):
    f = request.form
    kod = (f.get("kod") or "").strip().upper()
    musteri = (f.get("musteri") or "").strip()
    if not kod:
        return "Proje kodu zorunlu."
    if not musteri:
        return "Müşteri adı zorunlu."

    veri = (kod, musteri,
            (f.get("telefon") or "").strip() or None,
            (f.get("adres") or "").strip() or None,
            f.get("tip") or None,
            f.get("durum") or "acik",
            f.get("baslangic") or None,
            f.get("teslim") or None,
            (f.get("notlar") or "").strip() or None)
    try:
        if proje_id is None:
            g.son_proje_id = db.calistir(
                """INSERT INTO projeler
                   (kod, musteri, telefon, adres, tip, durum, baslangic, teslim, notlar)
                   VALUES (?,?,?,?,?,?,?,?,?)""", veri)
            db.log_yaz(g.kullanici, "proje_ekle", f"{kod} - {musteri}")
        else:
            db.calistir(
                """UPDATE projeler SET kod=?, musteri=?, telefon=?, adres=?, tip=?,
                          durum=?, baslangic=?, teslim=?, notlar=? WHERE id=?""",
                veri + (proje_id,))
            db.log_yaz(g.kullanici, "proje_guncelle", f"{kod} - {musteri}")
    except sqlite3.IntegrityError:
        return f"'{kod}' proje kodu zaten kullanılıyor."
    return None


# ------------------------------------------------------------- rezervasyonlar
@bp.route("/<int:proje_id>/rezerve", methods=("POST",))
@rol_gerekli("depo")
def rezerve_et(proje_id):
    proje = db.sorgu("SELECT * FROM projeler WHERE id = ?", (proje_id,), tek=True)
    if proje is None:
        abort(404)

    f = request.form
    varyant_id = f.get("varyant_id", type=int)
    depo_id = f.get("depo_id", type=int)
    try:
        miktar = float((f.get("miktar") or "0").replace(",", "."))
    except ValueError:
        miktar = 0

    if not varyant_id or not depo_id or miktar <= 0:
        flash("Ürün, depo ve sıfırdan büyük miktar girmelisiniz.", "hata")
        return redirect(url_for("projeler.detay", proje_id=proje_id))

    stok = db.varyant_stok(varyant_id, depo_id)
    rezerve = db.varyant_rezerve(varyant_id, depo_id)
    v = db.varyant_detay(varyant_id)
    if miktar > stok - rezerve:
        flash(f"{v['urun_ad']} ({v['sku']}): kullanılabilir stok "
              f"{stok - rezerve:g} {v['ana_birim']}, bu kadar rezerve edilemez.", "hata")
        return redirect(url_for("projeler.detay", proje_id=proje_id))

    db.calistir(
        """INSERT INTO rezervasyonlar
           (proje_id, varyant_id, depo_id, miktar, durum, kullanici_id, tarih, aciklama)
           VALUES (?,?,?,?,'aktif',?,?,?)""",
        (proje_id, varyant_id, depo_id, miktar, g.kullanici["id"], db.simdi(),
         (f.get("aciklama") or "").strip() or None))
    db.log_yaz(g.kullanici, "rezerve",
               f"{proje['kod']} icin {miktar:g} {v['ana_birim']} {v['sku']}")
    flash("Malzeme projeye rezerve edildi.", "basari")
    return redirect(url_for("projeler.detay", proje_id=proje_id))


@bp.route("/rezervasyon/<int:rez_id>/iptal", methods=("POST",))
@rol_gerekli("depo")
def rezerve_iptal(rez_id):
    r = db.sorgu("SELECT * FROM rezervasyonlar WHERE id = ?", (rez_id,), tek=True)
    if r is None:
        abort(404)
    db.calistir("UPDATE rezervasyonlar SET durum = 'iptal' WHERE id = ?", (rez_id,))
    db.log_yaz(g.kullanici, "rezerve_iptal", f"#{rez_id}")
    flash("Rezervasyon iptal edildi, malzeme tekrar kullanılabilir.", "basari")
    return redirect(url_for("projeler.detay", proje_id=r["proje_id"]))


@bp.route("/rezervasyon/<int:rez_id>/cikis", methods=("POST",))
@rol_gerekli("depo")
def rezerve_cikis(rez_id):
    """Rezerve malzemeyi fiilen depodan cikarir (sarf veya sevkiyat).

    Sahada malzeme cogu zaman tek seferde degil parca parca alinir. Bu yuzden
    miktar bos birakilirsa tamami, sayi girilirse o kadari cikar ve
    rezervasyonda kalan miktar bekler.
    """
    r = db.sorgu("SELECT * FROM rezervasyonlar WHERE id = ?", (rez_id,), tek=True)
    if r is None:
        abort(404)
    if r["durum"] != "aktif":
        flash("Bu rezervasyon zaten kapanmış.", "hata")
        return redirect(url_for("projeler.detay", proje_id=r["proje_id"]))

    tip = request.form.get("tip", "sarf")
    if tip not in ("sarf", "sevk"):
        tip = "sarf"

    ham_miktar = (request.form.get("miktar") or "").strip().replace(",", ".")
    if ham_miktar:
        try:
            miktar = float(ham_miktar)
        except ValueError:
            flash("Geçersiz miktar girdiniz.", "hata")
            return redirect(url_for("projeler.detay", proje_id=r["proje_id"]))
        if miktar <= 0:
            flash("Miktar sıfırdan büyük olmalı.", "hata")
            return redirect(url_for("projeler.detay", proje_id=r["proje_id"]))
        if miktar > r["miktar"] + 0.0001:
            flash(f"Rezervasyonda {r['miktar']:g} var, daha fazlası çıkarılamaz.", "hata")
            return redirect(url_for("projeler.detay", proje_id=r["proje_id"]))
    else:
        miktar = r["miktar"]

    yeterli, mevcut = stok_yeterli_mi(r["varyant_id"], r["depo_id"], miktar)
    if not yeterli:
        flash(f"Depoda yeterli stok yok (mevcut: {mevcut:g}).", "hata")
        return redirect(url_for("projeler.detay", proje_id=r["proje_id"]))

    proje = db.sorgu("SELECT * FROM projeler WHERE id = ?", (r["proje_id"],), tek=True)
    hareket_ekle(tip, r["varyant_id"], r["depo_id"], miktar, g.kullanici,
                 proje_id=r["proje_id"],
                 aciklama=f"{proje['kod']} rezervasyonundan çıkış")

    kalan = round(r["miktar"] - miktar, 4)
    if kalan > 0.0001:
        db.calistir("UPDATE rezervasyonlar SET miktar = ? WHERE id = ?", (kalan, rez_id))
        flash(f"{miktar:g} çıkış yapıldı, rezervasyonda {kalan:g} bekliyor.", "basari")
    else:
        db.calistir("UPDATE rezervasyonlar SET durum = 'kullanildi' WHERE id = ?",
                    (rez_id,))
        flash("Malzeme çıkışı yapıldı ve rezervasyon kapatıldı.", "basari")

    db.log_yaz(g.kullanici, "rezerve_cikis", f"#{rez_id} -> {tip}, {miktar:g}")
    return redirect(url_for("projeler.detay", proje_id=r["proje_id"]))


@bp.route("/<int:proje_id>/durum", methods=("POST",))
@giris_gerekli
def durum_degistir(proje_id):
    yeni_durum = request.form.get("durum")
    if yeni_durum not in dict(PROJE_DURUMLARI):
        abort(400)
    db.calistir("UPDATE projeler SET durum = ? WHERE id = ?", (yeni_durum, proje_id))

    # Proje kapandiysa bekleyen rezervasyonlari serbest birak
    if yeni_durum in ("tamamlandi", "iptal"):
        adet = db.tek_deger(
            "SELECT COUNT(*) FROM rezervasyonlar WHERE proje_id=? AND durum='aktif'",
            (proje_id,), 0)
        if adet:
            db.calistir(
                "UPDATE rezervasyonlar SET durum='iptal'"
                " WHERE proje_id=? AND durum='aktif'", (proje_id,))
            flash(f"{adet} bekleyen rezervasyon serbest bırakıldı.", "bilgi")

    db.log_yaz(g.kullanici, "proje_durum", f"#{proje_id} -> {yeni_durum}")
    flash("Proje durumu güncellendi.", "basari")
    return redirect(url_for("projeler.detay", proje_id=proje_id))
