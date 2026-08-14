"""Raporlar ve Excel'e (CSV) aktarim."""

import csv
import io
from datetime import datetime, timedelta

from flask import Blueprint, Response, render_template, request

import db
from auth import giris_gerekli, rol_gerekli
from sabitler import HAREKET_TIPLERI

bp = Blueprint("raporlar", __name__, url_prefix="/raporlar")


@bp.route("/")
@giris_gerekli
def anasayfa():
    return render_template("rapor_menu.html")


# --------------------------------------------------------------- stok degeri
@bp.route("/stok-degeri")
@giris_gerekli
def stok_degeri():
    depo_id = request.args.get("depo", type=int)
    depo_kosul = "AND s.depo_id = ?" if depo_id else ""
    params = (depo_id,) if depo_id else ()

    kategoriler = db.sorgu(
        f"""SELECT IFNULL(vv.kategori_ad, 'Kategorisiz') AS kategori,
                   COUNT(DISTINCT vv.varyant_id) AS kalem,
                   COALESCE(SUM(s.miktar), 0)    AS miktar,
                   COALESCE(SUM(s.miktar * vv.birim_fiyat), 0) AS tutar
            FROM v_varyant vv
            LEFT JOIN v_stok s ON s.varyant_id = vv.varyant_id {depo_kosul}
            WHERE vv.varyant_aktif = 1 AND vv.urun_aktif = 1
            GROUP BY IFNULL(vv.kategori_ad, 'Kategorisiz')
            HAVING tutar <> 0 OR miktar <> 0
            ORDER BY tutar DESC""", params)

    en_degerli = db.sorgu(
        f"""SELECT vv.urun_ad, vv.sku, vv.renk_dekor, vv.ana_birim, vv.birim_fiyat,
                   COALESCE(SUM(s.miktar), 0) AS miktar,
                   COALESCE(SUM(s.miktar * vv.birim_fiyat), 0) AS tutar
            FROM v_varyant vv
            LEFT JOIN v_stok s ON s.varyant_id = vv.varyant_id {depo_kosul}
            WHERE vv.varyant_aktif = 1 AND vv.urun_aktif = 1
            GROUP BY vv.varyant_id
            HAVING tutar > 0
            ORDER BY tutar DESC LIMIT 25""", params)

    toplam = sum(k["tutar"] for k in kategoriler)
    return render_template("rapor_stok_degeri.html", kategoriler=kategoriler,
                           en_degerli=en_degerli, toplam=toplam,
                           depolar=db.depo_listesi(), secili_depo=depo_id)


# ----------------------------------------------------------------- fire analizi
@bp.route("/fire")
@giris_gerekli
def fire():
    bas = request.args.get("bas") or (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    bit = request.args.get("bit") or db.bugun()

    satirlar = db.sorgu(
        """SELECT vv.varyant_id, vv.urun_ad, vv.sku, vv.renk_dekor, vv.ana_birim,
                  vv.birim_fiyat, vv.kategori_ad,
                  SUM(CASE WHEN h.tip = 'fire' THEN ABS(h.miktar) ELSE 0 END) AS fire,
                  SUM(CASE WHEN h.tip IN ('sarf','sevk','fire')
                           THEN ABS(h.miktar) ELSE 0 END) AS tuketim
           FROM hareketler h
           JOIN v_varyant vv ON vv.varyant_id = h.varyant_id
           WHERE h.tarih BETWEEN ? AND ?
             AND h.tip IN ('sarf','sevk','fire')
           GROUP BY vv.varyant_id
           HAVING fire > 0
           ORDER BY fire * vv.birim_fiyat DESC""", (bas, bit))

    toplam_fire_tutar = sum(s["fire"] * (s["birim_fiyat"] or 0) for s in satirlar)
    genel_fire = db.tek_deger(
        "SELECT COALESCE(SUM(ABS(miktar)),0) FROM hareketler"
        " WHERE tip='fire' AND tarih BETWEEN ? AND ?", (bas, bit), 0.0)
    genel_tuketim = db.tek_deger(
        "SELECT COALESCE(SUM(ABS(miktar)),0) FROM hareketler"
        " WHERE tip IN ('sarf','sevk','fire') AND tarih BETWEEN ? AND ?",
        (bas, bit), 0.0)

    return render_template("rapor_fire.html", satirlar=satirlar, bas=bas, bit=bit,
                           toplam_fire_tutar=toplam_fire_tutar,
                           genel_oran=(genel_fire / genel_tuketim * 100)
                           if genel_tuketim else 0)


# ------------------------------------------------------------ siparis onerisi
@bp.route("/siparis")
@giris_gerekli
def siparis():
    """Tuketim hizi + tedarik suresine gore 'simdi siparis verilmeli' listesi."""
    gun = request.args.get("gun", 90, type=int)
    satirlar = db.sorgu(
        """SELECT vv.varyant_id, vv.urun_ad, vv.urun_kod, vv.sku, vv.renk_dekor,
                  vv.olcu, vv.ana_birim, vv.min_stok, vv.birim_fiyat,
                  vv.tedarikci_ad, IFNULL(vv.teslim_gun, 7) AS teslim_gun,
                  COALESCE(st.miktar, 0) AS stok,
                  COALESCE(rz.miktar, 0) AS rezerve,
                  COALESCE(tk.miktar, 0) / ? AS gunluk
           FROM v_varyant vv
           LEFT JOIN (SELECT varyant_id, SUM(miktar) miktar FROM v_stok
                       GROUP BY varyant_id) st ON st.varyant_id = vv.varyant_id
           LEFT JOIN (SELECT varyant_id, SUM(miktar) miktar FROM v_rezerve
                       GROUP BY varyant_id) rz ON rz.varyant_id = vv.varyant_id
           LEFT JOIN (SELECT varyant_id, SUM(ABS(miktar)) miktar FROM hareketler
                       WHERE tip IN ('sarf','sevk','fire')
                         AND tarih >= date('now', ?)
                       GROUP BY varyant_id) tk ON tk.varyant_id = vv.varyant_id
           WHERE vv.varyant_aktif = 1 AND vv.urun_aktif = 1
           ORDER BY vv.urun_ad""", (float(gun), f"-{gun} day"))

    oneriler = []
    for s in satirlar:
        kullanilabilir = (s["stok"] or 0) - (s["rezerve"] or 0)
        gunluk = s["gunluk"] or 0
        kalan_gun = (kullanilabilir / gunluk) if gunluk > 0 else None
        teslim = s["teslim_gun"] or 7
        kritik = kullanilabilir <= s["min_stok"]
        zamani_geldi = kalan_gun is not None and kalan_gun <= teslim + 3

        if not (kritik or zamani_geldi):
            continue
        # Teslim suresi + 30 gunluk emniyet stogu hedeflenir
        hedef = max(s["min_stok"], gunluk * (teslim + 30))
        oneriler.append({
            **dict(s), "kullanilabilir": kullanilabilir, "kalan_gun": kalan_gun,
            "onerilen": max(0, round(hedef - kullanilabilir, 2)),
            "sebep": "kritik seviye" if kritik else "tedarik süresi doluyor",
        })

    oneriler.sort(key=lambda o: (o["kalan_gun"] if o["kalan_gun"] is not None else 9999))
    return render_template("rapor_siparis.html", oneriler=oneriler, gun=gun)


# ----------------------------------------------------------------- hareket ozet
@bp.route("/hareket-ozet")
@giris_gerekli
def hareket_ozet():
    bas = request.args.get("bas") or (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    bit = request.args.get("bit") or db.bugun()
    depo_id = request.args.get("depo", type=int)

    kosul, params = "h.tarih BETWEEN ? AND ?", [bas, bit]
    if depo_id:
        kosul += " AND h.depo_id = ?"
        params.append(depo_id)

    tipler = db.sorgu(
        f"""SELECT h.tip, COUNT(*) AS adet, SUM(ABS(h.miktar)) AS miktar,
                   SUM(ABS(h.miktar) * IFNULL(v.birim_fiyat,0)) AS tutar
            FROM hareketler h JOIN varyantlar v ON v.id = h.varyant_id
            WHERE {kosul} GROUP BY h.tip ORDER BY tutar DESC""", tuple(params))

    kullanicilar = db.sorgu(
        f"""SELECT IFNULL(k.ad_soyad,'-') AS ad, COUNT(*) AS adet
            FROM hareketler h LEFT JOIN kullanicilar k ON k.id = h.kullanici_id
            WHERE {kosul} GROUP BY h.kullanici_id ORDER BY adet DESC""", tuple(params))

    gunluk = db.sorgu(
        f"""SELECT h.tarih, COUNT(*) AS adet
            FROM hareketler h WHERE {kosul}
            GROUP BY h.tarih ORDER BY h.tarih DESC LIMIT 30""", tuple(params))

    return render_template("rapor_hareket_ozet.html", tipler=tipler,
                           kullanicilar=kullanicilar, gunluk=gunluk,
                           bas=bas, bit=bit, depolar=db.depo_listesi(),
                           secili_depo=depo_id, HAREKET_TIPLERI=HAREKET_TIPLERI)


# ------------------------------------------------------------- proje maliyet
@bp.route("/proje-maliyet")
@rol_gerekli("depo")
def proje_maliyet():
    satirlar = db.sorgu(
        """SELECT p.*,
                  COALESCE(SUM(CASE WHEN h.miktar < 0
                       THEN ABS(h.miktar) * IFNULL(v.birim_fiyat,0) END), 0) AS tutar,
                  COUNT(DISTINCT h.varyant_id) AS kalem
           FROM projeler p
           LEFT JOIN hareketler h ON h.proje_id = p.id
           LEFT JOIN varyantlar v ON v.id = h.varyant_id
           GROUP BY p.id
           ORDER BY tutar DESC""")
    return render_template("rapor_proje_maliyet.html", satirlar=satirlar)


# --------------------------------------------------------------------- disari
def _csv_yanit(basliklar, satirlar, dosya_adi):
    """Excel'in Turkce yerel ayariyla dogru acmasi icin BOM + noktali virgul."""
    tampon = io.StringIO()
    yazici = csv.writer(tampon, delimiter=";")
    yazici.writerow(basliklar)
    yazici.writerows(satirlar)
    icerik = "﻿" + tampon.getvalue()
    return Response(
        icerik, mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{dosya_adi}"'})


@bp.route("/disari/stok")
@giris_gerekli
def disari_stok():
    depo_id = request.args.get("depo", type=int)
    satirlar = db.stok_listesi(
        depo_id=depo_id,
        kategori_id=request.args.get("kategori", type=int),
        arama=(request.args.get("q") or "").strip() or None,
        sadece_kritik=request.args.get("kritik") == "1",
        sadece_stokta=request.args.get("stokta") == "1")

    def vir(d):
        return str(round(d or 0, 3)).replace(".", ",")

    return _csv_yanit(
        ["Stok Kodu", "Ürün Kodu", "Ürün", "Renk/Dekor", "Ölçü", "Kategori",
         "Birim", "Stok", "Rezerve", "Kullanılabilir", "Min. Stok",
         "Birim Fiyat", "Stok Değeri", "Tedarikçi"],
        [[s["sku"], s["urun_kod"], s["urun_ad"], s["renk_dekor"] or "",
          s["olcu"] or "", s["kategori_ad"] or "", s["ana_birim"],
          vir(s["stok"]), vir(s["rezerve"]), vir(s["kullanilabilir"]),
          vir(s["min_stok"]), vir(s["birim_fiyat"]), vir(s["stok_degeri"]),
          s["tedarikci_ad"] or ""] for s in satirlar],
        f"stok_{db.bugun()}.csv")


@bp.route("/disari/hareket")
@giris_gerekli
def disari_hareket():
    bas = request.args.get("bas") or "1900-01-01"
    bit = request.args.get("bit") or "2999-12-31"
    tip = request.args.get("tip") or ""
    depo_id = request.args.get("depo", type=int)

    kosul, params = ["h.tarih BETWEEN ? AND ?"], [bas, bit]
    if tip:
        kosul.append("h.tip = ?")
        params.append(tip)
    if depo_id:
        kosul.append("h.depo_id = ?")
        params.append(depo_id)

    satirlar = db.sorgu(
        f"""SELECT h.*, vv.urun_ad, vv.sku, vv.renk_dekor, vv.ana_birim,
                   d.ad AS depo_ad, k.ad_soyad AS kullanici_ad,
                   p.kod AS proje_kod, t.ad AS tedarikci_ad
            FROM hareketler h
            JOIN v_varyant vv ON vv.varyant_id = h.varyant_id
            JOIN depolar d ON d.id = h.depo_id
            LEFT JOIN kullanicilar k ON k.id = h.kullanici_id
            LEFT JOIN projeler p     ON p.id = h.proje_id
            LEFT JOIN tedarikciler t ON t.id = h.tedarikci_id
            WHERE {' AND '.join(kosul)}
            ORDER BY h.tarih, h.id""", tuple(params))

    return _csv_yanit(
        ["No", "Tarih", "İşlem", "Stok Kodu", "Ürün", "Renk/Dekor", "Depo",
         "Miktar", "Birim", "Belge No", "Tedarikçi", "Proje", "Kullanıcı",
         "Açıklama"],
        [[s["id"], s["tarih"], HAREKET_TIPLERI.get(s["tip"], {}).get("ad", s["tip"]),
          s["sku"], s["urun_ad"], s["renk_dekor"] or "", s["depo_ad"],
          str(round(s["miktar"], 3)).replace(".", ","), s["ana_birim"],
          s["belge_no"] or "", s["tedarikci_ad"] or "", s["proje_kod"] or "",
          s["kullanici_ad"] or "", s["aciklama"] or ""] for s in satirlar],
        f"hareketler_{db.bugun()}.csv")
