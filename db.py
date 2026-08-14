"""SQLite baglanti yonetimi, sema kurulumu ve ortak stok sorgulari."""

import os
import sqlite3
from datetime import datetime

from flask import current_app, g

PROJE_DIZIN = os.path.dirname(os.path.abspath(__file__))
VERITABANI_YOLU = os.path.join(PROJE_DIZIN, "veri", "depo.db")
SEMA_YOLU = os.path.join(PROJE_DIZIN, "schema.sql")


# ----------------------------------------------------------------- baglanti
# Turkce arama: hem buyuk/kucuk harf hem de aksan farki yok sayilir.
# Depoda kimse "Meşe Sonoma" ararken s ile s harfini ayirt etmeye ugrasmaz;
# "mese" yazinca da bulmali. SQLite'in LIKE'i sadece ASCII harflerde
# buyuk/kucuk esitligi yaptigi icin bu cevrimi kendimiz yapiyoruz.
_ARAMA_CEVRIM = str.maketrans({
    "İ": "i", "I": "i", "ı": "i",
    "Ş": "s", "ş": "s",
    "Ğ": "g", "ğ": "g",
    "Ü": "u", "ü": "u",
    "Ö": "o", "ö": "o",
    "Ç": "c", "ç": "c",
    "Â": "a", "â": "a", "Î": "i", "î": "i", "Û": "u", "û": "u",
})


def ara_norm(metin):
    """Arama icin metni sadelestirir: 'Meşe Sonoma' -> 'mese sonoma'."""
    if metin is None:
        return ""
    return str(metin).translate(_ARAMA_CEVRIM).lower()


def arama_kosulu(sutunlar) -> str:
    """Verilen sutunlar icin aksan/harf duyarsiz LIKE kosulu uretir."""
    return "(" + " OR ".join(
        f"ara_norm({s}) LIKE ara_norm(?)" for s in sutunlar) + ")"


def baglan() -> sqlite3.Connection:
    """Istek basina tek baglanti dondurur."""
    if "db" not in g:
        yol = current_app.config["VERITABANI"]
        os.makedirs(os.path.dirname(yol), exist_ok=True)
        g.db = sqlite3.connect(yol, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.create_function("ara_norm", 1, ara_norm)
    return g.db


def kapat(hata=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def sorgu(sql: str, params=(), tek=False):
    cur = baglan().execute(sql, params)
    satirlar = cur.fetchall()
    cur.close()
    if tek:
        return satirlar[0] if satirlar else None
    return satirlar


def calistir(sql: str, params=()) -> int:
    """INSERT/UPDATE/DELETE calistirir, lastrowid dondurur."""
    db = baglan()
    cur = db.execute(sql, params)
    db.commit()
    yeni_id = cur.lastrowid
    cur.close()
    return yeni_id


def tek_deger(sql: str, params=(), varsayilan=0):
    satir = sorgu(sql, params, tek=True)
    if satir is None or satir[0] is None:
        return varsayilan
    return satir[0]


# ------------------------------------------------------------------- kurulum
def sema_kur(app=None):
    """Sema dosyasini calistirir. Var olan tablolara dokunmaz."""
    yol = app.config["VERITABANI"] if app else current_app.config["VERITABANI"]
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(SEMA_YOLU, "r", encoding="utf-8") as f:
        sema = f.read()
    con = sqlite3.connect(yol)
    con.executescript(sema)
    con.commit()
    con.close()


def uygulamaya_bagla(app):
    app.teardown_appcontext(kapat)


# ------------------------------------------------------------- yardimcilar
def simdi() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def bugun() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def log_yaz(kullanici, islem: str, detay: str = ""):
    """Denetim izi. Kullanici None olabilir (sistem islemi)."""
    calistir(
        "INSERT INTO islem_log (zaman, kullanici_id, kullanici_adi, islem, detay)"
        " VALUES (?,?,?,?,?)",
        (
            simdi(),
            kullanici["id"] if kullanici else None,
            kullanici["kullanici_adi"] if kullanici else "sistem",
            islem,
            detay,
        ),
    )


# ------------------------------------------------------------ stok sorgulari
STOK_SECIM = """
    SELECT
        vv.*,
        COALESCE(s.miktar, 0)  AS stok,
        COALESCE(r.miktar, 0)  AS rezerve,
        COALESCE(s.miktar, 0) - COALESCE(r.miktar, 0) AS kullanilabilir,
        COALESCE(s.miktar, 0) * vv.birim_fiyat        AS stok_degeri
    FROM v_varyant vv
    LEFT JOIN (SELECT varyant_id, SUM(miktar) AS miktar FROM v_stok
               {stok_filtre} GROUP BY varyant_id) s ON s.varyant_id = vv.varyant_id
    LEFT JOIN (SELECT varyant_id, SUM(miktar) AS miktar FROM v_rezerve
               {rez_filtre} GROUP BY varyant_id) r ON r.varyant_id = vv.varyant_id
"""


def stok_listesi(depo_id=None, kategori_id=None, arama=None, sadece_kritik=False,
                 sadece_stokta=False, tedarikci_id=None, siralama="urun"):
    """Varyant bazli stok listesi. depo_id verilmezse tum depolarin toplami."""
    params = []
    if depo_id:
        stok_filtre = "WHERE depo_id = ?"
        rez_filtre = "WHERE depo_id = ?"
        params.extend([depo_id, depo_id])
    else:
        stok_filtre = rez_filtre = ""

    sql = STOK_SECIM.format(stok_filtre=stok_filtre, rez_filtre=rez_filtre)

    kosullar = ["vv.varyant_aktif = 1", "vv.urun_aktif = 1"]
    if kategori_id:
        kosullar.append("vv.kategori_id = ?")
        params.append(kategori_id)
    if tedarikci_id:
        kosullar.append("vv.tedarikci_id = ?")
        params.append(tedarikci_id)
    if arama:
        sutunlar = ["vv.urun_ad", "vv.urun_kod", "vv.sku", "vv.renk_dekor",
                    "vv.barkod", "vv.olcu"]
        kosullar.append(arama_kosulu(sutunlar))
        params.extend([f"%{arama}%"] * len(sutunlar))
    if sadece_kritik:
        kosullar.append("(COALESCE(s.miktar,0) - COALESCE(r.miktar,0)) <= vv.min_stok")
    if sadece_stokta:
        kosullar.append("COALESCE(s.miktar,0) > 0")

    sql += " WHERE " + " AND ".join(kosullar)

    siralamalar = {
        "urun": "vv.urun_ad, vv.renk_dekor",
        "stok_az": "kullanilabilir ASC",
        "stok_cok": "kullanilabilir DESC",
        "deger": "stok_degeri DESC",
        "kategori": "vv.kategori_ad, vv.urun_ad",
    }
    sql += " ORDER BY " + siralamalar.get(siralama, siralamalar["urun"])
    return sorgu(sql, tuple(params))


def varyant_stok(varyant_id: int, depo_id=None) -> float:
    if depo_id:
        return tek_deger(
            "SELECT COALESCE(SUM(miktar),0) FROM v_stok WHERE varyant_id=? AND depo_id=?",
            (varyant_id, depo_id), 0.0)
    return tek_deger(
        "SELECT COALESCE(SUM(miktar),0) FROM v_stok WHERE varyant_id=?",
        (varyant_id,), 0.0)


def varyant_rezerve(varyant_id: int, depo_id=None) -> float:
    if depo_id:
        return tek_deger(
            "SELECT COALESCE(SUM(miktar),0) FROM v_rezerve WHERE varyant_id=? AND depo_id=?",
            (varyant_id, depo_id), 0.0)
    return tek_deger(
        "SELECT COALESCE(SUM(miktar),0) FROM v_rezerve WHERE varyant_id=?",
        (varyant_id,), 0.0)


def varyant_detay(varyant_id: int):
    return sorgu("SELECT * FROM v_varyant WHERE varyant_id = ?", (varyant_id,), tek=True)


def depo_listesi(sadece_aktif=True):
    sql = "SELECT * FROM depolar"
    if sadece_aktif:
        sql += " WHERE aktif = 1"
    return sorgu(sql + " ORDER BY ad")


def kategori_listesi():
    return sorgu("SELECT * FROM kategoriler ORDER BY ad")


def tedarikci_listesi(sadece_aktif=True):
    sql = "SELECT * FROM tedarikciler"
    if sadece_aktif:
        sql += " WHERE aktif = 1"
    return sorgu(sql + " ORDER BY ad")
