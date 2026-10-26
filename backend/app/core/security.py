"""Senhas (Argon2id) e tokens de sessão opacos.

- Senha: Argon2id com o perfil recomendado pela OWASP (19 MiB, 2 iterações, 1 thread) — cabe na
  instância de 512 MB do Render mesmo com alguns logins simultâneos.
- Sessão: token aleatório de 256 bits. O banco guarda apenas o SHA-256 do token; o valor bruto só
  existe no cookie HttpOnly (web) ou no armazenamento do app Android.
  (No Android é SharedPreferences, não Keystore — o manifesto desliga o backup para que
  esse arquivo não saia do aparelho. Ver mobile/android/app/src/main/AndroidManifest.xml.)
"""

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher(memory_cost=19_456, time_cost=2, parallelism=1)

# Hash fixo usado para igualar o tempo de resposta quando o e-mail não existe
# (evita descobrir quais e-mails estão cadastrados medindo o tempo do login).
_DUMMY_HASH = _hasher.hash("kadosh-dummy-password-for-timing")

MIN_PASSWORD_LENGTH = 10


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Confere a senha. Com hash ausente, verifica contra um hash fixo para manter o tempo constante."""
    try:
        _hasher.verify(password_hash or _DUMMY_HASH, password)
        return password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def generate_session_token() -> tuple[str, str]:
    """Devolve (token_bruto, hash). Só o hash vai para o banco."""
    raw = secrets.token_urlsafe(32)  # 256 bits
    return raw, hash_session_token(raw)


def hash_session_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
