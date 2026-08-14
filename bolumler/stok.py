"""Stok listesi, arama ve varyant detay karti."""

from flask import Blueprint, abort, jsonify, render_template, request

import db
from auth import giris_gerekli

bp = Blueprint("stok", __name__, url_prefix="/stok")


@bp.route("/")
@giris_gerekli
def liste():
    depo_id = request.args.get("depo", type=int)
    kategori_id = request.args.get("kategori", type=int)
    tedarikci_id = request.args.get("tedarikci", type=int)
    arama = (request.args.get("q") or "").strip()
    kritik = request.args.get("kritik") == "1"
    stokta = request.args.get("stokta") == "1"
    siralama = request.args.get("sirala", "urun")

    satirlar = db.stok_listesi(
        depo_id=depo_id, kategori_id=kategori_id, arama=arama or None,
        sadece_kritik=kritik, sadece_stokta=stokta,
        tedarikci_id=tedarikci_id, siralama=siralama)

    toplam_deger = sum(s["stok_degeri"] or 0 for s in satirlar)
    # Liste bos: filtre mi daralttı, yoksa sistem henüz bos mu?
    sistem_bos = not satirlar and db.tek_deger(
        "SELECT COUNT(*) FROM varyantlar", (), 0) == 0

    return render_template(
        "stok_liste.html", satirlar=satirlar, sistem_bos=sistem_bos,
        depolar=db.depo_listesi(),
        kategoriler=db.kategori_listesi(), tedarikciler=db.tedarikci_listesi(),
        secili_depo=depo_id, secili_kategori=kategori_id,
        secili_tedarikci=tedarikci_id, arama=arama, kritik=kritik,
        stokta=stokta, siralama=siralama, toplam_deger=toplam_deger)


@bp.route("/varyant/<int:varyant_id>")
@giris_gerekli
def detay(varyant_id):
    varyant = db.varyant_detay(varyant_id)
    if varyant is None:
        abort(404)

    depo_dagilimi = db.sorgu(
        """SELECT d.id, d.ad,
                  COALESCE(s.miktar, 0) AS stok,
                  COALESCE(r.miktar, 0) AS rezerve
           FROM depolar d
           LEFT JOIN v_stok    s ON s.depo_id = d.id AND s.varyant_id = ?
           LEFT JOIN v_rezerve r ON r.depo_id = d.id AND r.varyant_id = ?
           WHERE d.aktif = 1
           ORDER BY d.ad""", (varyant_id, varyant_id))

    hareketler = db.sorgu(
        """SELECT h.*, d.ad AS depo_ad, k.ad_soyad AS kullanici_ad,
                  p.kod AS proje_kod, t.ad AS tedarikci_ad
           FROM hareketler h
           JOIN depolar d ON d.id = h.depo_id
           LEFT JOIN kullanicilar  k ON k.id = h.kullanici_id
           LEFT JOIN projeler      p ON p.id = h.proje_id
           LEFT JOIN tedarikciler  t ON t.id = h.tedarikci_id
           WHERE h.varyant_id = ?
           ORDER BY h.tarih DESC, h.id DESC LIMIT 100""", (varyant_id,))

    rezervasyonlar = db.sorgu(
        """SELECT r.*, p.kod AS proje_kod, p.musteri, d.ad AS depo_ad
           FROM rezervasyonlar r
           JOIN projeler p ON p.id = r.proje_id
           JOIN depolar  d ON d.id = r.depo_id
           WHERE r.varyant_id = ? AND r.durum = 'aktif'
           ORDER BY r.id DESC""", (varyant_id,))

    toplam_stok = sum(d["stok"] for d in depo_dagilimi)
    toplam_rezerve = sum(d["rezerve"] for d in depo_dagilimi)

    # Son 90 gunluk tuketim hizindan kalan gun tahmini
    gunluk = db.tek_deger(
        """SELECT COALESCE(SUM(ABS(miktar)),0) / 90.0 FROM hareketler
           WHERE varyant_id = ? AND tip IN ('sarf','sevk','fire')
             AND tarih >= date('now','-90 day')""", (varyant_id,), 0.0)
    kalan_gun = int((toplam_stok - toplam_rezerve) / gunluk) if gunluk > 0 else None

    return render_template(
        "varyant_detay.html", v=varyant, depo_dagilimi=depo_dagilimi,
        hareketler=hareketler, rezervasyonlar=rezervasyonlar,
        toplam_stok=toplam_stok, toplam_rezerve=toplam_rezerve,
        gunluk_tuketim=gunluk, kalan_gun=kalan_gun)


@bp.route("/ara")
@giris_gerekli
def ara():
    """Hareket ekranlarindaki hizli arama kutusu icin JSON ucu."""
    q = (request.args.get("q") or "").strip()
    depo_id = request.args.get("depo", type=int)
    if len(q) < 2:
        return jsonify([])

    satirlar = db.stok_listesi(depo_id=depo_id, arama=q)[:25]
    return jsonify([{
        "id": s["varyant_id"],
        "sku": s["sku"],
        "ad": s["urun_ad"],
        "renk": s["renk_dekor"] or "",
        "olcu": s["olcu"] or "",
        "birim": s["ana_birim"],
        "stok": round(s["stok"] or 0, 3),
        "kullanilabilir": round(s["kullanilabilir"] or 0, 3),
        "min_stok": s["min_stok"],
    } for s in satirlar])
