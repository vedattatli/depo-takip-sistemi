-- Redecor Depo Takip Sistemi - veritabani semasi
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------- kullanicilar
CREATE TABLE IF NOT EXISTS kullanicilar (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    kullanici_adi TEXT NOT NULL UNIQUE,
    ad_soyad      TEXT NOT NULL,
    sifre_hash    TEXT NOT NULL,
    rol           TEXT NOT NULL DEFAULT 'usta',   -- yonetici | depo | usta
    aktif         INTEGER NOT NULL DEFAULT 1,
    olusturma     TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- ------------------------------------------------------------------ tanimlar
CREATE TABLE IF NOT EXISTS kategoriler (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ad       TEXT NOT NULL UNIQUE,
    aciklama TEXT
);

CREATE TABLE IF NOT EXISTS tedarikciler (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ad         TEXT NOT NULL,
    yetkili    TEXT,
    telefon    TEXT,
    eposta     TEXT,
    adres      TEXT,
    teslim_gun INTEGER NOT NULL DEFAULT 7,   -- ortalama tedarik suresi (gun)
    notlar     TEXT,
    aktif      INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS depolar (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    ad       TEXT NOT NULL UNIQUE,
    adres    TEXT,
    aciklama TEXT,
    aktif    INTEGER NOT NULL DEFAULT 1
);

-- -------------------------------------------------------------------- urunler
-- Bir urun (orn. "PVC Pencere Profili 70mm") birden fazla varyant tasir
-- (renk / dekor / olcu). Stok her zaman varyant seviyesinde tutulur.
CREATE TABLE IF NOT EXISTS urunler (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    kod           TEXT NOT NULL UNIQUE,
    ad            TEXT NOT NULL,
    kategori_id   INTEGER REFERENCES kategoriler(id),
    tedarikci_id  INTEGER REFERENCES tedarikciler(id),
    ana_birim     TEXT NOT NULL DEFAULT 'adet',  -- stok bu birimde tutulur
    ikincil_birim TEXT,                          -- rapor icin cevrim birimi
    birim_katsayi REAL,                          -- 1 ana_birim = katsayi * ikincil_birim
    aciklama      TEXT,
    aktif         INTEGER NOT NULL DEFAULT 1,
    olusturma     TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS varyantlar (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    urun_id     INTEGER NOT NULL REFERENCES urunler(id) ON DELETE CASCADE,
    sku         TEXT NOT NULL UNIQUE,
    renk_dekor  TEXT,
    olcu        TEXT,
    barkod      TEXT,
    min_stok    REAL NOT NULL DEFAULT 0,
    birim_fiyat REAL NOT NULL DEFAULT 0,
    aktif       INTEGER NOT NULL DEFAULT 1
);

-- ------------------------------------------------------------------ projeler
CREATE TABLE IF NOT EXISTS projeler (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kod        TEXT NOT NULL UNIQUE,
    musteri    TEXT NOT NULL,
    telefon    TEXT,
    adres      TEXT,
    tip        TEXT,                              -- mutfak | kapi | pencere | karma
    durum      TEXT NOT NULL DEFAULT 'acik',      -- acik | uretimde | tamamlandi | iptal
    baslangic  TEXT,
    teslim     TEXT,
    notlar     TEXT,
    olusturma  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- -------------------------------------------------------------------- sayimlar
CREATE TABLE IF NOT EXISTS sayimlar (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    depo_id      INTEGER NOT NULL REFERENCES depolar(id),
    tarih        TEXT NOT NULL,
    durum        TEXT NOT NULL DEFAULT 'acik',    -- acik | tamamlandi | iptal
    kullanici_id INTEGER REFERENCES kullanicilar(id),
    notlar       TEXT,
    kapanis      TEXT
);

CREATE TABLE IF NOT EXISTS sayim_satirlari (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    sayim_id       INTEGER NOT NULL REFERENCES sayimlar(id) ON DELETE CASCADE,
    varyant_id     INTEGER NOT NULL REFERENCES varyantlar(id),
    sistem_miktar  REAL NOT NULL DEFAULT 0,
    sayilan_miktar REAL,
    UNIQUE (sayim_id, varyant_id)
);

-- ------------------------------------------------------------------ hareketler
-- Stok hicbir yerde sabit sayi olarak tutulmaz; her zaman bu tablodan
-- toplanarak hesaplanir. Boylece her rakamin arkasinda bir belge/kullanici olur.
-- miktar isaretlidir: giris (+), cikis (-).
CREATE TABLE IF NOT EXISTS hareketler (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tarih         TEXT NOT NULL,
    tip           TEXT NOT NULL,
    varyant_id    INTEGER NOT NULL REFERENCES varyantlar(id),
    depo_id       INTEGER NOT NULL REFERENCES depolar(id),
    miktar        REAL NOT NULL,
    birim_fiyat   REAL,
    belge_no      TEXT,
    tedarikci_id  INTEGER REFERENCES tedarikciler(id),
    proje_id      INTEGER REFERENCES projeler(id),
    sayim_id      INTEGER REFERENCES sayimlar(id),
    transfer_grup TEXT,
    kullanici_id  INTEGER REFERENCES kullanicilar(id),
    aciklama      TEXT,
    olusturma     TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- -------------------------------------------------------------- rezervasyonlar
-- Fiziken depoda duran ama bir projeye ayrilmis mallar.
CREATE TABLE IF NOT EXISTS rezervasyonlar (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    proje_id     INTEGER NOT NULL REFERENCES projeler(id) ON DELETE CASCADE,
    varyant_id   INTEGER NOT NULL REFERENCES varyantlar(id),
    depo_id      INTEGER NOT NULL REFERENCES depolar(id),
    miktar       REAL NOT NULL,
    durum        TEXT NOT NULL DEFAULT 'aktif',   -- aktif | kullanildi | iptal
    kullanici_id INTEGER REFERENCES kullanicilar(id),
    tarih        TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    aciklama     TEXT
);

-- ------------------------------------------------------------------ islem_log
CREATE TABLE IF NOT EXISTS islem_log (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    zaman         TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    kullanici_id  INTEGER,
    kullanici_adi TEXT,
    islem         TEXT NOT NULL,
    detay         TEXT
);

-- ------------------------------------------------------------------- indeksler
CREATE INDEX IF NOT EXISTS ix_hareket_varyant  ON hareketler(varyant_id);
CREATE INDEX IF NOT EXISTS ix_hareket_depo     ON hareketler(depo_id);
CREATE INDEX IF NOT EXISTS ix_hareket_tarih    ON hareketler(tarih);
CREATE INDEX IF NOT EXISTS ix_hareket_proje    ON hareketler(proje_id);
CREATE INDEX IF NOT EXISTS ix_varyant_urun     ON varyantlar(urun_id);
CREATE INDEX IF NOT EXISTS ix_varyant_barkod   ON varyantlar(barkod);
CREATE INDEX IF NOT EXISTS ix_rez_varyant      ON rezervasyonlar(varyant_id);
CREATE INDEX IF NOT EXISTS ix_rez_proje        ON rezervasyonlar(proje_id);

-- ---------------------------------------------------------------- gorunumler
DROP VIEW IF EXISTS v_stok;
CREATE VIEW v_stok AS
SELECT varyant_id, depo_id, ROUND(SUM(miktar), 4) AS miktar
FROM hareketler
GROUP BY varyant_id, depo_id;

DROP VIEW IF EXISTS v_rezerve;
CREATE VIEW v_rezerve AS
SELECT varyant_id, depo_id, ROUND(SUM(miktar), 4) AS miktar
FROM rezervasyonlar
WHERE durum = 'aktif'
GROUP BY varyant_id, depo_id;

DROP VIEW IF EXISTS v_varyant;
CREATE VIEW v_varyant AS
SELECT
    v.id            AS varyant_id,
    v.sku           AS sku,
    v.renk_dekor    AS renk_dekor,
    v.olcu          AS olcu,
    v.barkod        AS barkod,
    v.min_stok      AS min_stok,
    v.birim_fiyat   AS birim_fiyat,
    v.aktif         AS varyant_aktif,
    u.id            AS urun_id,
    u.kod           AS urun_kod,
    u.ad            AS urun_ad,
    u.ana_birim     AS ana_birim,
    u.ikincil_birim AS ikincil_birim,
    u.birim_katsayi AS birim_katsayi,
    u.aktif         AS urun_aktif,
    k.id            AS kategori_id,
    k.ad            AS kategori_ad,
    t.id            AS tedarikci_id,
    t.ad            AS tedarikci_ad,
    t.teslim_gun    AS teslim_gun
FROM varyantlar v
JOIN urunler u       ON u.id = v.urun_id
LEFT JOIN kategoriler  k ON k.id = u.kategori_id
LEFT JOIN tedarikciler t ON t.id = u.tedarikci_id;
