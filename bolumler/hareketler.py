"""Stok hareketleri: giris, cikis, fire, iade, transfer ve hareket dokumu.

Kural: stok hicbir yerde sabit sayi olarak tutulmaz. Her rakam bu tablodaki
hareketlerin toplamidir; boylece "bu 12 adet nereye gitti" sorusunun cevabi
her zaman vardir. Yanlis kayit silinmez, ters kayitla (storno) iptal edilir.
"""

import uuid

from flask import (Blueprint, abort, flash, g, redirect, render_template,
                   request, url_for)

import db
from auth import giris_gerekli, rol_gerekli
from sabitler import ELLE_GIRILEN_TIPLER, HAREKET_TIPLERI, rol_yeterli

bp = Blueprint("hareketler", __name__, url_prefix="/hareket")


def hareket_ekle(tip, varyant_id, depo_id, miktar, kullanici, tarih=None,
                 belge_no=None, tedarikci_id=None, proje_id=None,
                 aciklama=None, birim_fiyat=None, transfer_grup=None,
                 sayim_id=None, isaretli=False):
    """Tek hareket kaydeder. `miktar` pozitif verilir, isareti tip belirler.

    isaretli=True ise miktar oldugu gibi yazilir (sayim farki icin).
    """
    bilgi = HAREKET_TIPLERI[tip]
    gercek_miktar = miktar if isaretli else abs(miktar) * bilgi["yon"]

    return db.calistir(
        """INSERT INTO hareketler
           (tarih, tip, varyant_id, depo_id, miktar, birim_fiyat, belge_no,
            tedarikci_id, proje_id, sayim_id, transfer_grup, kullanici_id,
            aciklama, olusturma)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (tarih or db.bugun(), tip, varyant_id, depo_id, gercek_miktar,
         birim_fiyat, belge_no, tedarikci_id, proje_id, sayim_id,
         transfer_grup, kullanici["id"] if kullanici else None,
         aciklama, db.simdi()))


def stok_yeterli_mi(varyant_id, depo_id, miktar):
    """Cikis hareketinde deponun o kalemi karsilayip karsilamadigini soyler."""
    mevcut = db.varyant_stok(varyant_id, depo_id)
    return mevcut >= miktar, mevcut


# ------------------------------------------------------------------ giris ekrani
@bp.route("/yeni", methods=("GET", "POST"))
@giris_gerekli
def yeni():
    tip = request.values.get("tip", "giris")
    if tip not in ELLE_GIRILEN_TIPLER:
        tip = "giris"
    bilgi = HAREKET_TIPLERI[tip]

    if not rol_yeterli(g.kullanici["rol"], bilgi["rol"]):
        flash(f"'{bilgi['ad']}' girişi için yetkiniz yok.", "hata")
        return redirect(url_for("panel.anasayfa"))

    # Ustalar yalnizca uretim sarfi girebilir
    izinli_tipler = [t for t in ELLE_GIRILEN_TIPLER
                     if rol_yeterli(g.kullanici["rol"], HAREKET_TIPLERI[t]["rol"])]

    if request.method == "POST":
        sonuc = _coklu_kaydet(tip)
        if sonuc["ok"]:
            flash(f"{sonuc['adet']} kalem {bilgi['ad'].lower()} kaydedildi.", "basari")
            return redirect(url_for("hareketler.yeni", tip=tip))
        for mesaj in sonuc["hatalar"]:
            flash(mesaj, "hata")

    return render_template(
        "hareket_yeni.html", tip=tip, bilgi=bilgi, izinli_tipler=izinli_tipler,
        depolar=db.depo_listesi(), tedarikciler=db.tedarikci_listesi(),
        projeler=db.sorgu("SELECT * FROM projeler WHERE durum IN ('acik','uretimde')"
                          " ORDER BY kod"),
        bugun=db.bugun())


def _coklu_kaydet(tip):
    """Formdaki tum satirlari tek islemde kaydeder; biri hatalıysa hicbiri yazilmaz."""
    f = request.form
    bilgi = HAREKET_TIPLERI[tip]
    depo_id = f.get("depo_id", type=int)
    tarih = f.get("tarih") or db.bugun()
    belge_no = (f.get("belge_no") or "").strip() or None
    tedarikci_id = f.get("tedarikci_id", type=int) or None
    proje_id = f.get("proje_id", type=int) or None
    genel_aciklama = (f.get("aciklama") or "").strip() or None
    zorla = f.get("eksiye_izin") == "1" and g.kullanici["rol"] == "yonetici"

    varyant_idler = f.getlist("varyant_id")
    miktarlar = f.getlist("miktar")
    fiyatlar = f.getlist("birim_fiyat")
    satir_aciklamalari = f.getlist("satir_aciklama")

    hatalar = []
    if not depo_id:
        hatalar.append("Depo seçmelisiniz.")

    satirlar = []
    for i, vid in enumerate(varyant_idler):
        if not vid:
            continue
        try:
            varyant_id = int(vid)
            miktar = float((miktarlar[i] or "0").replace(",", "."))
        except (ValueError, IndexError):
            hatalar.append(f"{i + 1}. satırda geçersiz miktar.")
            continue
        if miktar <= 0:
            hatalar.append(f"{i + 1}. satırda miktar sıfırdan büyük olmalı.")
            continue

        v = db.varyant_detay(varyant_id)
        if v is None:
            hatalar.append(f"{i + 1}. satırdaki ürün bulunamadı.")
            continue

        if bilgi["yon"] < 0 and not zorla:
            yeterli, mevcut = stok_yeterli_mi(varyant_id, depo_id, miktar)
            if not yeterli:
                hatalar.append(
                    f"{v['urun_ad']} ({v['sku']}): depoda {mevcut:g} {v['ana_birim']} var, "
                    f"{miktar:g} çıkış yapılamaz.")
                continue

        try:
            fiyat = float((fiyatlar[i] or "").replace(",", ".")) if fiyatlar[i] else None
        except (ValueError, IndexError):
            fiyat = None

        satirlar.append({
            "varyant_id": varyant_id, "miktar": miktar, "fiyat": fiyat,
            "aciklama": (satir_aciklamalari[i].strip()
                         if i < len(satir_aciklamalari) and satir_aciklamalari[i]
                         else genel_aciklama),
            "v": v,
        })

    if not satirlar and not hatalar:
        hatalar.append("En az bir ürün satırı eklemelisiniz.")
    if hatalar:
        return {"ok": False, "adet": 0, "hatalar": hatalar}

    for s in satirlar:
        hareket_ekle(
            tip, s["varyant_id"], depo_id, s["miktar"], g.kullanici, tarih=tarih,
            belge_no=belge_no, tedarikci_id=tedarikci_id, proje_id=proje_id,
            aciklama=s["aciklama"], birim_fiyat=s["fiyat"])
        # Mal girisinde son alis fiyati varyanta islensin
        if tip == "giris" and s["fiyat"]:
            db.calistir("UPDATE varyantlar SET birim_fiyat = ? WHERE id = ?",
                        (s["fiyat"], s["varyant_id"]))

    db.log_yaz(g.kullanici, f"hareket_{tip}",
               f"{len(satirlar)} kalem, belge: {belge_no or '-'}")
    return {"ok": True, "adet": len(satirlar), "hatalar": []}


# --------------------------------------------------------------------- transfer
@bp.route("/transfer", methods=("GET", "POST"))
@rol_gerekli("depo")
def transfer():
    depolar = db.depo_listesi()

    if request.method == "POST":
        f = request.form
        kaynak = f.get("kaynak_depo", type=int)
        hedef = f.get("hedef_depo", type=int)
        tarih = f.get("tarih") or db.bugun()
        aciklama = (f.get("aciklama") or "").strip() or None

        hatalar = []
        if not kaynak or not hedef:
            hatalar.append("Kaynak ve hedef depo seçmelisiniz.")
        elif kaynak == hedef:
            hatalar.append("Kaynak ve hedef depo aynı olamaz.")

        satirlar = []
        for i, vid in enumerate(f.getlist("varyant_id")):
            if not vid:
                continue
            try:
                varyant_id = int(vid)
                miktar = float((f.getlist("miktar")[i] or "0").replace(",", "."))
            except (ValueError, IndexError):
                hatalar.append(f"{i + 1}. satırda geçersiz miktar.")
                continue
            if miktar <= 0:
                hatalar.append(f"{i + 1}. satırda miktar sıfırdan büyük olmalı.")
                continue
            v = db.varyant_detay(varyant_id)
            if kaynak:
                yeterli, mevcut = stok_yeterli_mi(varyant_id, kaynak, miktar)
                if not yeterli:
                    hatalar.append(
                        f"{v['urun_ad']} ({v['sku']}): kaynak depoda {mevcut:g} "
                        f"{v['ana_birim']} var, {miktar:g} transfer edilemez.")
                    continue
            satirlar.append((varyant_id, miktar))

        if not satirlar and not hatalar:
            hatalar.append("En az bir ürün satırı eklemelisiniz.")

        if hatalar:
            for h in hatalar:
                flash(h, "hata")
        else:
            grup = uuid.uuid4().hex[:12]
            for varyant_id, miktar in satirlar:
                hareket_ekle("transfer_cikis", varyant_id, kaynak, miktar,
                             g.kullanici, tarih=tarih, aciklama=aciklama,
                             transfer_grup=grup)
                hareket_ekle("transfer_giris", varyant_id, hedef, miktar,
                             g.kullanici, tarih=tarih, aciklama=aciklama,
                             transfer_grup=grup)
            db.log_yaz(g.kullanici, "transfer", f"{len(satirlar)} kalem, grup {grup}")
            flash(f"{len(satirlar)} kalem transfer edildi.", "basari")
            return redirect(url_for("hareketler.transfer"))

    return render_template("transfer.html", depolar=depolar, bugun=db.bugun())


# ---------------------------------------------------------------------- dokum
@bp.route("/")
@giris_gerekli
def liste():
    tip = request.args.get("tip") or ""
    depo_id = request.args.get("depo", type=int)
    proje_id = request.args.get("proje", type=int)
    kullanici_id = request.args.get("kullanici", type=int)
    bas = request.args.get("bas") or ""
    bit = request.args.get("bit") or ""
    arama = (request.args.get("q") or "").strip()
    sayfa = max(1, request.args.get("sayfa", 1, type=int))
    boyut = 50

    kosullar, params = ["1=1"], []
    if tip:
        kosullar.append("h.tip = ?")
        params.append(tip)
    if depo_id:
        kosullar.append("h.depo_id = ?")
        params.append(depo_id)
    if proje_id:
        kosullar.append("h.proje_id = ?")
        params.append(proje_id)
    if kullanici_id:
        kosullar.append("h.kullanici_id = ?")
        params.append(kullanici_id)
    if bas:
        kosullar.append("h.tarih >= ?")
        params.append(bas)
    if bit:
        kosullar.append("h.tarih <= ?")
        params.append(bit)
    if arama:
        sutunlar = ["vv.urun_ad", "vv.sku", "h.belge_no", "vv.renk_dekor"]
        kosullar.append(db.arama_kosulu(sutunlar))
        params.extend([f"%{arama}%"] * len(sutunlar))
    nerede = " AND ".join(kosullar)

    toplam = db.tek_deger(
        f"""SELECT COUNT(*) FROM hareketler h
            JOIN v_varyant vv ON vv.varyant_id = h.varyant_id
            WHERE {nerede}""", tuple(params))

    satirlar = db.sorgu(
        f"""SELECT h.*, vv.urun_ad, vv.sku, vv.renk_dekor, vv.olcu, vv.ana_birim,
                   d.ad AS depo_ad, k.ad_soyad AS kullanici_ad,
                   p.kod AS proje_kod, t.ad AS tedarikci_ad
            FROM hareketler h
            JOIN v_varyant vv ON vv.varyant_id = h.varyant_id
            JOIN depolar d    ON d.id = h.depo_id
            LEFT JOIN kullanicilar k ON k.id = h.kullanici_id
            LEFT JOIN projeler     p ON p.id = h.proje_id
            LEFT JOIN tedarikciler t ON t.id = h.tedarikci_id
            WHERE {nerede}
            ORDER BY h.tarih DESC, h.id DESC
            LIMIT ? OFFSET ?""", tuple(params) + (boyut, (sayfa - 1) * boyut))

    return render_template(
        "hareket_liste.html", satirlar=satirlar, toplam=toplam, sayfa=sayfa,
        boyut=boyut, sayfa_sayisi=max(1, -(-toplam // boyut)),
        depolar=db.depo_listesi(),
        projeler=db.sorgu("SELECT * FROM projeler ORDER BY kod"),
        kullanicilar=db.sorgu("SELECT * FROM kullanicilar ORDER BY ad_soyad"),
        secili={"tip": tip, "depo": depo_id, "proje": proje_id,
                "kullanici": kullanici_id, "bas": bas, "bit": bit, "q": arama})


@bp.route("/<int:hareket_id>/iptal", methods=("POST",))
@rol_gerekli("yonetici")
def iptal(hareket_id):
    """Hatali hareketi ters kayitla iptal eder. Orijinal kayit silinmez.

    Transfer iki ayri hareketten olusur; birini iptal edip digerini birakmak
    stogu bozardi. Bu yuzden transferin iki ayagi da birlikte iptal edilir.
    """
    h = db.sorgu("SELECT * FROM hareketler WHERE id = ?", (hareket_id,), tek=True)
    if h is None:
        abort(404)
    if h["tip"] in ("sayim", "duzeltme"):
        flash("Sayım düzeltmeleri ve iptal kayıtları geri alınamaz; "
              "gerekiyorsa yeni bir sayım yapın.", "hata")
        return redirect(request.referrer or url_for("hareketler.liste"))

    if h["transfer_grup"]:
        iptal_edilecek = db.sorgu(
            "SELECT * FROM hareketler WHERE transfer_grup = ? AND varyant_id = ?"
            " AND tip IN ('transfer_cikis','transfer_giris')",
            (h["transfer_grup"], h["varyant_id"]))
    else:
        iptal_edilecek = [h]

    # Daha once iptal edilmis mi?
    for kayit in iptal_edilecek:
        onceki = db.sorgu(
            "SELECT 1 FROM hareketler WHERE tip='duzeltme' AND aciklama LIKE ?",
            (f"#{kayit['id']} %",), tek=True)
        if onceki:
            flash(f"#{kayit['id']} numaralı hareket zaten iptal edilmiş.", "hata")
            return redirect(request.referrer or url_for("hareketler.liste"))

    # Stogu eksiye dusurecek bir iptal, verinin tutarsiz oldugunun isaretidir
    for kayit in iptal_edilecek:
        if kayit["miktar"] > 0:
            mevcut = db.varyant_stok(kayit["varyant_id"], kayit["depo_id"])
            if mevcut < kayit["miktar"]:
                v = db.varyant_detay(kayit["varyant_id"])
                flash(
                    f"Bu hareket iptal edilemez: {v['urun_ad']} ({v['sku']}) için "
                    f"depoda {mevcut:g} {v['ana_birim']} var, iptal {kayit['miktar']:g} "
                    f"düşürecekti. Mal çıkışı yapılmış görünüyor — düzeltmeyi sayımla "
                    f"yapın.", "hata")
                return redirect(request.referrer or url_for("hareketler.liste"))

    for kayit in iptal_edilecek:
        hareket_ekle(
            "duzeltme", kayit["varyant_id"], kayit["depo_id"], -kayit["miktar"],
            g.kullanici, tarih=db.bugun(), isaretli=True, belge_no=kayit["belge_no"],
            proje_id=kayit["proje_id"],
            aciklama=f"#{kayit['id']} numaralı "
                     f"{HAREKET_TIPLERI[kayit['tip']]['ad'].lower()} kaydının iptali")

    db.log_yaz(g.kullanici, "hareket_iptal",
               f"#{hareket_id} ve bağlı {len(iptal_edilecek) - 1} kayıt iptal edildi")
    if len(iptal_edilecek) > 1:
        flash(f"Transferin her iki ayağı da iptal edildi ({len(iptal_edilecek)} kayıt).",
              "basari")
    else:
        flash(f"#{hareket_id} numaralı hareket ters kayıtla iptal edildi.", "basari")
    return redirect(request.referrer or url_for("hareketler.liste"))
