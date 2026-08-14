"""Tanim ekranlari: depolar, kategoriler, tedarikciler, kullanicilar, islem gecmisi."""

import io
import os
import sqlite3
import tempfile

from flask import (Blueprint, abort, current_app, flash, g, redirect,
                   render_template, request, send_file, url_for)
from guvenlik import sifre_hashle

import db
from auth import rol_gerekli
from sabitler import ROLLER

bp = Blueprint("tanimlar", __name__, url_prefix="/tanimlar")


# ---------------------------------------------------------------------- depolar
@bp.route("/depolar", methods=("GET", "POST"))
@rol_gerekli("depo")
def depolar():
    if request.method == "POST":
        ad = (request.form.get("ad") or "").strip()
        depo_id = request.form.get("id", type=int)
        if not ad:
            flash("Depo adı zorunlu.", "hata")
        else:
            veri = (ad, (request.form.get("adres") or "").strip() or None,
                    (request.form.get("aciklama") or "").strip() or None,
                    1 if request.form.get("aktif") else 0)
            try:
                if depo_id:
                    db.calistir("UPDATE depolar SET ad=?, adres=?, aciklama=?, aktif=?"
                                " WHERE id=?", veri + (depo_id,))
                    flash("Depo güncellendi.", "basari")
                else:
                    db.calistir("INSERT INTO depolar (ad, adres, aciklama, aktif)"
                                " VALUES (?,?,?,?)", veri)
                    flash("Depo eklendi.", "basari")
                db.log_yaz(g.kullanici, "depo_kaydet", ad)
            except sqlite3.IntegrityError:
                flash(f"'{ad}' adında bir depo zaten var.", "hata")
        return redirect(url_for("tanimlar.depolar"))

    satirlar = db.sorgu(
        """SELECT d.*,
                  (SELECT COUNT(*) FROM hareketler h WHERE h.depo_id = d.id) AS hareket,
                  (SELECT COALESCE(SUM(s.miktar * v.birim_fiyat),0) FROM v_stok s
                    JOIN varyantlar v ON v.id = s.varyant_id
                   WHERE s.depo_id = d.id) AS deger
           FROM depolar d ORDER BY d.ad""")
    duzenle = None
    if request.args.get("duzenle", type=int):
        duzenle = db.sorgu("SELECT * FROM depolar WHERE id=?",
                           (request.args.get("duzenle", type=int),), tek=True)
    return render_template("tanim_depolar.html", satirlar=satirlar, duzenle=duzenle)


# ------------------------------------------------------------------ kategoriler
@bp.route("/kategoriler", methods=("GET", "POST"))
@rol_gerekli("depo")
def kategoriler():
    if request.method == "POST":
        ad = (request.form.get("ad") or "").strip()
        kid = request.form.get("id", type=int)
        if not ad:
            flash("Kategori adı zorunlu.", "hata")
        else:
            aciklama = (request.form.get("aciklama") or "").strip() or None
            try:
                if kid:
                    db.calistir("UPDATE kategoriler SET ad=?, aciklama=? WHERE id=?",
                                (ad, aciklama, kid))
                    flash("Kategori güncellendi.", "basari")
                else:
                    db.calistir("INSERT INTO kategoriler (ad, aciklama) VALUES (?,?)",
                                (ad, aciklama))
                    flash("Kategori eklendi.", "basari")
            except sqlite3.IntegrityError:
                flash(f"'{ad}' kategorisi zaten var.", "hata")
        return redirect(url_for("tanimlar.kategoriler"))

    satirlar = db.sorgu(
        """SELECT k.*, (SELECT COUNT(*) FROM urunler u
                         WHERE u.kategori_id = k.id AND u.aktif=1) AS urun_sayisi
           FROM kategoriler k ORDER BY k.ad""")
    duzenle = None
    if request.args.get("duzenle", type=int):
        duzenle = db.sorgu("SELECT * FROM kategoriler WHERE id=?",
                           (request.args.get("duzenle", type=int),), tek=True)
    return render_template("tanim_kategoriler.html", satirlar=satirlar, duzenle=duzenle)


@bp.route("/kategoriler/<int:kid>/sil", methods=("POST",))
@rol_gerekli("yonetici")
def kategori_sil(kid):
    adet = db.tek_deger("SELECT COUNT(*) FROM urunler WHERE kategori_id=?", (kid,), 0)
    if adet:
        flash(f"Bu kategoride {adet} ürün var, önce onları taşıyın.", "hata")
    else:
        db.calistir("DELETE FROM kategoriler WHERE id=?", (kid,))
        flash("Kategori silindi.", "basari")
    return redirect(url_for("tanimlar.kategoriler"))


# ----------------------------------------------------------------- tedarikciler
@bp.route("/tedarikciler", methods=("GET", "POST"))
@rol_gerekli("depo")
def tedarikciler():
    if request.method == "POST":
        ad = (request.form.get("ad") or "").strip()
        tid = request.form.get("id", type=int)
        if not ad:
            flash("Tedarikçi adı zorunlu.", "hata")
        else:
            veri = (ad,
                    (request.form.get("yetkili") or "").strip() or None,
                    (request.form.get("telefon") or "").strip() or None,
                    (request.form.get("eposta") or "").strip() or None,
                    (request.form.get("adres") or "").strip() or None,
                    request.form.get("teslim_gun", type=int) or 7,
                    (request.form.get("notlar") or "").strip() or None,
                    1 if request.form.get("aktif") else 0)
            if tid:
                db.calistir(
                    """UPDATE tedarikciler SET ad=?, yetkili=?, telefon=?, eposta=?,
                              adres=?, teslim_gun=?, notlar=?, aktif=? WHERE id=?""",
                    veri + (tid,))
                flash("Tedarikçi güncellendi.", "basari")
            else:
                db.calistir(
                    """INSERT INTO tedarikciler
                       (ad, yetkili, telefon, eposta, adres, teslim_gun, notlar, aktif)
                       VALUES (?,?,?,?,?,?,?,?)""", veri)
                flash("Tedarikçi eklendi.", "basari")
            db.log_yaz(g.kullanici, "tedarikci_kaydet", ad)
        return redirect(url_for("tanimlar.tedarikciler"))

    satirlar = db.sorgu(
        """SELECT t.*, (SELECT COUNT(*) FROM urunler u
                         WHERE u.tedarikci_id = t.id AND u.aktif=1) AS urun_sayisi
           FROM tedarikciler t ORDER BY t.aktif DESC, t.ad""")
    duzenle = None
    if request.args.get("duzenle", type=int):
        duzenle = db.sorgu("SELECT * FROM tedarikciler WHERE id=?",
                           (request.args.get("duzenle", type=int),), tek=True)
    return render_template("tanim_tedarikciler.html", satirlar=satirlar,
                           duzenle=duzenle)


# ----------------------------------------------------------------- kullanicilar
@bp.route("/kullanicilar", methods=("GET", "POST"))
@rol_gerekli("yonetici")
def kullanicilar():
    if request.method == "POST":
        kid = request.form.get("id", type=int)
        kullanici_adi = (request.form.get("kullanici_adi") or "").strip().lower()
        ad_soyad = (request.form.get("ad_soyad") or "").strip()
        rol = request.form.get("rol") or "usta"
        sifre = request.form.get("sifre") or ""
        aktif = 1 if request.form.get("aktif") else 0

        if not kullanici_adi or not ad_soyad:
            flash("Kullanıcı adı ve ad soyad zorunlu.", "hata")
        elif rol not in ROLLER:
            flash("Geçersiz rol.", "hata")
        elif not kid and len(sifre) < 4:
            flash("Yeni kullanıcı için en az 4 karakterlik şifre girin.", "hata")
        else:
            try:
                if kid:
                    db.calistir(
                        "UPDATE kullanicilar SET kullanici_adi=?, ad_soyad=?, rol=?,"
                        " aktif=? WHERE id=?",
                        (kullanici_adi, ad_soyad, rol, aktif, kid))
                    if sifre:
                        if len(sifre) < 4:
                            flash("Şifre en az 4 karakter olmalı, şifre değiştirilmedi.",
                                  "hata")
                        else:
                            db.calistir("UPDATE kullanicilar SET sifre_hash=? WHERE id=?",
                                        (sifre_hashle(sifre), kid))
                    flash("Kullanıcı güncellendi.", "basari")
                else:
                    db.calistir(
                        """INSERT INTO kullanicilar
                           (kullanici_adi, ad_soyad, sifre_hash, rol, aktif)
                           VALUES (?,?,?,?,?)""",
                        (kullanici_adi, ad_soyad, sifre_hashle(sifre),
                         rol, aktif))
                    flash("Kullanıcı eklendi.", "basari")
                db.log_yaz(g.kullanici, "kullanici_kaydet", f"{kullanici_adi} ({rol})")
            except sqlite3.IntegrityError:
                flash(f"'{kullanici_adi}' kullanıcı adı zaten alınmış.", "hata")
        return redirect(url_for("tanimlar.kullanicilar"))

    satirlar = db.sorgu(
        """SELECT k.*, (SELECT COUNT(*) FROM hareketler h
                         WHERE h.kullanici_id = k.id) AS hareket_sayisi
           FROM kullanicilar k ORDER BY k.aktif DESC, k.ad_soyad""")
    duzenle = None
    if request.args.get("duzenle", type=int):
        duzenle = db.sorgu("SELECT * FROM kullanicilar WHERE id=?",
                           (request.args.get("duzenle", type=int),), tek=True)
    return render_template("tanim_kullanicilar.html", satirlar=satirlar,
                           duzenle=duzenle, roller=ROLLER)


@bp.route("/kullanicilar/<int:kid>/durum", methods=("POST",))
@rol_gerekli("yonetici")
def kullanici_durum(kid):
    if kid == g.kullanici["id"]:
        flash("Kendi hesabınızı pasife alamazsınız.", "hata")
        return redirect(url_for("tanimlar.kullanicilar"))
    k = db.sorgu("SELECT * FROM kullanicilar WHERE id=?", (kid,), tek=True)
    if k is None:
        abort(404)
    yeni = 0 if k["aktif"] else 1
    if not yeni and k["rol"] == "yonetici":
        kalan = db.tek_deger(
            "SELECT COUNT(*) FROM kullanicilar WHERE rol='yonetici' AND aktif=1", (), 0)
        if kalan <= 1:
            flash("Sistemde en az bir aktif yönetici kalmalı.", "hata")
            return redirect(url_for("tanimlar.kullanicilar"))
    db.calistir("UPDATE kullanicilar SET aktif=? WHERE id=?", (yeni, kid))
    db.log_yaz(g.kullanici, "kullanici_durum",
               f"{k['kullanici_adi']} -> {'aktif' if yeni else 'pasif'}")
    flash("Kullanıcı durumu güncellendi.", "basari")
    return redirect(url_for("tanimlar.kullanicilar"))


# ------------------------------------------------------------------- yedekleme
@bp.route("/yedek")
@rol_gerekli("yonetici")
def yedek():
    """Veritabaninin tutarli bir kopyasini indirir.

    Dosyayi dogrudan kopyalamak yerine SQLite'in kendi yedekleme arayuzu
    kullaniliyor; boylece uygulama acikken, tam o anda bir kayit yazilirken
    yedek alinsa bile bozuk dosya olusmuyor.
    """
    kaynak = sqlite3.connect(current_app.config["VERITABANI"])
    tampon = io.BytesIO()
    try:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as gecici:
            gecici_yol = gecici.name
        hedef = sqlite3.connect(gecici_yol)
        kaynak.backup(hedef)
        hedef.close()
        with open(gecici_yol, "rb") as f:
            tampon.write(f.read())
        os.remove(gecici_yol)
    finally:
        kaynak.close()
    tampon.seek(0)

    dosya_adi = f"depo-yedek-{db.bugun()}.db"
    db.log_yaz(g.kullanici, "yedek_al", dosya_adi)
    return send_file(tampon, mimetype="application/x-sqlite3",
                     as_attachment=True, download_name=dosya_adi)


# ------------------------------------------------------------------- islem log
@bp.route("/gecmis")
@rol_gerekli("yonetici")
def gecmis():
    sayfa = max(1, request.args.get("sayfa", 1, type=int))
    boyut = 100
    toplam = db.tek_deger("SELECT COUNT(*) FROM islem_log", (), 0)
    satirlar = db.sorgu(
        "SELECT * FROM islem_log ORDER BY id DESC LIMIT ? OFFSET ?",
        (boyut, (sayfa - 1) * boyut))
    return render_template("tanim_gecmis.html", satirlar=satirlar, sayfa=sayfa,
                           sayfa_sayisi=max(1, -(-toplam // boyut)), toplam=toplam)
