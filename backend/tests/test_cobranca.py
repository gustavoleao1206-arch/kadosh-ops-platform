"""A régua de cobrança: pago, a receber, atrasado.

O teste que dá nome ao arquivo é `test_python_e_sql_concordam`. A regra existe duas vezes —
`billing.situacao` para a resposta da API e `billing.situacao_sql` para o filtro `?cobranca=` — e o
pior bug possível deste módulo seria elas divergirem: a lista de "atrasados" mostrando uma OS que,
aberta, se diz "a receber". Aqui as duas rodam sobre a MESMA matriz de casos e têm de bater.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models import WorkOrder
from app.services import billing
from tests.conftest import STAFF_EMAIL, STAFF_PASS, login_android

AGORA = datetime(2026, 9, 7, 15, 0, tzinfo=timezone.utc)
ONTEM = AGORA - timedelta(days=1)
AMANHA = AGORA + timedelta(days=1)

# (status, total, pago, vencimento) -> situação esperada
CASOS = [
    # nada a cobrar antes da recepção do veículo
    ("orcamento", 10000, 0, None, None),
    ("agendado", 10000, 0, None, None),
    ("confirmado", 10000, 0, ONTEM, None),
    # encerradas sem entrega não são dívida
    ("cancelado", 10000, 0, ONTEM, None),
    ("nao_compareceu", 10000, 0, ONTEM, None),
    # OS sem valor não é cobrança nenhuma
    ("recebido", 0, 0, None, None),
    ("concluido", 0, 0, ONTEM, None),
    # quitada
    ("recebido", 10000, 10000, None, "pago"),
    ("concluido", 10000, 10000, ONTEM, "pago"),
    ("aguardando_retirada", 10000, 10000, AMANHA, "pago"),
    # no pátio, ainda devendo: pendente enquanto o prazo não vira
    ("recebido", 10000, 0, None, "pendente"),
    ("em_execucao", 10000, 4000, None, "pendente"),
    ("aguardando_retirada", 10000, 0, AMANHA, "pendente"),
    # prazo vencido com saldo: atrasado, mesmo com o carro ainda na loja
    ("recebido", 10000, 0, ONTEM, "atrasado"),
    ("em_execucao", 10000, 9999, ONTEM, "atrasado"),
    # entregue devendo e SEM prazo: atrasado — é o caso que precisa gritar
    ("concluido", 10000, 0, None, "atrasado"),
    ("concluido", 10000, 5000, None, "atrasado"),
    # ...e com prazo combinado no futuro volta a ser só "a receber"
    ("concluido", 10000, 5000, AMANHA, "pendente"),
    # o instante exato do vencimento ainda NÃO é atraso (só depois dele)
    ("concluido", 10000, 0, AGORA, "pendente"),
]


@pytest.mark.parametrize("status,total,pago,venc,esperado", CASOS)
def test_regra_em_python(status, total, pago, venc, esperado):
    assert (
        billing.situacao(
            status=status,
            valor_total_centavos=total,
            pago_centavos=pago,
            vencimento=venc,
            agora=AGORA,
        )
        == esperado
    )


def test_python_e_sql_concordam(db, client, admin_headers, seed_cliente_veiculo):
    """A mesma matriz, agora gravada no banco e classificada pelo CASE do SQL.

    Se este teste falhar depois de você mexer em `billing`, é porque só uma das duas
    implementações foi alterada — o filtro e a tela ficariam contando histórias diferentes.

    Os pagamentos não são gravados aqui (o service recusaria dinheiro numa OS de orçamento), então
    o esperado é recalculado em Python com `pago=0`: o que se compara é a CLASSIFICAÇÃO, não o valor.
    """
    cliente, veiculo = seed_cliente_veiculo
    por_id: dict[int, tuple] = {}
    for caso in CASOS:
        status, total, _pago, venc, _esperado = caso
        wo = WorkOrder(
            client_id=cliente["id"],
            vehicle_id=None if status in ("orcamento", "cancelado") else veiculo["id"],
            status=status,
            valor_total_centavos=total,
            vencimento=venc,
        )
        db.add(wo)
        db.flush()
        por_id[wo.id] = caso
    db.commit()

    pago_col = billing.pago_por_os()
    linhas = db.execute(
        select(WorkOrder.id, billing.situacao_sql(pago_col.c.pago, agora=AGORA))
        .outerjoin(pago_col, pago_col.c.wid == WorkOrder.id)
        .where(WorkOrder.id.in_(por_id))
    ).all()

    assert len(linhas) == len(CASOS)
    for wid, do_sql in linhas:
        status, total, _pago, venc, _esperado = por_id[wid]
        do_python = billing.situacao(
            status=status, valor_total_centavos=total, pago_centavos=0, vencimento=venc, agora=AGORA
        )
        assert do_sql == do_python, f"OS {wid} ({status}, total={total}, venc={venc})"


def _os_recebida(client, headers, cliente, veiculo, servico):
    r = client.post(
        "/api/v1/work-orders",
        json={"client_id": cliente["id"], "vehicle_id": veiculo["id"], "itens": [{"service_id": servico["id"]}]},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    wo = r.json()
    r = client.post(
        f"/api/v1/work-orders/{wo['id']}/transition", json={"to_status": "recebido"}, headers=headers
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_os_no_patio_e_pendente_e_a_api_diz_o_rotulo(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    wo = _os_recebida(client, admin_headers, cliente, veiculo, lavagem)
    assert wo["situacao_cobranca"] == "pendente"
    # rótulo e cor vêm prontos: nenhum cliente escreve "A receber" nem escolhe amarelo
    assert wo["situacao_cobranca_label"] == "A receber"
    assert wo["situacao_cobranca_tone"] == "warn"


def test_quitar_muda_a_situacao_para_pago(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    wo = _os_recebida(client, admin_headers, cliente, veiculo, lavagem)
    r = client.post(
        f"/api/v1/work-orders/{wo['id']}/payments",
        json={"valor_centavos": wo["valor_total_centavos"], "forma": "pix", "idempotency_key": "quitar-01"},
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["situacao_cobranca"] == "pago"
    assert r.json()["situacao_cobranca_tone"] == "ok"


def test_entregar_devendo_sem_prazo_vira_atrasado(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    """O caso que motivou a regra: o carro saiu, o dinheiro não entrou e ninguém combinou data."""
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    wo = _os_recebida(client, admin_headers, cliente, veiculo, lavagem)
    r = client.post(
        f"/api/v1/work-orders/{wo['id']}/transition", json={"to_status": "concluido"}, headers=admin_headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["situacao_cobranca"] == "atrasado"
    assert r.json()["situacao_cobranca_tone"] == "danger"


def test_prazo_futuro_tira_a_os_entregue_do_vermelho(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    """Ele leva sexta o resto: pôr a data devolve a OS para a fila normal até o prazo chegar."""
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    wo = _os_recebida(client, admin_headers, cliente, veiculo, lavagem)
    client.post(f"/api/v1/work-orders/{wo['id']}/transition", json={"to_status": "concluido"}, headers=admin_headers)

    futuro = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    r = client.patch(f"/api/v1/work-orders/{wo['id']}", json={"vencimento": futuro}, headers=admin_headers)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["situacao_cobranca"] == "pendente"
    assert corpo["vencimento"] is not None
    # o de/para do prazo fica no histórico
    assert any(e["tipo"] == "vencimento" for e in corpo["eventos"])


def test_vencimento_e_a_unica_edicao_permitida_numa_os_concluida(
    client, admin_headers, seed_cliente_veiculo, seed_servicos
):
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    wo = _os_recebida(client, admin_headers, cliente, veiculo, lavagem)
    client.post(f"/api/v1/work-orders/{wo['id']}/transition", json={"to_status": "concluido"}, headers=admin_headers)

    futuro = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    ok = client.patch(f"/api/v1/work-orders/{wo['id']}", json={"vencimento": futuro}, headers=admin_headers)
    assert ok.status_code == 200, ok.text
    # qualquer outro campo continua barrado — inclusive quando vem de carona com o vencimento
    r = client.patch(
        f"/api/v1/work-orders/{wo['id']}",
        json={"vencimento": futuro, "observacoes": "tentando editar"},
        headers=admin_headers,
    )
    assert r.status_code == 409
    assert "encerrada" in r.json()["detail"].lower()


def test_prazo_exige_saldo_a_receber(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    """Data de vencimento em OS quitada seria enfeite que ainda por cima mente na régua."""
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    wo = _os_recebida(client, admin_headers, cliente, veiculo, lavagem)
    client.post(
        f"/api/v1/work-orders/{wo['id']}/payments",
        json={"valor_centavos": wo["valor_total_centavos"], "forma": "dinheiro", "idempotency_key": "quitou-tudo"},
        headers=admin_headers,
    )
    futuro = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    r = client.patch(f"/api/v1/work-orders/{wo['id']}", json={"vencimento": futuro}, headers=admin_headers)
    assert r.status_code == 409
    assert "saldo" in r.json()["detail"].lower()


def test_prazo_recusado_em_orcamento(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    wo = client.post(
        "/api/v1/work-orders",
        json={"client_id": cliente["id"], "vehicle_id": veiculo["id"], "itens": [{"service_id": lavagem["id"]}]},
        headers=admin_headers,
    ).json()
    futuro = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    r = client.patch(f"/api/v1/work-orders/{wo['id']}", json={"vencimento": futuro}, headers=admin_headers)
    assert r.status_code == 409
    assert "pagamento" in r.json()["detail"].lower()


def test_limpar_o_prazo_sempre_pode(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    """Tirar a data é inofensivo — a OS só volta para a regra padrão."""
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    wo = _os_recebida(client, admin_headers, cliente, veiculo, lavagem)
    futuro = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    client.patch(f"/api/v1/work-orders/{wo['id']}", json={"vencimento": futuro}, headers=admin_headers)
    r = client.patch(f"/api/v1/work-orders/{wo['id']}", json={"vencimento": None}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["vencimento"] is None
    assert r.json()["situacao_cobranca"] == "pendente"


def test_filtro_de_cobranca_bate_com_o_campo_da_propria_os(
    client, admin_headers, seed_cliente_veiculo, seed_servicos
):
    """O contrato entre a lista e o detalhe: quem o filtro traz diz o mesmo quando aberto."""
    cliente, veiculo = seed_cliente_veiculo
    lavagem, polimento = seed_servicos

    quitada = _os_recebida(client, admin_headers, cliente, veiculo, lavagem)
    client.post(
        f"/api/v1/work-orders/{quitada['id']}/payments",
        json={"valor_centavos": quitada["valor_total_centavos"], "forma": "pix", "idempotency_key": "f-quitada"},
        headers=admin_headers,
    )
    devendo = _os_recebida(client, admin_headers, cliente, veiculo, polimento)
    entregue_devendo = _os_recebida(client, admin_headers, cliente, veiculo, lavagem)
    client.post(
        f"/api/v1/work-orders/{entregue_devendo['id']}/transition",
        json={"to_status": "concluido"},
        headers=admin_headers,
    )

    for situacao, esperados in (
        ("pago", {quitada["id"]}),
        ("pendente", {devendo["id"]}),
        ("atrasado", {entregue_devendo["id"]}),
    ):
        r = client.get(f"/api/v1/work-orders?cobranca={situacao}", headers=admin_headers)
        assert r.status_code == 200, r.text
        itens = r.json()["items"]
        assert {i["id"] for i in itens} == esperados, situacao
        # cada linha trazida confirma, no próprio corpo, a situação pela qual foi filtrada
        assert all(i["situacao_cobranca"] == situacao for i in itens), situacao


def test_estorno_devolve_a_os_para_a_fila_de_cobranca(
    client, admin_headers, seed_cliente_veiculo, seed_servicos
):
    """Estornar não é só desfazer dinheiro: a OS volta a ser cobrança, e o filtro tem de segui-la."""
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    wo = _os_recebida(client, admin_headers, cliente, veiculo, lavagem)
    pago = client.post(
        f"/api/v1/work-orders/{wo['id']}/payments",
        json={"valor_centavos": wo["valor_total_centavos"], "forma": "pix", "idempotency_key": "vai-estornar"},
        headers=admin_headers,
    ).json()
    assert pago["situacao_cobranca"] == "pago"

    pid = pago["pagamentos"][0]["id"]
    r = client.post(
        f"/api/v1/work-orders/{wo['id']}/payments/{pid}/estorno",
        json={"motivo": "Pix não caiu"},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["situacao_cobranca"] == "pendente"
    lista = client.get("/api/v1/work-orders?cobranca=pendente", headers=admin_headers).json()["items"]
    assert wo["id"] in {i["id"] for i in lista}


def test_filtro_invalido_e_422(client, admin_headers):
    assert client.get("/api/v1/work-orders?cobranca=inventado", headers=admin_headers).status_code == 422


def test_socio_tambem_ve_a_regua(client, staff, seed_cliente_veiculo, seed_servicos):
    """Cobrança atrasada precisa aparecer para quem está no balcão, não só para o dono."""
    headers = login_android(client, STAFF_EMAIL, STAFF_PASS)
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    wo = _os_recebida(client, headers, cliente, veiculo, lavagem)
    assert client.get("/api/v1/work-orders?cobranca=pendente", headers=headers).status_code == 200
    assert wo["situacao_cobranca"] == "pendente"


def test_prazo_e_desconto_no_mesmo_patch_olham_o_total_novo(
    client, admin_headers, seed_cliente_veiculo, seed_servicos
):
    """Achado da revisão: a checagem de saldo do vencimento rodava ANTES do recálculo do total.

    Cenário concreto: OS de R$ 100 com desconto de R$ 50 (total R$ 50), quitada com R$ 50. Um PATCH
    que TIRA o desconto e põe prazo devolve o total para R$ 100 e cria saldo de R$ 50 — mas a
    validação, olhando o total velho, via saldo zero e recusava um prazo perfeitamente legítimo.
    """
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    wo = client.post(
        "/api/v1/work-orders",
        json={
            "client_id": cliente["id"],
            "vehicle_id": veiculo["id"],
            "itens": [{"service_id": lavagem["id"], "valor_centavos": 10000}],
            "desconto_centavos": 5000,
        },
        headers=admin_headers,
    ).json()
    assert wo["valor_total_centavos"] == 5000
    client.post(f"/api/v1/work-orders/{wo['id']}/transition", json={"to_status": "recebido"}, headers=admin_headers)
    client.post(
        f"/api/v1/work-orders/{wo['id']}/payments",
        json={"valor_centavos": 5000, "forma": "pix", "idempotency_key": "quita-desc-01"},
        headers=admin_headers,
    )

    futuro = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    r = client.patch(
        f"/api/v1/work-orders/{wo['id']}",
        json={"desconto_centavos": 0, "vencimento": futuro},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["valor_total_centavos"] == 10000
    assert corpo["saldo_centavos"] == 5000
    assert corpo["vencimento"] is not None
    assert corpo["situacao_cobranca"] == "pendente"


def test_prazo_recusado_quando_o_desconto_do_mesmo_patch_quita_a_os(
    client, admin_headers, seed_cliente_veiculo, seed_servicos
):
    """O outro lado do mesmo bug: o desconto zera o saldo, então o prazo não deve ser aceito."""
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    wo = client.post(
        "/api/v1/work-orders",
        json={
            "client_id": cliente["id"],
            "vehicle_id": veiculo["id"],
            "itens": [{"service_id": lavagem["id"], "valor_centavos": 10000}],
        },
        headers=admin_headers,
    ).json()
    client.post(f"/api/v1/work-orders/{wo['id']}/transition", json={"to_status": "recebido"}, headers=admin_headers)
    client.post(
        f"/api/v1/work-orders/{wo['id']}/payments",
        json={"valor_centavos": 5000, "forma": "pix", "idempotency_key": "meio-pago-01"},
        headers=admin_headers,
    )

    futuro = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    r = client.patch(
        f"/api/v1/work-orders/{wo['id']}",
        json={"desconto_centavos": 5000, "vencimento": futuro},
        headers=admin_headers,
    )
    assert r.status_code == 409
    assert "saldo" in r.json()["detail"].lower()
    # e a recusa não pode ter deixado o desconto aplicado pela metade
    depois = client.get(f"/api/v1/work-orders/{wo['id']}", headers=admin_headers).json()
    assert depois["desconto_centavos"] == 0
    assert depois["valor_total_centavos"] == 10000
    assert depois["vencimento"] is None
