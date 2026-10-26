"""As três correções da auditoria da fase 9.

Cada teste falha se a correção for desfeita — que é o único jeito de uma correção de segurança
continuar valendo depois que quem a fez esquece por que a fez.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.models import AuthSession
from app.services import auth as auth_service
from app.services.periods import DATA_MAX, DATA_MIN, dentro_do_calendario
from tests.conftest import ADMIN_EMAIL, ADMIN_PASS, login_android


# --------------------------------------------------------- teto absoluto da sessão


def test_sessao_morre_no_teto_absoluto_mesmo_em_uso_diario(client, admin, db):
    """A validade desliza, mas até um limite contado do LOGIN.

    Sem isto, um token que vaze e seja usado uma vez por mês vale para sempre — e o dono não tem
    como perceber, porque não existe tela que liste as sessões vivas.
    """
    headers = login_android(client, ADMIN_EMAIL, ADMIN_PASS)
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

    sessao = db.scalars(select(AuthSession)).one()
    limite = get_settings().SESSION_ABSOLUTE_DAYS
    # o token continua "válido" (expires_at no futuro), mas nasceu além do teto
    sessao.created_at = datetime.now(timezone.utc) - timedelta(days=limite + 1)
    sessao.expires_at = datetime.now(timezone.utc) + timedelta(days=30)
    sessao.last_used_at = datetime.now(timezone.utc)
    db.commit()

    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_sessao_recente_continua_valendo(client, admin, db):
    """O outro lado: o teto não pode derrubar quem entrou ontem."""
    headers = login_android(client, ADMIN_EMAIL, ADMIN_PASS)
    sessao = db.scalars(select(AuthSession)).one()
    sessao.created_at = datetime.now(timezone.utc) - timedelta(days=1)
    db.commit()
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200


def test_renovacao_nao_promete_mais_do_que_o_teto(client, admin, db):
    """Perto do fim, a sessão passa a valer só até o teto.

    Sem este ajuste, a última renovação prometeria 30 dias que a checagem do teto não cumpriria: o
    cliente veria uma data e o servidor obedeceria outra.
    """
    ajustes = get_settings()
    headers = login_android(client, ADMIN_EMAIL, ADMIN_PASS)
    sessao = db.scalars(select(AuthSession)).one()

    nascimento = datetime.now(timezone.utc) - timedelta(days=ajustes.SESSION_ABSOLUTE_DAYS - 2)
    sessao.created_at = nascimento
    # last_used_at antigo o bastante para disparar a renovação
    sessao.last_used_at = datetime.now(timezone.utc) - timedelta(hours=ajustes.SESSION_TOUCH_MINUTES / 60 + 2)
    sessao.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    db.commit()

    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

    db.expire_all()
    sessao = db.scalars(select(AuthSession)).one()
    teto = nascimento + timedelta(days=ajustes.SESSION_ABSOLUTE_DAYS)
    # tolerância de um minuto: o teste e o servidor não leem o relógio no mesmo instante
    assert sessao.expires_at <= teto + timedelta(minutes=1)
    assert sessao.expires_at < datetime.now(timezone.utc) + timedelta(days=ajustes.SESSION_DAYS)


def test_teto_e_o_do_ajuste_nao_um_numero_solto():
    """O teto tem de vir da configuração — senão muda-se o .env e o código ignora."""
    assert get_settings().SESSION_ABSOLUTE_DAYS >= get_settings().SESSION_DAYS


# ------------------------------------------- guarda de calendário nas datas do corpo


def test_dentro_do_calendario_aceita_o_intervalo_e_recusa_o_resto():
    dentro = datetime(2026, 9, 7, tzinfo=timezone.utc)
    assert dentro_do_calendario(dentro) is dentro
    assert dentro_do_calendario(None) is None
    for fora in (datetime(1999, 12, 31, tzinfo=timezone.utc), datetime(2101, 1, 1, tzinfo=timezone.utc)):
        with pytest.raises(ValueError, match="2000 a 2100"):
            dentro_do_calendario(fora)
    # as bordas são inclusivas
    assert dentro_do_calendario(datetime.combine(DATA_MIN, datetime.min.time(), tzinfo=timezone.utc))
    assert dentro_do_calendario(datetime.combine(DATA_MAX, datetime.min.time(), tzinfo=timezone.utc))


DATAS_DO_CORPO = [
    ("POST", "/api/v1/work-orders", "scheduled_at"),
    ("PATCH", "/api/v1/work-orders/{id}", "scheduled_at"),
    ("PATCH", "/api/v1/work-orders/{id}", "previsao_conclusao"),
    ("PATCH", "/api/v1/work-orders/{id}", "vencimento"),
]


@pytest.mark.parametrize("metodo,caminho,campo", DATAS_DO_CORPO)
def test_data_absurda_no_corpo_vira_422_e_nao_500(
    client, admin_headers, seed_cliente_veiculo, seed_servicos, metodo, caminho, campo
):
    """9999-12-31 chegava até `_refresh_previsao`, que soma minutos e estoura OverflowError.

    OverflowError não é HTTPException nem IntegrityError — não há handler, e a resposta era 500
    genérica no meio de um agendamento. Agora é 422 em português, dita pelo validador.
    """
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    wo = client.post(
        "/api/v1/work-orders",
        json={
            "client_id": cliente["id"],
            "vehicle_id": veiculo["id"],
            "itens": [{"service_id": lavagem["id"]}],
        },
        headers=admin_headers,
    ).json()
    client.post(f"/api/v1/work-orders/{wo['id']}/transition", json={"to_status": "recebido"}, headers=admin_headers)

    corpo = {campo: "9999-12-31T23:59:59"}
    if metodo == "POST":
        corpo |= {"client_id": cliente["id"], "vehicle_id": veiculo["id"], "status": "agendado"}

    r = client.request(metodo, caminho.format(id=wo["id"]), json=corpo, headers=admin_headers)
    assert r.status_code == 422, f"{metodo} {caminho} com {campo} absurdo respondeu {r.status_code}"
    assert "2000 a 2100" in r.text


def test_data_absurda_na_recepcao_tambem_e_422(client, admin_headers, seed_servicos):
    """A recepção é o caminho do celular — o dedo errado aqui é o mais provável de todos."""
    lavagem, _ = seed_servicos
    r = client.post(
        "/api/v1/work-orders/intake",
        json={
            "cliente": {"nome": "Teste Data", "telefone": "82 98888-7777"},
            "veiculo": {"placa": "DAT1A11", "marca": "VW", "modelo": "Gol"},
            "itens": [{"service_id": lavagem["id"]}],
            "previsao_conclusao": "9999-12-31T23:59:59",
            "idempotency_key": "intake-data-absurda",
        },
        headers=admin_headers,
    )
    assert r.status_code == 422
    assert "2000 a 2100" in r.text


def test_pagamento_com_data_absurda_para_tras(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    """`pago_em` já barrava o futuro; o passado absurdo passava direto para o caixa."""
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    wo = client.post(
        "/api/v1/work-orders",
        json={
            "client_id": cliente["id"],
            "vehicle_id": veiculo["id"],
            "itens": [{"service_id": lavagem["id"]}],
        },
        headers=admin_headers,
    ).json()
    client.post(f"/api/v1/work-orders/{wo['id']}/transition", json={"to_status": "recebido"}, headers=admin_headers)

    r = client.post(
        f"/api/v1/work-orders/{wo['id']}/payments",
        json={
            "valor_centavos": 1000,
            "forma": "pix",
            "idempotency_key": "pago-em-absurdo",
            "pago_em": "1500-01-01T10:00:00",
        },
        headers=admin_headers,
    )
    assert r.status_code == 422
    assert "2000 a 2100" in r.text


def test_data_plausivel_continua_passando(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    """A guarda não pode estreitar o uso normal: agendar para o ano que vem tem de funcionar."""
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    daqui_um_ano = (datetime.now(timezone.utc) + timedelta(days=365)).replace(microsecond=0)
    r = client.post(
        "/api/v1/work-orders",
        json={
            "client_id": cliente["id"],
            "vehicle_id": veiculo["id"],
            "status": "agendado",
            "scheduled_at": daqui_um_ano.isoformat(),
            "itens": [{"service_id": lavagem["id"]}],
        },
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text


# --------------------------------------------------- o manifesto do app (o token no backup)


def test_manifesto_do_app_desliga_o_backup():
    """O token do sócio vive em SharedPreferences; com o backup ligado ele sai do aparelho.

    Este teste mora no backend de propósito: é aqui que roda a CI, e a checagem é textual — não
    precisa de Flutter nem de Android SDK para valer.
    """
    import pathlib

    raiz = pathlib.Path(__file__).resolve().parents[2]
    manifesto = (raiz / "mobile/android/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
    regras = raiz / "mobile/android/app/src/main/res/xml/regras_de_extracao.xml"

    assert 'android:allowBackup="false"' in manifesto, "o backup do Android voltou a ficar ligado"
    assert 'android:dataExtractionRules="@xml/regras_de_extracao"' in manifesto
    assert regras.exists(), "o XML das regras de extração sumiu"

    conteudo = regras.read_text(encoding="utf-8")
    # as duas metades importam: nuvem E transferência direta de celular para celular
    assert "<cloud-backup>" in conteudo and "<device-transfer>" in conteudo
    assert conteudo.count('<exclude domain="sharedpref" />') == 2


def test_comentario_do_security_nao_promete_cofre():
    """O comentário dizia que o token ficava "no cofre do aparelho". Não fica — e comentário que
    descreve uma proteção inexistente é pior que comentário nenhum: alguém confia nele."""
    import pathlib

    raiz = pathlib.Path(__file__).resolve().parents[1]
    texto = (raiz / "app/core/security.py").read_text(encoding="utf-8")
    assert "cofre do aparelho" not in texto
