"""Fiziksel sayim (envanter) modulu.

Sayim korlemesine yapilir: sayimi yapan kisi sistemdeki rakami GOREMEZ.
Gorurse cogu zaman sistemdeki sayiyi yazar ve sayim hicbir ise yaramaz.
Sistem miktari ancak sayim kapatilinca fark raporunda ortaya cikar.
"""

from flask import (Blueprint, abort, flash, g, redirect, render_template,
                   request, url_for)

import db
from auth import giris_gerekli, rol_gerekli
from bolumler.hareketler import hareket_ekle

bp = Blueprint("sayim", __name__, url_prefix="/sayim")


@bp.route("/")
@giris_gerekli
def liste():
    sayimlar = db.sorgu(
        """SELECT s.*, d.ad AS depo_ad, k.ad_soyad AS kullanici_ad,
                  (SELECT COUNT(*) FROM sayim_satirlari ss
                    WHERE ss.sayim_id = s.id) AS satir_sayisi,
                  (SELECT COUNT(*) FROM sayim_satirlari ss
                    WHERE ss.sayim_id = s.id AND ss.sayilan_miktar IS NOT NULL)
                    AS sayilan_sayisi
           FROM sayimlar s
           JOIN depolar d ON d.id = s.depo_id
           LEFT JOIN kullanicilar k ON k.id = s.kullanici_id
           ORDER BY s.id DESC""")
    return render_template("sayim_liste.html", sayimlar=sayimlar,
                           depolar=db.depo_listesi(),
                           kategoriler=db.kategori_listesi(), bugun=db.bugun())


@bp.route("/yeni", methods=("POST",))
@rol_gerekli("depo")
def yeni():
    depo_id = request.form.get("depo_id", type=int)
    kategori_id = request.form.get("kategori_id", type=int)
    kapsam = request.form.get("kapsam", "hepsi")

    if not depo_id:
        flash("Depo seçmelisiniz.", "hata")
        return redirect(url_for("sayim.liste"))

    acik = db.sorgu("SELECT * FROM sayimlar WHERE depo_id=? AND durum='acik'",
                    (depo_id,), tek=True)
    if acik:
        flash("Bu depoda zaten açık bir sayım var. Önce onu tamamlayın.", "hata")
        return redirect(url_for("sayim.detay", sayim_id=acik["id"]))

    sayim_id = db.calistir(
        """INSERT INTO sayimlar (depo_id, tarih, durum, kullanici_id, notlar)
           VALUES (?,?,'acik',?,?)""",
        (depo_id, db.bugun(), g.kullanici["id"],
         (request.form.get("notlar") or "").strip() or None))

    # Sayilacak kalemler: sistemdeki miktar anlik fotograf olarak saklanir
    params = [depo_id]
    kosul = ""
    if kategori_id:
        kosul += " AND vv.kategori_id = ?"
        params.append(kategori_id)
    if kapsam == "stokta":
        kosul += " AND COALESCE(s.miktar,0) <> 0"

    kalemler = db.sorgu(
        f"""SELECT vv.varyant_id, COALESCE(s.miktar, 0) AS miktar
            FROM v_varyant vv
            LEFT JOIN v_stok s ON s.varyant_id = vv.varyant_id AND s.depo_id = ?
            WHERE vv.varyant_aktif = 1 AND vv.urun_aktif = 1 {kosul}""",
        tuple(params))

    for k in kalemler:
        db.calistir(
            "INSERT INTO sayim_satirlari (sayim_id, varyant_id, sistem_miktar)"
            " VALUES (?,?,?)", (sayim_id, k["varyant_id"], k["miktar"]))

    db.log_yaz(g.kullanici, "sayim_baslat", f"#{sayim_id}, {len(kalemler)} kalem")
    flash(f"Sayım başlatıldı. {len(kalemler)} kalem sayılacak.", "basari")
    return redirect(url_for("sayim.detay", sayim_id=sayim_id))


@bp.route("/<int:sayim_id>")
@giris_gerekli
def detay(sayim_id):
    sayim = db.sorgu(
        """SELECT s.*, d.ad AS depo_ad, k.ad_soyad AS kullanici_ad
           FROM sayimlar s JOIN depolar d ON d.id = s.depo_id
           LEFT JOIN kullanicilar k ON k.id = s.kullanici_id
           WHERE s.id = ?""", (sayim_id,), tek=True)
    if sayim is None:
        abort(404)

    arama = (request.args.get("q") or "").strip()
    sadece_bos = request.args.get("bos") == "1"

    kosul, params = "", [sayim_id]
    if arama:
        sutunlar = ["vv.urun_ad", "vv.sku", "vv.renk_dekor"]
        kosul += " AND " + db.arama_kosulu(sutunlar)
        params.extend([f"%{arama}%"] * len(sutunlar))
    if sadece_bos:
        kosul += " AND ss.sayilan_miktar IS NULL"

    satirlar = db.sorgu(
        f"""SELECT ss.*, vv.urun_ad, vv.urun_kod, vv.sku, vv.renk_dekor, vv.olcu,
                   vv.ana_birim, vv.kategori_ad, vv.birim_fiyat,
                   COALESCE(cs.miktar, 0) AS guncel_stok
            FROM sayim_satirlari ss
            JOIN v_varyant vv ON vv.varyant_id = ss.varyant_id
            LEFT JOIN v_stok cs ON cs.varyant_id = ss.varyant_id
                               AND cs.depo_id = ?
            WHERE ss.sayim_id = ? {kosul}
            ORDER BY vv.kategori_ad, vv.urun_ad, vv.renk_dekor""",
        tuple([sayim["depo_id"]] + params))

    ozet = {
        "toplam": db.tek_deger(
            "SELECT COUNT(*) FROM sayim_satirlari WHERE sayim_id=?", (sayim_id,), 0),
        "sayilan": db.tek_deger(
            "SELECT COUNT(*) FROM sayim_satirlari"
            " WHERE sayim_id=? AND sayilan_miktar IS NOT NULL", (sayim_id,), 0),
    }

    farkli = []
    if sayim["durum"] != "acik":
        farkli = [s for s in satirlar
                  if s["sayilan_miktar"] is not None
                  and abs(s["sayilan_miktar"] - s["sistem_miktar"]) > 0.0001]

    return render_template("sayim_detay.html", sayim=sayim, satirlar=satirlar,
                           ozet=ozet, arama=arama, sadece_bos=sadece_bos,
                           farkli=farkli)


@bp.route("/<int:sayim_id>/kaydet", methods=("POST",))
@rol_gerekli("depo")
def kaydet(sayim_id):
    sayim = db.sorgu("SELECT * FROM sayimlar WHERE id = ?", (sayim_id,), tek=True)
    if sayim is None:
        abort(404)
    if sayim["durum"] != "acik":
        flash("Kapanmış sayım değiştirilemez.", "hata")
        return redirect(url_for("sayim.detay", sayim_id=sayim_id))

    guncellenen = 0
    for anahtar, deger in request.form.items():
        if not anahtar.startswith("sayilan_"):
            continue
        satir_id = anahtar.split("_", 1)[1]
        deger = (deger or "").strip().replace(",", ".")
        if deger == "":
            db.calistir(
                "UPDATE sayim_satirlari SET sayilan_miktar = NULL"
                " WHERE id = ? AND sayim_id = ?", (satir_id, sayim_id))
            continue
        try:
            miktar = float(deger)
        except ValueError:
            continue
        db.calistir(
            "UPDATE sayim_satirlari SET sayilan_miktar = ?"
            " WHERE id = ? AND sayim_id = ?", (miktar, satir_id, sayim_id))
        guncellenen += 1

    flash(f"{guncellenen} kalem kaydedildi.", "basari")
    return redirect(url_for("sayim.detay", sayim_id=sayim_id,
                            q=request.form.get("q") or None,
                            bos=request.form.get("bos") or None))


@bp.route("/<int:sayim_id>/tamamla", methods=("POST",))
@rol_gerekli("depo")
def tamamla(sayim_id):
    """Sayimi kapatir ve farklar icin duzeltme hareketi olusturur."""
    sayim = db.sorgu("SELECT * FROM sayimlar WHERE id = ?", (sayim_id,), tek=True)
    if sayim is None:
        abort(404)
    if sayim["durum"] != "acik":
        flash("Bu sayım zaten kapanmış.", "hata")
        return redirect(url_for("sayim.detay", sayim_id=sayim_id))

    satirlar = db.sorgu(
        """SELECT ss.*, COALESCE(s.miktar, 0) AS guncel_stok, vv.sku, vv.ana_birim
           FROM sayim_satirlari ss
           JOIN v_varyant vv ON vv.varyant_id = ss.varyant_id
           LEFT JOIN v_stok s ON s.varyant_id = ss.varyant_id AND s.depo_id = ?
           WHERE ss.sayim_id = ? AND ss.sayilan_miktar IS NOT NULL""",
        (sayim["depo_id"], sayim_id))

    duzeltme, artan, azalan = 0, 0.0, 0.0
    for s in satirlar:
        # Fark, sayim aciliş fotografina gore degil GUNCEL stoga gore hesaplanir;
        # sayim suresince baska hareket girilmis olabilir.
        fark = round(s["sayilan_miktar"] - s["guncel_stok"], 4)
        if abs(fark) < 0.0001:
            continue
        hareket_ekle("sayim", s["varyant_id"], sayim["depo_id"], fark, g.kullanici,
                     tarih=db.bugun(), sayim_id=sayim_id, isaretli=True,
                     aciklama=f"#{sayim_id} sayım farkı "
                              f"(sistem {s['guncel_stok']:g} → sayılan {s['sayilan_miktar']:g})")
        duzeltme += 1
        if fark > 0:
            artan += fark
        else:
            azalan += abs(fark)

    db.calistir("UPDATE sayimlar SET durum='tamamlandi', kapanis=? WHERE id=?",
                (db.simdi(), sayim_id))
    db.log_yaz(g.kullanici, "sayim_tamamla",
               f"#{sayim_id}, {duzeltme} kalemde fark bulundu")
    flash(f"Sayım tamamlandı. {duzeltme} kalemde fark çıktı, stok düzeltildi.",
          "basari" if duzeltme == 0 else "bilgi")
    return redirect(url_for("sayim.detay", sayim_id=sayim_id))


@bp.route("/<int:sayim_id>/iptal", methods=("POST",))
@rol_gerekli("yonetici")
def iptal(sayim_id):
    sayim = db.sorgu("SELECT * FROM sayimlar WHERE id = ?", (sayim_id,), tek=True)
    if sayim is None:
        abort(404)
    if sayim["durum"] != "acik":
        flash("Sadece açık sayımlar iptal edilebilir.", "hata")
        return redirect(url_for("sayim.detay", sayim_id=sayim_id))
    db.calistir("UPDATE sayimlar SET durum='iptal', kapanis=? WHERE id=?",
                (db.simdi(), sayim_id))
    db.log_yaz(g.kullanici, "sayim_iptal", f"#{sayim_id}")
    flash("Sayım iptal edildi, stoklara dokunulmadı.", "bilgi")
    return redirect(url_for("sayim.liste"))
