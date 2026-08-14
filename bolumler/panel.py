"""Ana panel (dashboard) - deponun tek bakista durumu."""

from datetime import datetime, timedelta

from flask import Blueprint, render_template, request

import db
from auth import giris_gerekli

bp = Blueprint("panel", __name__)


@bp.route("/panel")
@giris_gerekli
def anasayfa():
    depo_id = request.args.get("depo", type=int)
    depolar = db.depo_listesi()

    kritikler = db.stok_listesi(depo_id=depo_id, sadece_kritik=True, siralama="stok_az")

    ay_basi = datetime.now().strftime("%Y-%m-01")
    otuz_gun_once = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    depo_kosul = " AND depo_id = ?" if depo_id else ""
    depo_param = (depo_id,) if depo_id else ()

    def ay_toplam(tipler):
        yer = ",".join("?" * len(tipler))
        return db.tek_deger(
            f"SELECT COALESCE(SUM(ABS(miktar)),0) FROM hareketler"
            f" WHERE tip IN ({yer}) AND tarih >= ?{depo_kosul}",
            tuple(tipler) + (ay_basi,) + depo_param, 0.0)

    ozet = {
        "varyant_sayisi": db.tek_deger(
            "SELECT COUNT(*) FROM v_varyant WHERE varyant_aktif=1 AND urun_aktif=1"),
        "urun_sayisi": db.tek_deger("SELECT COUNT(*) FROM urunler WHERE aktif=1"),
        "kritik_sayisi": len(kritikler),
        "stok_degeri": _stok_degeri(depo_id),
        "ay_giris": ay_toplam(["giris", "iade_giris"]),
        "ay_cikis": ay_toplam(["sarf", "sevk"]),
        "ay_fire": ay_toplam(["fire"]),
        "acik_proje": db.tek_deger(
            "SELECT COUNT(*) FROM projeler WHERE durum IN ('acik','uretimde')"),
    }

    son_hareketler = db.sorgu(
        """SELECT h.*, vv.urun_ad, vv.sku, vv.renk_dekor, vv.ana_birim,
                  d.ad AS depo_ad, k.ad_soyad AS kullanici_ad, p.kod AS proje_kod
           FROM hareketler h
           JOIN v_varyant vv ON vv.varyant_id = h.varyant_id
           JOIN depolar d    ON d.id = h.depo_id
           LEFT JOIN kullanicilar k ON k.id = h.kullanici_id
           LEFT JOIN projeler p     ON p.id = h.proje_id
           WHERE 1=1 """ + (" AND h.depo_id = ?" if depo_id else "") +
        " ORDER BY h.tarih DESC, h.id DESC LIMIT 12", depo_param)

    projeler = db.sorgu(
        """SELECT p.*,
                  (SELECT COUNT(*) FROM rezervasyonlar r
                    WHERE r.proje_id = p.id AND r.durum='aktif') AS rezerv_sayisi
           FROM projeler p
           WHERE p.durum IN ('acik','uretimde')
           ORDER BY IFNULL(p.teslim,'9999') LIMIT 8""")

    # Son 30 gunun fire orani - bu sektorde takip edilmesi gereken temel gosterge
    fire = db.tek_deger(
        "SELECT COALESCE(SUM(ABS(miktar)),0) FROM hareketler"
        " WHERE tip='fire' AND tarih >= ?" + depo_kosul,
        (otuz_gun_once,) + depo_param, 0.0)
    tuketim = db.tek_deger(
        "SELECT COALESCE(SUM(ABS(miktar)),0) FROM hareketler"
        " WHERE tip IN ('sarf','sevk','fire') AND tarih >= ?" + depo_kosul,
        (otuz_gun_once,) + depo_param, 0.0)
    ozet["fire_orani"] = (fire / tuketim * 100) if tuketim else 0

    return render_template(
        "panel.html", ozet=ozet, kritikler=kritikler[:10],
        kritik_toplam=len(kritikler), son_hareketler=son_hareketler,
        projeler=projeler, depolar=depolar, secili_depo=depo_id)


def _stok_degeri(depo_id=None):
    if depo_id:
        return db.tek_deger(
            """SELECT COALESCE(SUM(s.miktar * v.birim_fiyat), 0)
               FROM v_stok s JOIN varyantlar v ON v.id = s.varyant_id
               WHERE s.depo_id = ?""", (depo_id,), 0.0)
    return db.tek_deger(
        """SELECT COALESCE(SUM(s.miktar * v.birim_fiyat), 0)
           FROM v_stok s JOIN varyantlar v ON v.id = s.varyant_id""", (), 0.0)
