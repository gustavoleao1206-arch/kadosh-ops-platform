"""Os caminhos que a cobertura mostrou nunca terem rodado — e que mexem em dinheiro.

97% de cobertura esconde o que importa: entre as linhas nunca executadas estava o `except
IntegrityError` de `payments.registrar`, que é justamente a rede que impede COBRAR O CLIENTE DUAS
VEZES quando dois toques chegam ao mesmo tempo. Código de corrida que nunca rodou em teste é
código que ninguém sabe se funciona — e este só é exercitado por uma corrida de verdade, que não
acontece sozinha numa suíte sequencial.

Os testes abaixo forçam essas condições à mão, em vez de esperar que a sorte as produza.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import Payment, WorkOrder
from app.services import payments as pay_svc
from app.services.periods import mes_referencia
from tests.conftest import login_android


def _os_recebida(client, headers, cliente, veiculo, servico, valor=20000):
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
    return wo


# ------------------------------------------------- a corrida da chave de pagamento


def _cega_a_leitura_da_chave(monkeypatch, vezes: int):
    """Faz `_mesma_chave` responder "não existe" nas `vezes` primeiras chamadas.

    É o que uma corrida de verdade produz: a transação gêmea comitou, mas as nossas duas leituras
    (a rápida e a que roda sob o lock) aconteceram antes de ela ficar visível. Sem cegar essas
    leituras, o teste nunca chega ao INSERT — a segunda leitura resolve tudo, e o `except
    IntegrityError` continua sendo código que ninguém sabe se funciona.
    """
    original = pay_svc._mesma_chave
    contador = {"n": 0}

    def espiao(db_, chave):
        contador["n"] += 1
        return None if contador["n"] <= vezes else original(db_, chave)

    monkeypatch.setattr(pay_svc, "_mesma_chave", espiao)
    return contador


def test_corrida_na_chave_devolve_o_estado_em_vez_de_cobrar_de_novo(
    db, client, admin, admin_headers, seed_cliente_veiculo, seed_servicos, monkeypatch
):
    """Dois toques simultâneos com a MESMA chave: o segundo não pode virar segundo pagamento.

    A defesa tem duas camadas. A primeira é a leitura da chave (a rápida e a que roda sob o lock),
    e já é testada em test_payments.py. Esta é a SEGUNDA: quando a gêmea comita tarde demais para
    ser vista, o UNIQUE do banco estoura no flush e o `except IntegrityError` precisa reconhecer a
    chave e devolver o estado — em vez de deixar subir um 500 ou, pior, cobrar de novo.
    """
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    wo = _os_recebida(client, admin_headers, cliente, veiculo, lavagem)
    chave = "corrida-mesma-chave-01"

    # a requisição gêmea já gravou e comitou
    db.add(
        Payment(
            work_order_id=wo["id"],
            valor_centavos=5000,
            forma="pix",
            idempotency_key=chave,
            created_by=admin.id,
        )
    )
    db.commit()

    # ...mas as nossas duas leituras não a enxergam
    contador = _cega_a_leitura_da_chave(monkeypatch, vezes=2)

    resultado = pay_svc.registrar(
        db,
        wo["id"],
        {"valor_centavos": 5000, "forma": "pix", "idempotency_key": chave},
        user=admin,
    )

    # a terceira leitura (dentro do except) é que salva: precisa ter acontecido
    assert contador["n"] >= 3, "o INSERT não chegou a estourar — o teste não exercitou o que devia"
    assert resultado.id == wo["id"]

    pagamentos = db.scalars(select(Payment).where(Payment.work_order_id == wo["id"])).all()
    assert len(pagamentos) == 1, "a corrida criou um segundo pagamento — o cliente pagaria em dobro"
    assert pagamentos[0].valor_centavos == 5000


def test_corrida_com_chave_de_outra_os_sobe_o_erro(
    db, client, admin, admin_headers, seed_cliente_veiculo, seed_servicos, monkeypatch
):
    """Se a chave gêmea pertence a OUTRA OS, a exceção sobe — não vira 200 silencioso.

    Engolir aqui devolveria "deu certo" para um pagamento que nunca foi lançado, e o dono só
    descobriria a diferença no fechamento do caixa.
    """
    cliente, veiculo = seed_cliente_veiculo
    lavagem, polimento = seed_servicos
    wo_a = _os_recebida(client, admin_headers, cliente, veiculo, lavagem)
    wo_b = _os_recebida(client, admin_headers, cliente, veiculo, polimento)
    chave = "corrida-outra-os-01"

    db.add(
        Payment(
            work_order_id=wo_b["id"],  # a gêmea caiu em OUTRA OS
            valor_centavos=5000,
            forma="pix",
            idempotency_key=chave,
            created_by=admin.id,
        )
    )
    db.commit()
    _cega_a_leitura_da_chave(monkeypatch, vezes=2)

    with pytest.raises(IntegrityError):
        pay_svc.registrar(
            db,
            wo_a["id"],
            {"valor_centavos": 5000, "forma": "pix", "idempotency_key": chave},
            user=admin,
        )

    # e a OS de destino continua sem pagamento nenhum
    db.rollback()
    assert db.scalars(select(Payment).where(Payment.work_order_id == wo_a["id"])).all() == []


def test_repetir_a_chave_pela_api_nao_duplica(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    """O caminho comum, pela porta da frente: o sócio toca duas vezes porque a resposta demorou."""
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    wo = _os_recebida(client, admin_headers, cliente, veiculo, lavagem)
    corpo = {"valor_centavos": 8000, "forma": "pix", "idempotency_key": "toque-repetido-001"}

    primeira = client.post(f"/api/v1/work-orders/{wo['id']}/payments", json=corpo, headers=admin_headers)
    segunda = client.post(f"/api/v1/work-orders/{wo['id']}/payments", json=corpo, headers=admin_headers)

    assert primeira.status_code == 201
    assert segunda.status_code in (200, 201)
    # o que importa não é o status, é o dinheiro: um pagamento só
    assert segunda.json()["pago_centavos"] == 8000
    assert len([p for p in segunda.json()["pagamentos"] if p["estornado_em"] is None]) == 1


# ------------------------------------------------------------- série mensal: faturado


def test_serie_mensal_soma_faturado_no_mes_da_entrega(
    client, admin_headers, seed_cliente_veiculo, seed_servicos, db
):
    """A cobertura mostrou que o balde de FATURADO da série nunca rodava — só o de recebido.

    São contas diferentes: faturado é OS concluída (por `conclusao`), recebido é dinheiro que
    entrou (por `pago_em`). Um carro entregue em setembro e pago em outubro cai em meses
    diferentes, e é exatamente isso que o gráfico do painel mostra.
    """
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    wo = _os_recebida(client, admin_headers, cliente, veiculo, lavagem, valor=30000)
    client.post(
        f"/api/v1/work-orders/{wo['id']}/payments",
        json={"valor_centavos": 30000, "forma": "pix", "idempotency_key": "serie-fat-0001"},
        headers=admin_headers,
    )
    r = client.post(
        f"/api/v1/work-orders/{wo['id']}/transition", json={"to_status": "concluido"}, headers=admin_headers
    )
    assert r.status_code == 200, r.text

    meses = client.get("/api/v1/relatorios/mensal?meses=2", headers=admin_headers).json()["meses"]
    atual = meses[-1]
    assert atual["faturado_centavos"] == 30000
    assert atual["recebido_centavos"] == 30000
    assert atual["os_concluidas"] == 1
    # o mês anterior segue zerado — a série não pode espalhar o valor
    assert meses[0]["faturado_centavos"] == 0


def test_serie_mensal_ignora_o_que_esta_fora_da_janela(
    client, admin_headers, seed_cliente_veiculo, seed_servicos, db
):
    """OS concluída antes da janela não pode aparecer: o balde `None` é um caminho real."""
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    wo = _os_recebida(client, admin_headers, cliente, veiculo, lavagem, valor=12345)
    client.post(f"/api/v1/work-orders/{wo['id']}/transition", json={"to_status": "concluido"}, headers=admin_headers)

    # empurra a conclusão para bem antes da janela pedida
    linha = db.get(WorkOrder, wo["id"])
    linha.conclusao = datetime.now(timezone.utc) - timedelta(days=400)
    db.commit()

    meses = client.get("/api/v1/relatorios/mensal?meses=2", headers=admin_headers).json()["meses"]
    assert all(m["faturado_centavos"] == 0 for m in meses)
    assert all(m["os_concluidas"] == 0 for m in meses)


# ------------------------------------------------------------------ bordas de período


def test_mes_referencia_recusa_ano_fora_do_calendario():
    """`2026-13` já falhava (mês inválido). `1500-01` é mês VÁLIDO com ano absurdo."""
    assert mes_referencia("2026-09").year == 2026
    for absurdo in ("1500-01", "3000-12"):
        with pytest.raises(ValueError, match="2000 a 2100"):
            mes_referencia(absurdo)


def test_relatorio_com_mes_fora_do_calendario_e_422(client, admin_headers):
    r = client.get("/api/v1/relatorios?periodo=mes_especifico&mes=1500-01", headers=admin_headers)
    assert r.status_code == 422
    assert "2000 a 2100" in r.text


# --------------------------------------------------------- bordas do lançamento de item


def test_valor_negativo_no_item_e_recusado(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    """O schema barra antes, mas a checagem do service é a última linha — e nunca tinha rodado."""
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    r = client.post(
        "/api/v1/work-orders",
        json={
            "client_id": cliente["id"],
            "vehicle_id": veiculo["id"],
            "itens": [{"service_id": lavagem["id"], "valor_centavos": -1}],
        },
        headers=admin_headers,
    )
    assert r.status_code == 422


def test_os_concluida_recusa_lancar_e_remover_servico(
    client, admin_headers, seed_cliente_veiculo, seed_servicos
):
    """Depois de entregue, o serviço congela: reabrir é uma decisão do dono, com motivo."""
    cliente, veiculo = seed_cliente_veiculo
    lavagem, polimento = seed_servicos
    wo = _os_recebida(client, admin_headers, cliente, veiculo, lavagem)
    detalhe = client.post(
        f"/api/v1/work-orders/{wo['id']}/transition", json={"to_status": "concluido"}, headers=admin_headers
    ).json()

    r = client.post(
        f"/api/v1/work-orders/{wo['id']}/items",
        json=[{"service_id": polimento["id"], "idempotency_key": "depois-do-fim-1"}],
        headers=admin_headers,
    )
    assert r.status_code == 409
    assert "reabra" in r.json()["detail"].lower()

    item_id = detalhe["itens"][0]["id"]
    r = client.delete(f"/api/v1/work-orders/{wo['id']}/items/{item_id}", headers=admin_headers)
    assert r.status_code == 409


def test_os_nova_so_nasce_orcamento_ou_agendamento(client, admin_headers, seed_cliente_veiculo):
    """Criar OS já "concluída" pularia recepção, número e pagamento — e o histórico nasceria falso."""
    cliente, veiculo = seed_cliente_veiculo
    r = client.post(
        "/api/v1/work-orders",
        json={"client_id": cliente["id"], "vehicle_id": veiculo["id"], "status": "concluido"},
        headers=admin_headers,
    )
    assert r.status_code == 422


def test_agendar_sem_data_e_recusado(client, admin_headers, seed_cliente_veiculo):
    cliente, veiculo = seed_cliente_veiculo
    r = client.post(
        "/api/v1/work-orders",
        json={"client_id": cliente["id"], "vehicle_id": veiculo["id"], "status": "agendado"},
        headers=admin_headers,
    )
    assert r.status_code == 422


def test_trocar_para_veiculo_inexistente_e_404(client, admin_headers, seed_cliente_veiculo):
    cliente, veiculo = seed_cliente_veiculo
    wo = client.post(
        "/api/v1/work-orders",
        json={"client_id": cliente["id"], "vehicle_id": veiculo["id"]},
        headers=admin_headers,
    ).json()
    r = client.patch(f"/api/v1/work-orders/{wo['id']}", json={"vehicle_id": 999999}, headers=admin_headers)
    assert r.status_code == 404


def test_socio_tambem_cai_nas_bordas(client, staff, seed_cliente_veiculo, seed_servicos):
    """As regras de valor não afrouxam por papel — o sócio esbarra nos mesmos limites."""
    from tests.conftest import STAFF_EMAIL, STAFF_PASS

    headers = login_android(client, STAFF_EMAIL, STAFF_PASS)
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    wo = _os_recebida(client, headers, cliente, veiculo, lavagem, valor=10000)
    r = client.post(
        f"/api/v1/work-orders/{wo['id']}/payments",
        json={"valor_centavos": 999999, "forma": "pix", "idempotency_key": "socio-passa-do-saldo"},
        headers=headers,
    )
    assert r.status_code == 409
    assert "passa do que falta" in r.json()["detail"].lower()
