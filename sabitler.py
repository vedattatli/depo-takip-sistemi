"""Uygulama genelinde kullanilan sabitler: roller, hareket tipleri, birimler."""

UYGULAMA_ADI = "Redecor Depo"

# --------------------------------------------------------------------- roller
# Sirali: yukaridakiler asagidakilerin tum yetkilerini kapsar.
ROLLER = {
    "yonetici": "Yönetici",
    "depo": "Depo Sorumlusu",
    "usta": "Usta / Üretim",
}

ROL_SIRA = ["usta", "depo", "yonetici"]


def rol_yeterli(kullanici_rol: str, gereken_rol: str) -> bool:
    """kullanici_rol, gereken_rol seviyesine esit veya ustunde mi?"""
    try:
        return ROL_SIRA.index(kullanici_rol) >= ROL_SIRA.index(gereken_rol)
    except ValueError:
        return False


# ------------------------------------------------------------- hareket tipleri
# yon: +1 stogu artirir, -1 azaltir
# rol: bu hareketi girebilmek icin gereken en dusuk rol
HAREKET_TIPLERI = {
    "giris": {
        "ad": "Mal Girişi",
        "yon": +1,
        "rol": "depo",
        "aciklama": "Tedarikçiden gelen mal, irsaliye ile giriş",
        "renk": "yesil",
    },
    "sarf": {
        "ad": "Üretim Sarfı",
        "yon": -1,
        "rol": "usta",
        "aciklama": "Atölyede üretimde kullanılan malzeme",
        "renk": "turuncu",
    },
    "sevk": {
        "ad": "Sevkiyat",
        "yon": -1,
        "rol": "depo",
        "aciklama": "Montaja / müşteriye çıkan mal",
        "renk": "mavi",
    },
    "fire": {
        "ad": "Fire / Zayi",
        "yon": -1,
        "rol": "depo",
        "aciklama": "Kesim artığı, kırık, hasarlı, kayıp",
        "renk": "kirmizi",
    },
    "iade_giris": {
        "ad": "Müşteri İadesi",
        "yon": +1,
        "rol": "depo",
        "aciklama": "Sahadan geri dönen sağlam mal",
        "renk": "yesil",
    },
    "iade_cikis": {
        "ad": "Tedarikçiye İade",
        "yon": -1,
        "rol": "depo",
        "aciklama": "Hatalı mal tedarikçiye geri gönderildi",
        "renk": "kirmizi",
    },
    "transfer_cikis": {
        "ad": "Transfer Çıkışı",
        "yon": -1,
        "rol": "depo",
        "aciklama": "Başka depoya gönderim",
        "renk": "gri",
    },
    "transfer_giris": {
        "ad": "Transfer Girişi",
        "yon": +1,
        "rol": "depo",
        "aciklama": "Başka depodan gelen",
        "renk": "gri",
    },
    "sayim": {
        "ad": "Sayım Düzeltmesi",
        "yon": 0,  # isaret sayim farkina gore belirlenir
        "rol": "depo",
        "aciklama": "Fiziksel sayım sonrası fark düzeltmesi",
        "renk": "mor",
    },
    "duzeltme": {
        "ad": "Hareket İptali",
        "yon": 0,  # isaret, iptal edilen hareketin tersidir
        "rol": "yonetici",
        "aciklama": "Yanlış girilmiş bir hareketin ters kayıtla iptali",
        "renk": "mor",
    },
}

# Hareket ekranindan elle secilebilen tipler (transfer ve sayim kendi ekranindan)
ELLE_GIRILEN_TIPLER = [
    "giris", "sarf", "sevk", "fire", "iade_giris", "iade_cikis",
]

# --------------------------------------------------------------------- birimler
BIRIMLER = [
    ("adet", "Adet"),
    ("m2", "m² (metrekare)"),
    ("mtul", "mtül (metretül)"),
    ("metre", "Metre"),
    ("boy", "Boy (çubuk)"),
    ("takim", "Takım"),
    ("kutu", "Kutu"),
    ("paket", "Paket"),
    ("kg", "Kilogram"),
    ("litre", "Litre"),
]

BIRIM_ADLARI = dict(BIRIMLER)

# ---------------------------------------------------------------- proje tipleri
PROJE_TIPLERI = [
    ("mutfak", "Mutfak"),
    ("kapi", "Kapı"),
    ("pencere", "Pencere"),
    ("dolap", "Dolap / Gardırop"),
    ("karma", "Karma"),
]

PROJE_DURUMLARI = [
    ("acik", "Açık"),
    ("uretimde", "Üretimde"),
    ("tamamlandi", "Tamamlandı"),
    ("iptal", "İptal"),
]

# ----------------------------------------- ilk kurulumda olusturulan kategoriler
VARSAYILAN_KATEGORILER = [
    ("Panel / Levha", "MDF, sunta, lamine, akrilik levhalar"),
    ("Mutfak Kapağı", "Lake, PVC membran, akrilik, laminat kapaklar"),
    ("Tezgah", "Suni mermer, laminat, granit tezgahlar"),
    ("PVC Profil", "Pencere ve kapı PVC profilleri"),
    ("Alüminyum Profil", "Alüminyum doğrama profilleri"),
    ("Cam", "Isıcam üniteleri, tek cam, ayna"),
    ("Hırdavat", "Menteşe, ray, kulp, kilit, ispanyolet"),
    ("Kenar Bandı", "PVC ve ABS kenar bantları"),
    ("Kimyasal", "Tutkal, silikon, poliüretan köpük, temizleyici"),
    ("Aksesuar", "Çekmece sistemi, sepet, aydınlatma, çöp kovası"),
]

VARSAYILAN_DEPOLAR = [
    ("Ana Depo", "Merkez depo"),
    ("Atölye", "Üretim alanı ara stoğu"),
]
