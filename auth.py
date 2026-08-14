"""Giris/cikis islemleri ve rol tabanli yetki kontrolu."""

import functools

from flask import (Blueprint, flash, g, redirect, render_template, request,
                   session, url_for)
import db
from guvenlik import sifre_dogrula, sifre_hashle
from sabitler import ROLLER, rol_yeterli

bp = Blueprint("auth", __name__)


@bp.before_app_request
def kullaniciyi_yukle():
    kid = session.get("kullanici_id")
    if kid is None:
        g.kullanici = None
    else:
        g.kullanici = db.sorgu(
            "SELECT * FROM kullanicilar WHERE id = ? AND aktif = 1", (kid,), tek=True)
        if g.kullanici is None:
            session.clear()


def giris_gerekli(view):
    @functools.wraps(view)
    def sarmalanmis(**kwargs):
        if g.kullanici is None:
            return redirect(url_for("auth.giris", devam=request.path))
        return view(**kwargs)
    return sarmalanmis


def rol_gerekli(gereken_rol):
    """Belirtilen rol seviyesinin altindaki kullanicilari engeller."""
    def dekorator(view):
        @functools.wraps(view)
        def sarmalanmis(**kwargs):
            if g.kullanici is None:
                return redirect(url_for("auth.giris", devam=request.path))
            if not rol_yeterli(g.kullanici["rol"], gereken_rol):
                flash(f"Bu işlem için '{ROLLER[gereken_rol]}' yetkisi gerekiyor.", "hata")
                return redirect(url_for("panel.anasayfa"))
            return view(**kwargs)
        return sarmalanmis
    return dekorator


@bp.route("/giris", methods=("GET", "POST"))
def giris():
    if g.kullanici is not None:
        return redirect(url_for("panel.anasayfa"))

    if request.method == "POST":
        kullanici_adi = request.form.get("kullanici_adi", "").strip()
        sifre = request.form.get("sifre", "")
        kullanici = db.sorgu(
            "SELECT * FROM kullanicilar WHERE kullanici_adi = ?",
            (kullanici_adi,), tek=True)

        if kullanici is None or not sifre_dogrula(kullanici["sifre_hash"], sifre):
            flash("Kullanıcı adı veya şifre hatalı.", "hata")
        elif not kullanici["aktif"]:
            flash("Bu kullanıcı pasif durumda. Yöneticiye başvurun.", "hata")
        else:
            session.clear()
            session["kullanici_id"] = kullanici["id"]
            session.permanent = True
            g.kullanici = kullanici
            db.log_yaz(kullanici, "giris", "sisteme giriş yapıldı")
            devam = request.args.get("devam")
            if devam and devam.startswith("/"):
                return redirect(devam)
            return redirect(url_for("panel.anasayfa"))

    return render_template("giris.html")


@bp.route("/cikis")
def cikis():
    if g.kullanici is not None:
        db.log_yaz(g.kullanici, "cikis", "oturum kapatıldı")
    session.clear()
    return redirect(url_for("auth.giris"))


@bp.route("/sifre-degistir", methods=("GET", "POST"))
@giris_gerekli
def sifre_degistir():
    if request.method == "POST":
        mevcut = request.form.get("mevcut", "")
        yeni = request.form.get("yeni", "")
        yeni2 = request.form.get("yeni2", "")

        if not sifre_dogrula(g.kullanici["sifre_hash"], mevcut):
            flash("Mevcut şifre hatalı.", "hata")
        elif len(yeni) < 4:
            flash("Yeni şifre en az 4 karakter olmalı.", "hata")
        elif yeni != yeni2:
            flash("Yeni şifreler birbiriyle uyuşmuyor.", "hata")
        else:
            db.calistir("UPDATE kullanicilar SET sifre_hash = ? WHERE id = ?",
                        (sifre_hashle(yeni), g.kullanici["id"]))
            db.log_yaz(g.kullanici, "sifre_degisti", "kendi şifresini değiştirdi")
            flash("Şifreniz güncellendi.", "basari")
            return redirect(url_for("panel.anasayfa"))

    return render_template("sifre_degistir.html")
