"""Barkod uretimi, etiket basimi ve el terminaliyle okutma.

El terminali (USB/bluetooth barkod okuyucu) klavye gibi davranir: okuttugunuzda
kodu yazip Enter'a basar. Bu yuzden ayri bir surucu ya da eklenti gerekmez;
odaklanmis bir metin kutusu yeterlidir.
"""

import barcode as barkod_kutuphanesi
from barcode.writer import SVGWriter
from flask import (Blueprint, abort, flash, g, jsonify, redirect,
                   render_template, request, url_for)

import db
from auth import giris_gerekli, rol_gerekli

bp = Blueprint("barkod", __name__, url_prefix="/barkod")

# Etiket uzerindeki barkodun olculeri (mm)
ETIKET_AYARI = {
    "module_width": 0.26,
    "module_height": 9.0,
    "font_size": 7,
    "text_distance": 2.0,
    "quiet_zone": 1.0,
    "write_text": False,   # kodu biz ayrica yaziyoruz, cift yazmasin
}


def barkod_uret(varyant_id: int) -> str:
    """Firma ici barkod numarasi. Kisa tutuluyor ki etikete sigsin."""
    return f"RD{varyant_id:06d}"


def svg_ciz(deger: str) -> str:
    """Code128 barkodunu satir ici SVG olarak dondurur.

    Code128 her turlu harf-rakam kombinasyonunu tasiyabildigi icin hem bizim
    urettigimiz kodlar hem de tedarikcinin kutu uzerindeki mevcut barkodu
    ayni sekilde basilabiliyor.
    """
    try:
        nesne = barkod_kutuphanesi.get("code128", deger, writer=SVGWriter())
        ham = nesne.render(ETIKET_AYARI).decode("utf-8")
    except Exception:
        return ""
    # XML basligini ve DOCTYPE'i atip sadece <svg> govdesini birakiyoruz
    yer = ham.find("<svg")
    return ham[yer:] if yer >= 0 else ""


@bp.route("/")
@rol_gerekli("depo")
def liste():
    arama = (request.args.get("q") or "").strip()
    kategori_id = request.args.get("kategori", type=int)
    eksik = request.args.get("eksik") == "1"

    satirlar = db.stok_listesi(kategori_id=kategori_id, arama=arama or None)
    if eksik:
        satirlar = [s for s in satirlar if not s["barkod"]]

    return render_template("barkod_liste.html", satirlar=satirlar,
                           kategoriler=db.kategori_listesi(), arama=arama,
                           secili_kategori=kategori_id, eksik=eksik,
                           barkodsuz=sum(1 for s in satirlar if not s["barkod"]))


@bp.route("/uret", methods=("POST",))
@rol_gerekli("depo")
def uret():
    """Secili varyantlara barkod numarasi atar. Var olan barkoda dokunmaz."""
    idler = request.form.getlist("varyant_id")
    hepsi = request.form.get("hepsi") == "1"

    if hepsi:
        idler = [str(r["id"]) for r in db.sorgu(
            "SELECT id FROM varyantlar WHERE aktif=1"
            " AND (barkod IS NULL OR barkod = '')")]

    uretilen = 0
    for vid in idler:
        try:
            varyant_id = int(vid)
        except ValueError:
            continue
        v = db.sorgu("SELECT * FROM varyantlar WHERE id = ?", (varyant_id,), tek=True)
        if v is None or (v["barkod"] or "").strip():
            continue
        db.calistir("UPDATE varyantlar SET barkod = ? WHERE id = ?",
                    (barkod_uret(varyant_id), varyant_id))
        uretilen += 1

    db.log_yaz(g.kullanici, "barkod_uret", f"{uretilen} varyanta barkod atandı")
    if uretilen:
        flash(f"{uretilen} kaleme barkod üretildi.", "basari")
    else:
        flash("Barkod üretilecek kalem bulunamadı (hepsinde zaten barkod var).", "bilgi")
    return redirect(request.referrer or url_for("barkod.liste"))


@bp.route("/etiket", methods=("POST",))
@rol_gerekli("depo")
def etiket():
    """Secili kalemler icin yazdirilabilir etiket sayfasi uretir."""
    idler = request.form.getlist("varyant_id")
    if not idler:
        flash("Etiket basmak için en az bir kalem seçmelisiniz.", "hata")
        return redirect(url_for("barkod.liste"))

    try:
        adet = max(1, min(50, int(request.form.get("adet") or 1)))
    except ValueError:
        adet = 1

    etiketler = []
    barkodsuz = 0
    for vid in idler:
        try:
            v = db.varyant_detay(int(vid))
        except ValueError:
            continue
        if v is None:
            continue
        kod = (v["barkod"] or "").strip()
        if not kod:
            barkodsuz += 1
            continue
        cizim = svg_ciz(kod)
        for _ in range(adet):
            etiketler.append({"v": v, "kod": kod, "svg": cizim})

    if barkodsuz:
        flash(f"{barkodsuz} kalemin barkodu olmadığı için etikete girmedi. "
              f"Önce 'Barkod üret' deyin.", "hata")
    if not etiketler:
        return redirect(url_for("barkod.liste"))

    db.log_yaz(g.kullanici, "etiket_bas", f"{len(etiketler)} etiket")
    return render_template("etiket_yazdir.html", etiketler=etiketler)


@bp.route("/oku")
@giris_gerekli
def oku():
    """El terminalinden okutulan kodu varyanta cevirir (JSON)."""
    kod = (request.args.get("kod") or "").strip()
    depo_id = request.args.get("depo", type=int)
    if not kod:
        return jsonify({"bulundu": False, "mesaj": "Boş kod"})

    v = db.sorgu(
        "SELECT * FROM v_varyant WHERE barkod = ? AND varyant_aktif = 1",
        (kod,), tek=True)
    if v is None:
        # Barkod alani bos birakilmis olabilir; stok kodundan da deneyelim
        v = db.sorgu(
            "SELECT * FROM v_varyant WHERE sku = ? AND varyant_aktif = 1",
            (kod.upper(),), tek=True)
    if v is None:
        return jsonify({"bulundu": False,
                        "mesaj": f"'{kod}' hiçbir ürüne tanımlı değil"})

    stok = db.varyant_stok(v["varyant_id"], depo_id)
    rezerve = db.varyant_rezerve(v["varyant_id"], depo_id)
    return jsonify({
        "bulundu": True,
        "id": v["varyant_id"],
        "sku": v["sku"],
        "ad": v["urun_ad"],
        "renk": v["renk_dekor"] or "",
        "olcu": v["olcu"] or "",
        "birim": v["ana_birim"],
        "stok": round(stok, 3),
        "kullanilabilir": round(stok - rezerve, 3),
    })


@bp.route("/varyant/<int:varyant_id>.svg")
@giris_gerekli
def tekil_svg(varyant_id):
    """Tek bir varyantin barkodunu SVG olarak dondurur (etiket onizleme)."""
    v = db.varyant_detay(varyant_id)
    if v is None or not (v["barkod"] or "").strip():
        abort(404)
    cizim = svg_ciz(v["barkod"].strip())
    if not cizim:
        abort(404)
    return cizim, 200, {"Content-Type": "image/svg+xml; charset=utf-8"}
