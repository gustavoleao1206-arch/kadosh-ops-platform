"""Bloqueio de login: o atacante tranca a si mesmo, nunca o dono — e a força bruta continua fechada.

A versão anterior contava as falhas só por e-mail, somando todo mundo. Um único IP errando a senha
do dono assim que o bloqueio vencia (~15 tentativas/hora, abaixo do limite de 5/min por IP) mantinha
a conta bloqueada indefinidamente, até para a senha certa vinda de qualquer lugar.

Os testes provam as duas metades, porque uma sem a outra é fácil de "consertar":
- negação de serviço: um IP insistente não impede o dono de entrar, nem de um endereço novo;
- força bruta: uma origem só, ou muitas origens somadas, continuam barradas ANTES de a senha ser
  testada — inclusive quando a senha enviada é a certa.

O relógio do limitador é falso (`relogio`): horas de ataque rodam em segundos e sem `sleep`.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.limiter import AttemptLimiter, login_throttle, origem
from app.main import app
from app.models import AuthLog
from tests.conftest import ADMIN_EMAIL, ADMIN_PASS, STAFF_EMAIL, STAFF_PASS

ERRADA = "senha-errada-123"
ATACANTE = "203.0.113.66"
CASA = "198.51.100.10"  # de onde o dono costuma entrar


class Relogio:
    def __init__(self) -> None:
        self.t = 1_000_000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def relogio(monkeypatch):
    r = Relogio()
    monkeypatch.setattr(login_throttle.per_source, "clock", r)
    monkeypatch.setattr(login_throttle.per_account, "clock", r)
    return r


def _login(c: TestClient, senha: str, email: str = ADMIN_EMAIL):
    return c.post("/api/v1/auth/login", json={"email": email, "senha": senha, "client": "android"})


def _de(ip: str) -> TestClient:
    return TestClient(app, client=(ip, 1))


# ------------------------------------------------------------ o ataque da auditoria


def test_um_ip_insistente_nao_tranca_o_dono_nem_ganha_forca_bruta(admin, relogio):
    """Três horas de um atacante ideal: tenta no instante exato em que cada espera vence."""
    s = get_settings()
    falhas, barradas = 0, 0
    with _de(ATACANTE) as atacante:
        fim = relogio.t + 3 * 3600
        while relogio.t < fim:
            r = _login(atacante, ERRADA)
            if r.status_code == 429:
                barradas += 1
                relogio.t += int(r.headers["Retry-After"])
                continue
            assert r.status_code == 401
            falhas += 1
            relogio.t += 1
            # o ponto do conserto: o ataque nunca chega a acionar a trava da CONTA
            assert login_throttle.account_wait(ADMIN_EMAIL) == 0
            assert login_throttle.per_account.failures(ADMIN_EMAIL) < s.LOGIN_FREE_FAILURES_PER_ACCOUNT

        # força bruta continua contida: ~13 senhas testadas por hora, não 300 (5/min)
        assert barradas > 0
        assert falhas <= 17 * 3
        # e a origem do atacante não testa senha nem quando acerta: logo após uma falha, está barrada
        assert _login(atacante, ERRADA).status_code in (401, 429)
        r = _login(atacante, ADMIN_PASS)
        assert r.status_code == 429 and r.headers["Retry-After"]

    # o dono entra no meio do ataque — de casa e também de um endereço que a conta NUNCA usou
    with _de(CASA) as casa:
        assert _login(casa, ADMIN_PASS).status_code == 200
    with _de("192.0.2.200") as hotel:
        assert _login(hotel, ADMIN_PASS).status_code == 200


def test_trava_por_origem_e_so_de_quem_errou(admin):
    """Cinco erros de um IP barram aquele IP — e só ele. O mesmo e-mail, de outro lugar, entra."""
    with _de(ATACANTE) as atacante, _de("192.0.2.7") as outro:
        for _ in range(5):
            assert _login(atacante, ERRADA).status_code == 401
        r = _login(atacante, ADMIN_PASS)
        assert r.status_code == 429 and "e-mail" in r.json()["detail"] and r.headers["Retry-After"]
        assert _login(outro, ADMIN_PASS).status_code == 200


# ------------------------------------------------------------ força bruta distribuída


def test_muitos_ips_somados_acionam_a_trava_da_conta_sem_trancar_o_dono(admin, relogio):
    s = get_settings()
    with _de(CASA) as casa:
        assert _login(casa, ADMIN_PASS).status_code == 200  # a conta já entrou de casa

    # cada IP erra uma vez só: nenhum chega perto da trava por origem
    for i in range(1, s.LOGIN_FREE_FAILURES_PER_ACCOUNT + 1):
        with _de(f"203.0.113.{i}") as c:
            assert _login(c, ERRADA).status_code == 401

    # origem desconhecida: barrada antes de testar a senha — mesmo enviando a certa
    with _de("203.0.113.99") as novo:
        r = _login(novo, ADMIN_PASS)
        assert r.status_code == 429 and r.headers["Retry-After"]
    # a tentativa barrada não conta como falha (não alimenta a própria trava)
    assert login_throttle.per_account.failures(ADMIN_EMAIL) == s.LOGIN_FREE_FAILURES_PER_ACCOUNT

    # o dono, de uma origem conhecida, entra no meio do ataque
    with _de(CASA) as casa:
        assert _login(casa, ADMIN_PASS).status_code == 200

    # o login do dono NÃO devolve ao atacante a cota da conta
    with _de("203.0.113.98") as outro_novo:
        assert _login(outro_novo, ERRADA).status_code == 429

    # e a trava é temporária: vencida a espera, uma origem nova volta a ser atendida
    relogio.t += int(r.headers["Retry-After"])
    with _de("203.0.113.99") as novo:
        assert _login(novo, ADMIN_PASS).status_code == 200


def test_trava_da_conta_cresce_e_tem_teto(admin, relogio):
    s = get_settings()
    for i in range(s.LOGIN_FREE_FAILURES_PER_ACCOUNT + 30):
        login_throttle.register_failure(ADMIN_EMAIL, f"10.1.{i // 250}.{i % 250}")
    espera = login_throttle.account_wait(ADMIN_EMAIL)
    assert espera == s.LOGIN_MAX_BLOCK_SECONDS
    # passada a janela inteira sem novas falhas, a conta volta ao normal sozinha
    relogio.t += 3600 + 1
    assert login_throttle.account_wait(ADMIN_EMAIL) == 0


# ------------------------------------------------------------ o que conta como "origem conhecida"


def _sob_ataque(relogio) -> None:
    s = get_settings()
    for i in range(s.LOGIN_FREE_FAILURES_PER_ACCOUNT):
        login_throttle.register_failure(ADMIN_EMAIL, f"10.9.0.{i}")
    assert login_throttle.account_wait(ADMIN_EMAIL) > 0


def _login_ok(db, user_id: int, ip: str, *, dias_atras: int = 0) -> None:
    db.add(
        AuthLog(
            evento="login_ok",
            user_id=user_id,
            ip=ip,
            created_at=datetime.now(timezone.utc) - timedelta(days=dias_atras),
        )
    )
    db.commit()


def test_origem_conhecida_e_da_propria_conta(admin, staff, db, relogio):
    """Ter entrado como OUTRO usuário daquele IP não torna o IP conhecido desta conta."""
    _login_ok(db, staff.id, "192.0.2.50")
    _sob_ataque(relogio)
    with _de("192.0.2.50") as c:
        assert _login(c, ADMIN_PASS).status_code == 429
        assert _login(c, STAFF_PASS, email=STAFF_EMAIL).status_code == 200  # a conta do sócio não está sob ataque


def test_origem_conhecida_expira(admin, db, relogio):
    dias = get_settings().LOGIN_TRUSTED_SOURCE_DAYS
    _login_ok(db, admin.id, "192.0.2.60", dias_atras=dias + 1)
    _login_ok(db, admin.id, "192.0.2.61", dias_atras=dias - 1)
    _sob_ataque(relogio)
    with _de("192.0.2.60") as velho, _de("192.0.2.61") as recente:
        assert _login(velho, ADMIN_PASS).status_code == 429
        assert _login(recente, ADMIN_PASS).status_code == 200


def test_falha_de_origem_conhecida_ainda_conta(admin, db, relogio):
    """Ser conhecida isenta da trava da CONTA, não da trava por origem: quem rouba o wi-fi de casa
    também não ganha força bruta."""
    _login_ok(db, admin.id, CASA)
    with _de(CASA) as casa:
        for _ in range(5):
            assert _login(casa, ERRADA).status_code == 401
        assert _login(casa, ADMIN_PASS).status_code == 429


# ------------------------------------------------------------ IPv6


def test_origem_agrupa_ipv6_por_64():
    assert origem("203.0.113.5") == "203.0.113.5"
    assert origem("2001:db8:1:2::a") == origem("2001:db8:1:2:ffff:ffff:ffff:ffff") == "2001:db8:1:2::/64"
    assert origem("2001:db8:1:3::a") != origem("2001:db8:1:2::a")
    assert origem("::ffff:203.0.113.5") == "203.0.113.5"
    assert origem("testclient") == "testclient"
    assert origem(None) == "?"


def test_trocar_o_fim_do_ipv6_nao_zera_a_trava(admin):
    """Um aparelho IPv6 controla o /64 inteiro: girar o endereço dentro dele não é outra origem."""
    for i in range(5):
        with _de(f"2001:db8:66:1::{i + 1:x}") as c:
            assert _login(c, ERRADA).status_code == 401
    with _de("2001:db8:66:1::ff") as c:
        assert _login(c, ADMIN_PASS).status_code == 429
    with _de("2001:db8:77:1::1") as outro:  # outro /64 não herda a trava
        assert _login(outro, ADMIN_PASS).status_code == 200


def test_dono_em_ipv6_continua_conhecido_quando_o_endereco_gira(admin, relogio):
    with _de("2001:db8:aa:bb::1") as c:
        assert _login(c, ADMIN_PASS).status_code == 200
    _sob_ataque(relogio)
    with _de("2001:db8:aa:bb:1234:5678:9abc:def0") as c:  # extensão de privacidade trocou o sufixo
        assert _login(c, ADMIN_PASS).status_code == 200


# ------------------------------------------------------------ memória


def test_limitador_descarta_chaves_vencidas():
    """Sem a varredura, cada e-mail inventado ficaria no dicionário até o próximo deploy."""
    r = Relogio()
    lim = AttemptLimiter(free_attempts=5, max_block_seconds=900, window_seconds=3600, clock=r)
    for i in range(1000):
        lim.register_failure(f"inventado{i}@x.br")
    assert len(lim._attempts) == 1000
    r.t += 3600 + AttemptLimiter.SWEEP_EVERY_SECONDS + 1
    lim.register_failure("mais-um@x.br")
    assert len(lim._attempts) == 1
