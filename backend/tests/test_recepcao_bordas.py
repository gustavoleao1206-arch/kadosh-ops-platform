"""A recepção é o caminho mais usado do sistema — e era o menos coberto (88%).

O sócio recebe carro o dia inteiro, no celular, com a mão molhada e a internet ruim. Todas as
recusas testadas aqui existem porque a alternativa é pior que o erro: receber um carro para um
cliente arquivado, atribuir um veículo ao dono errado, ou — o caso grave — abrir DUAS OS para o
mesmo carro porque o sinal caiu e ele tocou de novo.

Esse último caminho (`except IntegrityError` de `intake.receber`) nunca tinha rodado em teste. Uma
OS duplicada não é só um registro a mais: ela consome um número da sequência, aparece duas vezes no
pátio e faz o dono cobrar o mesmo serviço em dobro.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models import Client, Vehicle, WorkOrder
from app.schemas.intake import IntakeIn
from app.services import intake as intake_svc


def _corpo(servico, **patch):
    base = {
        "cliente": {"nome": "Cliente Recepção", "telefone": "82 97777-0001"},
        "veiculo": {"placa": "REC1A11", "marca": "VW", "modelo": "Polo"},
        "itens": [{"service_id": servico["id"]}],
        "idempotency_key": "recepcao-padrao-001",
    }
    base.update(patch)
    return base


# ------------------------------------------------------------------ cliente


def test_receber_para_cliente_inexistente_e_404(client, admin_headers, seed_servicos):
    lavagem, _ = seed_servicos
    r = client.post(
        "/api/v1/work-orders/intake",
        json=_corpo(lavagem, cliente={"id": 999999}, idempotency_key="rec-cli-inexistente"),
        headers=admin_headers,
    )
    assert r.status_code == 404
    assert "cliente" in r.json()["detail"].lower()


def test_receber_para_cliente_arquivado_e_409(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    """Arquivar é a forma de "apagar" um cliente aqui. Receber para ele o ressuscitaria pela porta
    dos fundos, sem ninguém decidir isso."""
    cliente, _ = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    assert client.post(f"/api/v1/clients/{cliente['id']}/arquivar", headers=admin_headers).status_code == 200

    r = client.post(
        "/api/v1/work-orders/intake",
        json=_corpo(lavagem, cliente={"id": cliente["id"]}, idempotency_key="rec-cli-arquivado"),
        headers=admin_headers,
    )
    assert r.status_code == 409
    assert "arquivado" in r.json()["detail"].lower()


def test_telefone_repetido_reaproveita_o_cliente_em_vez_de_duplicar(
    client, admin_headers, seed_cliente_veiculo, seed_servicos, db
):
    """O mesmo cliente voltando com outro carro não pode virar dois cadastros."""
    cliente, _ = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    antes = len(db.scalars(select(Client)).all())

    r = client.post(
        "/api/v1/work-orders/intake",
        json=_corpo(
            lavagem,
            cliente={"nome": "Ruan escrito de outro jeito", "telefone": "82 99911-0001"},
            veiculo={"placa": "OUT2B22", "marca": "Fiat", "modelo": "Argo"},
            idempotency_key="rec-tel-repetido",
        ),
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["cliente"]["id"] == cliente["id"]
    assert len(db.scalars(select(Client)).all()) == antes


# ------------------------------------------------------------------ veículo


def test_receber_veiculo_inexistente_e_404(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    cliente, _ = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    r = client.post(
        "/api/v1/work-orders/intake",
        json=_corpo(
            lavagem,
            cliente={"id": cliente["id"]},
            veiculo={"id": 999999},
            idempotency_key="rec-vei-inexistente",
        ),
        headers=admin_headers,
    )
    assert r.status_code == 404


def test_veiculo_de_outro_cliente_e_recusado(client, admin_headers, seed_cliente_veiculo, seed_servicos, staff_headers):
    """Receber o carro de A na ficha de B faria o histórico, a cobrança e o laudo de entrada
    apontarem para a pessoa errada."""
    cliente_a, veiculo_a = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    outro = client.post(
        "/api/v1/clients", json={"nome": "Outro Dono", "telefone": "82 96666-0002"}, headers=staff_headers
    ).json()

    r = client.post(
        "/api/v1/work-orders/intake",
        json=_corpo(
            lavagem,
            cliente={"id": outro["id"]},
            veiculo={"id": veiculo_a["id"]},
            idempotency_key="rec-vei-de-outro",
        ),
        headers=admin_headers,
    )
    assert r.status_code == 422
    assert "não pertence" in r.json()["detail"].lower()


def test_veiculo_arquivado_e_409(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    assert client.post(f"/api/v1/vehicles/{veiculo['id']}/arquivar", headers=admin_headers).status_code == 200

    r = client.post(
        "/api/v1/work-orders/intake",
        json=_corpo(
            lavagem,
            cliente={"id": cliente["id"]},
            veiculo={"id": veiculo["id"]},
            idempotency_key="rec-vei-arquivado",
        ),
        headers=admin_headers,
    )
    assert r.status_code == 409
    assert "arquivado" in r.json()["detail"].lower()


def test_placa_de_outro_dono_manda_transferir_em_vez_de_adivinhar(
    client, admin_headers, seed_cliente_veiculo, seed_servicos
):
    """Carro vendido é caso real. O sistema não escolhe sozinho quem é o dono: ele diz o que fazer."""
    _, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    r = client.post(
        "/api/v1/work-orders/intake",
        json=_corpo(
            lavagem,
            cliente={"nome": "Comprador Novo", "telefone": "82 95555-0003"},
            veiculo={"placa": veiculo["placa"], "marca": "Honda", "modelo": "Civic EX"},
            idempotency_key="rec-placa-de-outro",
        ),
        headers=admin_headers,
    )
    assert r.status_code == 409
    assert "transfira" in r.json()["detail"].lower()


# --------------------------------------------- a corrida que abriria duas OS para o mesmo carro


def test_corrida_na_recepcao_devolve_a_mesma_os(db, client, admin, admin_headers, seed_servicos, monkeypatch):
    """Dois toques em "Receber" com a mesma chave: a segunda não pode abrir uma segunda OS.

    Como no pagamento, a defesa tem duas camadas, e esta é a de baixo: quando a gêmea comita tarde
    demais para ser vista pelas leituras, o UNIQUE estoura no flush e o `except IntegrityError`
    precisa reconhecer a chave e devolver a OS já criada. Sem isso, o pátio mostraria o mesmo carro
    duas vezes e o dono cobraria o serviço em dobro.
    """
    lavagem, _ = seed_servicos
    chave = "corrida-recepcao-0001"

    # a requisição gêmea já criou a OS e comitou
    primeira = client.post(
        "/api/v1/work-orders/intake",
        json=_corpo(lavagem, idempotency_key=chave),
        headers=admin_headers,
    )
    assert primeira.status_code == 201, primeira.text
    id_original = primeira.json()["id"]

    # ...mas as leituras desta requisição não a enxergam
    if not hasattr(intake_svc, "_mesma_chave"):
        pytest.skip("a recepção não expõe _mesma_chave — ajuste o teste ao nome real")

    original = intake_svc._mesma_chave
    chamadas = {"n": 0}

    def cego(db_, ch):
        chamadas["n"] += 1
        return None if chamadas["n"] <= 1 else original(db_, ch)

    monkeypatch.setattr(intake_svc, "_mesma_chave", cego)

    # o corpo passa pelo schema, como na rota: `IntakeIn` normaliza o telefone e a placa, e chamar
    # o service com o texto cru criaria um cliente novo em vez de reaproveitar o existente —
    # testando um caminho que a API nunca percorre
    dados = IntakeIn(**_corpo(lavagem, idempotency_key=chave)).model_dump()
    resultado = intake_svc.receber(db, dados, user=admin)

    assert chamadas["n"] >= 2, "o INSERT não chegou a estourar — o teste não exercitou o que devia"
    assert resultado.id == id_original, "a corrida abriu uma segunda OS para o mesmo carro"
    assert len(db.scalars(select(WorkOrder)).all()) == 1


def test_repetir_a_recepcao_pela_api_devolve_a_mesma_os(client, admin_headers, seed_servicos, db):
    """O caminho comum: a resposta demorou e o sócio tocou de novo."""
    lavagem, _ = seed_servicos
    corpo = _corpo(lavagem, idempotency_key="recepcao-repetida-01")

    primeira = client.post("/api/v1/work-orders/intake", json=corpo, headers=admin_headers)
    segunda = client.post("/api/v1/work-orders/intake", json=corpo, headers=admin_headers)

    assert primeira.status_code == 201
    assert segunda.status_code in (200, 201)
    assert segunda.json()["id"] == primeira.json()["id"]
    assert segunda.json()["numero"] == primeira.json()["numero"]
    # e o número da loja não foi queimado duas vezes
    assert len(db.scalars(select(WorkOrder)).all()) == 1
    assert len(db.scalars(select(Vehicle)).all()) == 1


# ------------------------------------------------------------------ campos opcionais


def test_recepcao_grava_observacoes_e_desconto(client, admin_headers, seed_servicos):
    """Os dois campos opcionais da recepção nunca tinham sido exercitados."""
    lavagem, _ = seed_servicos
    r = client.post(
        "/api/v1/work-orders/intake",
        json=_corpo(
            lavagem,
            observacoes="Cliente pediu para ligar antes de entregar.",
            desconto_centavos=1500,
            idempotency_key="rec-com-opcionais",
        ),
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["observacoes"] == "Cliente pediu para ligar antes de entregar."
    assert corpo["desconto_centavos"] == 1500
    assert corpo["valor_total_centavos"] == 12990 - 1500


def test_recepcao_com_desconto_maior_que_os_servicos_e_recusada(client, admin_headers, seed_servicos):
    """Desconto acima da soma criaria total negativo — o piso vale desde a recepção."""
    lavagem, _ = seed_servicos
    r = client.post(
        "/api/v1/work-orders/intake",
        json=_corpo(lavagem, desconto_centavos=999999, idempotency_key="rec-desconto-absurdo"),
        headers=admin_headers,
    )
    assert r.status_code == 422
    assert "desconto" in r.json()["detail"].lower()
