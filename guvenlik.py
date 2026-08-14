"""Sifre hashleme.

Not: macOS ile gelen Python 3.9, OpenSSL'in scrypt destegi olmadan derlenmis
oluyor; werkzeug'un varsayilan yontemi bu yuzden calismiyor. pbkdf2-sha256
her Python surumunde mevcut ve bu is icin fazlasiyla guvenli.
"""

from werkzeug.security import check_password_hash, generate_password_hash

YONTEM = "pbkdf2:sha256"


def sifre_hashle(sifre: str) -> str:
    return generate_password_hash(sifre, method=YONTEM)


def sifre_dogrula(hash_degeri: str, sifre: str) -> bool:
    try:
        return check_password_hash(hash_degeri, sifre)
    except (ValueError, TypeError):
        return False
