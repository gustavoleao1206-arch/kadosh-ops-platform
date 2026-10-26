"""Limites de tentativas de login. São três travas, e as três precisam existir juntas:

- Por IP: slowapi (5/min) na rota. O IP é extraído por `client_ip`: atrás do proxy do Render usamos o
  ÚLTIMO valor de X-Forwarded-For (o que o proxy acrescentou), nunca o primeiro (forjável pelo cliente).
- Por ORIGEM, isto é, pelo par (e-mail, IP): atraso progressivo após N falhas (1 s, 2 s, 4 s… até
  15 min). É o freio da força bruta, e só freia quem errou: o atacante tranca a si mesmo, não o dono.
- Por CONTA, somando todas as origens: um teto bem mais alto, que só vale para origem que a conta
  NUNCA usou para entrar. Fecha a força bruta distribuída (cada IP com poucas tentativas) sem deixar
  um terceiro trancar o dono, que entra de um endereço conhecido.

Por que não basta contar por e-mail: a versão anterior fazia isso, e o contador era de todo mundo.
Um único IP que errasse a senha do dono assim que o bloqueio vencesse (~15 tentativas/hora, bem
abaixo dos 5/min) mantinha o dono bloqueado indefinidamente, até com a senha certa. O teto por conta
desta versão foi escolhido acima do que uma origem sozinha consegue acumular numa janela (17 falhas
com os valores padrão), então esse ataque não chega nem a acioná-lo.

Tudo em memória: uma instância só, não precisa de Redis. O estado se perde num redeploy, o que só
favorece o dono (zera também o contador do atacante).
"""

import ipaddress
import math
import threading
import time
from collections import deque
from collections.abc import Callable, Hashable

from fastapi import Request
from slowapi import Limiter

from app.core.config import get_settings


def client_ip(request: Request) -> str:
    settings = get_settings()
    if settings.TRUST_PROXY_HEADERS:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[-1].strip()
    return request.client.host if request.client else "127.0.0.1"


limiter = Limiter(key_func=client_ip)


def origem(ip: str | None) -> str:
    """Chave da ORIGEM de uma tentativa: o IPv4 inteiro, ou o prefixo /64 do IPv6.

    Um aparelho IPv6 controla o /64 inteiro e troca de endereço dentro dele à vontade (é o que as
    extensões de privacidade fazem sozinhas, várias vezes por dia). Contar por endereço deixaria o
    atacante zerar o próprio contador trocando o final do IP, e faria o dono perder o status de
    "origem conhecida" a cada troca.
    """
    if not ip:
        return "?"
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip  # não é IP (o TestClient manda "testclient"): usa o texto como veio
    if isinstance(addr, ipaddress.IPv6Address):
        if addr.ipv4_mapped:
            return str(addr.ipv4_mapped)
        return str(ipaddress.ip_network(f"{addr}/64", strict=False))
    return str(addr)


class AttemptLimiter:
    """Atraso progressivo em memória, por chave.

    Até `free_attempts` falhas dentro da janela, nada. Dali em diante, cada nova tentativa espera
    1 s, 2 s, 4 s… (até `max_block_seconds`), contados da ÚLTIMA falha daquela chave.
    """

    SWEEP_EVERY_SECONDS = 60

    def __init__(
        self,
        free_attempts: int,
        max_block_seconds: int,
        window_seconds: int = 3600,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.free_attempts = free_attempts
        self.max_block_seconds = max_block_seconds
        self.window_seconds = window_seconds
        self.clock = clock
        self._attempts: dict[Hashable, deque[float]] = {}
        self._next_sweep = 0.0
        self._lock = threading.Lock()

    def _prune(self, key: Hashable, now: float) -> deque[float] | None:
        q = self._attempts.get(key)
        if not q:
            return None
        while q and now - q[0] > self.window_seconds:
            q.popleft()
        if not q:
            del self._attempts[key]
            return None
        return q

    def _sweep(self, now: float) -> None:
        """Descarta chaves cuja falha mais recente já saiu da janela.

        Sem isto, toda chave consultada uma única vez (um e-mail inventado, um IP de passagem)
        ficaria no dicionário para sempre: memória crescendo devagar até o próximo deploy.
        """
        if now < self._next_sweep:
            return
        self._next_sweep = now + self.SWEEP_EVERY_SECONDS
        for key in [k for k, q in self._attempts.items() if now - q[-1] > self.window_seconds]:
            del self._attempts[key]

    def failures(self, key: Hashable) -> int:
        """Falhas desta chave dentro da janela."""
        with self._lock:
            q = self._prune(key, self.clock())
            return len(q) if q else 0

    def blocked_for(self, key: Hashable) -> int:
        """Segundos restantes de bloqueio para esta chave (0 = liberado)."""
        now = self.clock()
        with self._lock:
            q = self._prune(key, now)
            if not q:
                return 0
            n = len(q)
            if n < self.free_attempts:
                return 0
            delay = min(2 ** (n - self.free_attempts), self.max_block_seconds)
            remaining = delay - (now - q[-1])
            return max(0, math.ceil(remaining))

    def register_failure(self, key: Hashable) -> None:
        now = self.clock()
        with self._lock:
            self._sweep(now)
            self._attempts.setdefault(key, deque()).append(now)

    def clear(self, key: Hashable) -> None:
        with self._lock:
            self._attempts.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._attempts.clear()
            self._next_sweep = 0.0


class LoginThrottle:
    """As duas travas do login que olham o e-mail (a terceira, por IP, é o slowapi na rota)."""

    def __init__(self, *, per_source: AttemptLimiter, per_account: AttemptLimiter) -> None:
        self.per_source = per_source
        self.per_account = per_account

    @staticmethod
    def _source_key(email: str, ip: str | None) -> tuple[str, str]:
        return email, origem(ip)

    def source_wait(self, email: str, ip: str | None) -> int:
        """Espera imposta a ESTA origem para este e-mail. Vale sempre, inclusive para o dono."""
        return self.per_source.blocked_for(self._source_key(email, ip))

    def account_wait(self, email: str) -> int:
        """Espera da conta inteira. Quem chama decide se a origem é conhecida e, portanto, isenta."""
        return self.per_account.blocked_for(email)

    def register_failure(self, email: str, ip: str | None) -> None:
        self.per_source.register_failure(self._source_key(email, ip))
        self.per_account.register_failure(email)

    def clear_source(self, email: str, ip: str | None) -> None:
        """Depois de um login certo, zera SÓ a origem que acertou.

        O contador da conta não é zerado: ele soma as falhas de terceiros, e um login do dono no meio
        de um ataque distribuído não pode devolver ao atacante a cota inteira. Ele envelhece sozinho
        com a janela — e o dono, agora numa origem conhecida, não depende dele.
        """
        self.per_source.clear(self._source_key(email, ip))

    def reset(self) -> None:
        self.per_source.reset()
        self.per_account.reset()


_s = get_settings()
login_throttle = LoginThrottle(
    per_source=AttemptLimiter(
        free_attempts=_s.LOGIN_FREE_ATTEMPTS_PER_SOURCE, max_block_seconds=_s.LOGIN_MAX_BLOCK_SECONDS
    ),
    per_account=AttemptLimiter(
        free_attempts=_s.LOGIN_FREE_FAILURES_PER_ACCOUNT, max_block_seconds=_s.LOGIN_MAX_BLOCK_SECONDS
    ),
)
