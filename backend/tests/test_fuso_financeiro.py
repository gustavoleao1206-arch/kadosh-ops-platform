"""As fronteiras de fuso do financeiro (America/Maceio, UTC−3).

O banco guarda UTC; o dono conta o dia da LOJA. Entre 21h e meia-noite em Maceió, o relógio do banco
já está no dia seguinte — é a janela em que um Pix da noite de segunda aparece na terça, o
fechamento do mês vaza para o mês seguinte e ninguém entende por quê.

Os horários daqui não são decorativos: 02:59Z e 03:01Z são os dois minutos que cercam a virada do
dia local (00:00 em Maceió = 03:00 UTC). Um pagamento de cada lado prova de que lado a conta caiu.
"""

from datetime import datetime, timedelta, timezone

from app.services.periods import month_bounds, today_local
from tests.conftest import login_android

UTC = timezone.utc


def _paga(client, headers, cliente, veiculo, servico, *, valor, chave, pago_em):
    wo = client.post(
        "/api/v1/work-orders",
        json={
            "client_id": cliente["id"],
            "vehicle_id": veiculo["id"],
            "itens": [{"service_id": servico["id"], "valor_centavos": valor}],
        },
        headers=headers,
    ).json()
    client.post(f"/api/v1/work-orders/{wo['id']}/transition", json={"to_status": "recebido"}, headers=headers)
    r = client.post(
        f"/api/v1/work-orders/{wo['id']}/payments",
        json={
            "valor_centavos": valor,
            "forma": "pix",
            "idempotency_key": chave,
            "pago_em": pago_em.isoformat(),
        },
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_virada_do_dia_local_separa_os_dois_pagamentos(
    client, admin_headers, seed_cliente_veiculo, seed_servicos
):
    """02:59Z é ainda ONTEM na loja; 03:01Z já é hoje. O caixa e o extrato têm de concordar nisso."""
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos

    hoje = today_local()
    ontem = hoje - timedelta(days=1)
    # 00:00 local de hoje = 03:00Z de hoje
    antes = datetime(hoje.year, hoje.month, hoje.day, 2, 59, tzinfo=UTC)
    depois = datetime(hoje.year, hoje.month, hoje.day, 3, 1, tzinfo=UTC)

    _paga(client, admin_headers, cliente, veiculo, lavagem, valor=1100, chave="fuso-ontem", pago_em=antes)
    _paga(client, admin_headers, cliente, veiculo, lavagem, valor=2200, chave="fuso-hoje1", pago_em=depois)

    caixa_ontem = client.get(f"/api/v1/caixa?dia={ontem.isoformat()}", headers=admin_headers).json()
    caixa_hoje = client.get(f"/api/v1/caixa?dia={hoje.isoformat()}", headers=admin_headers).json()
    assert caixa_ontem["recebido_centavos"] == 1100
    assert caixa_hoje["recebido_centavos"] == 2200

    ext_ontem = client.get(
        f"/api/v1/extrato?de={ontem.isoformat()}&ate={ontem.isoformat()}", headers=admin_headers
    ).json()
    ext_hoje = client.get(
        f"/api/v1/extrato?de={hoje.isoformat()}&ate={hoje.isoformat()}", headers=admin_headers
    ).json()
    assert ext_ontem["total_centavos"] == caixa_ontem["recebido_centavos"]
    assert ext_hoje["total_centavos"] == caixa_hoje["recebido_centavos"]


def test_virada_do_mes_local(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    """O último Pix do mês, às 23h em Maceió, é do mês que fechou — não do que começou em UTC."""
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos

    hoje = today_local()
    primeiro_deste_mes = hoje.replace(day=1)
    # 23:30 local do último dia do mês passado = 02:30Z do dia 1 deste mês
    ultimo_instante_do_mes_passado = datetime(
        primeiro_deste_mes.year, primeiro_deste_mes.month, primeiro_deste_mes.day, 2, 30, tzinfo=UTC
    )
    _paga(
        client,
        admin_headers,
        cliente,
        veiculo,
        lavagem,
        valor=4400,
        chave="fuso-mes-x",
        pago_em=ultimo_instante_do_mes_passado,
    )

    deste = client.get("/api/v1/relatorios?periodo=mes", headers=admin_headers).json()
    passado = client.get("/api/v1/relatorios?periodo=mes_passado", headers=admin_headers).json()
    assert deste["totais"]["recebido_centavos"] == 0
    assert passado["totais"]["recebido_centavos"] == 4400

    # e a série mensal joga o valor no mesmo balde do relatório
    meses = client.get("/api/v1/relatorios/mensal?meses=2", headers=admin_headers).json()["meses"]
    anterior, atual = meses
    assert anterior["recebido_centavos"] == 4400
    assert atual["recebido_centavos"] == 0


def test_mes_especifico_usa_os_mesmos_limites_do_mes_corrente(
    client, admin_headers, seed_cliente_veiculo, seed_servicos
):
    """Pedir "este mês" e pedir o mês pelo nome tem de devolver exatamente o mesmo período."""
    hoje = today_local()
    corrente = client.get("/api/v1/relatorios?periodo=mes", headers=admin_headers).json()["periodo"]
    nomeado = client.get(
        f"/api/v1/relatorios?periodo=mes_especifico&mes={hoje.year:04d}-{hoje.month:02d}",
        headers=admin_headers,
    ).json()["periodo"]
    assert (corrente["de"], corrente["ate"], corrente["label"]) == (
        nomeado["de"],
        nomeado["ate"],
        nomeado["label"],
    )


def test_limites_do_mes_sao_do_fuso_da_loja():
    """[00:00 local do dia 1, 00:00 local do dia 1 do mês seguinte) — em UTC, 03:00 dos dois lados."""
    hoje = today_local()
    ini, fim = month_bounds(hoje)
    assert ini.hour == 3 and ini.minute == 0
    assert fim.hour == 3 and fim.minute == 0
    assert ini.day == 1 and fim.day == 1


def test_vencimento_na_virada_da_meia_noite_local(
    client, admin_headers, seed_cliente_veiculo, seed_servicos
):
    """Prazo "até hoje" só vira atraso depois da meia-noite da loja, não às 21h de ontem."""
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    wo = client.post(
        "/api/v1/work-orders",
        json={
            "client_id": cliente["id"],
            "vehicle_id": veiculo["id"],
            "itens": [{"service_id": lavagem["id"], "valor_centavos": 5000}],
        },
        headers=admin_headers,
    ).json()
    client.post(f"/api/v1/work-orders/{wo['id']}/transition", json={"to_status": "recebido"}, headers=admin_headers)

    # prazo daqui a um minuto: ainda não venceu
    quase = datetime.now(UTC) + timedelta(minutes=1)
    r = client.patch(
        f"/api/v1/work-orders/{wo['id']}", json={"vencimento": quase.isoformat()}, headers=admin_headers
    )
    assert r.json()["situacao_cobranca"] == "pendente"

    # prazo de um minuto atrás: venceu
    passou = datetime.now(UTC) - timedelta(minutes=1)
    r = client.patch(
        f"/api/v1/work-orders/{wo['id']}", json={"vencimento": passou.isoformat()}, headers=admin_headers
    )
    assert r.json()["situacao_cobranca"] == "atrasado"


def test_vencimento_sem_fuso_e_lido_como_horario_da_loja(
    client, admin_headers, seed_cliente_veiculo, seed_servicos
):
    """O app pode mandar data sem fuso; ela vale como hora de Maceió, nunca como UTC.

    A diferença não é acadêmica: lida como UTC, uma data das 23h locais viraria 20h — três horas de
    prazo a menos, e uma OS marcada como atrasada antes da hora.
    """
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    wo = client.post(
        "/api/v1/work-orders",
        json={
            "client_id": cliente["id"],
            "vehicle_id": veiculo["id"],
            "itens": [{"service_id": lavagem["id"], "valor_centavos": 5000}],
        },
        headers=admin_headers,
    ).json()
    client.post(f"/api/v1/work-orders/{wo['id']}/transition", json={"to_status": "recebido"}, headers=admin_headers)

    amanha = today_local() + timedelta(days=1)
    r = client.patch(
        f"/api/v1/work-orders/{wo['id']}",
        json={"vencimento": f"{amanha.isoformat()}T18:00:00"},  # sem fuso, de propósito
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    guardado = datetime.fromisoformat(r.json()["vencimento"].replace("Z", "+00:00"))
    # 18:00 em Maceió = 21:00 UTC
    assert guardado.astimezone(UTC).hour == 21
