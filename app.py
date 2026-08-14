"""Redecor Depo Takip Sistemi - uygulama giris noktasi."""

import os
import secrets
from datetime import timedelta

from flask import Flask, g, redirect, render_template, url_for

import db
import sabitler


def gizli_anahtar(proje_dizin: str) -> str:
    """Oturum anahtarini dosyada saklar; her acilista oturumlar dusmesin diye."""
    yol = os.path.join(proje_dizin, "veri", "gizli_anahtar.txt")
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    if os.path.exists(yol):
        with open(yol, "r", encoding="utf-8") as f:
            deger = f.read().strip()
            if deger:
                return deger
    deger = secrets.token_hex(32)
    with open(yol, "w", encoding="utf-8") as f:
        f.write(deger)
    os.chmod(yol, 0o600)
    return deger


def uygulama_olustur(test_config=None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    proje_dizin = os.path.dirname(os.path.abspath(__file__))

    app.config.from_mapping(
        SECRET_KEY=gizli_anahtar(proje_dizin),
        VERITABANI=os.path.join(proje_dizin, "veri", "depo.db"),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        JSON_AS_ASCII=False,
        MAX_CONTENT_LENGTH=16 * 1024 * 1024,   # toplu aktarim dosyasi ust siniri
    )
    if test_config:
        app.config.update(test_config)

    db.sema_kur(app)
    db.uygulamaya_bagla(app)

    # ------------------------------------------------------------ bolumler
    import auth
    from bolumler import (aktarim, barkod, hareketler, panel, projeler,
                          raporlar, sayim, stok, tanimlar, urunler)

    app.register_blueprint(auth.bp)
    app.register_blueprint(panel.bp)
    app.register_blueprint(stok.bp)
    app.register_blueprint(urunler.bp)
    app.register_blueprint(hareketler.bp)
    app.register_blueprint(projeler.bp)
    app.register_blueprint(sayim.bp)
    app.register_blueprint(raporlar.bp)
    app.register_blueprint(barkod.bp)
    app.register_blueprint(aktarim.bp)
    app.register_blueprint(tanimlar.bp)

    @app.route("/")
    def kok():
        return redirect(url_for("panel.anasayfa"))

    # ------------------------------------------------------ sablon yardimcilari
    @app.template_filter("sayi")
    def sayi_bicimle(deger, ondalik=2):
        """1234.5 -> '1.234,5' (gereksiz sifirlari atar)."""
        if deger is None:
            return "0"
        try:
            deger = float(deger)
        except (TypeError, ValueError):
            return str(deger)
        metin = f"{deger:,.{ondalik}f}"
        metin = metin.replace(",", "#").replace(".", ",").replace("#", ".")
        if "," in metin:
            metin = metin.rstrip("0").rstrip(",")
        return metin or "0"

    @app.template_filter("para")
    def para_bicimle(deger):
        if deger is None:
            deger = 0
        try:
            deger = float(deger)
        except (TypeError, ValueError):
            return str(deger)
        metin = f"{deger:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")
        return f"{metin} ₺"

    @app.template_filter("kisa_tarih")
    def kisa_tarih(deger):
        """'2026-08-09 14:30:00' -> '09.08.2026 14:30'"""
        if not deger:
            return "-"
        metin = str(deger)
        try:
            tarih_kismi = metin[:10]
            y, a, g_ = tarih_kismi.split("-")
            sonuc = f"{g_}.{a}.{y}"
            if len(metin) > 11:
                sonuc += " " + metin[11:16]
            return sonuc
        except ValueError:
            return metin

    @app.context_processor
    def sablon_degiskenleri():
        return {
            "sabitler": sabitler,
            "kullanici": g.get("kullanici"),
            "UYGULAMA_ADI": sabitler.UYGULAMA_ADI,
            "rol_yeterli": sabitler.rol_yeterli,
        }

    @app.errorhandler(404)
    def bulunamadi(e):
        return render_template("hata.html", kod=404,
                               mesaj="Aradığınız sayfa bulunamadı."), 404

    @app.errorhandler(500)
    def sunucu_hatasi(e):
        return render_template("hata.html", kod=500,
                               mesaj="Beklenmeyen bir hata oluştu."), 500

    return app


app = uygulama_olustur()


if __name__ == "__main__":
    # macOS'ta 5000 portunu AirPlay servisi kullaniyor, o yuzden 5051.
    port = int(os.environ.get("PORT", 5051))
    app.run(host="127.0.0.1", port=port, debug=True)
