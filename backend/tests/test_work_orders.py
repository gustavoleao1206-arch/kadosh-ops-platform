"""OS unificada: orçamento, agendamento, itens, totais, máquina de estados e eventos."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.services.periods import day_bounds, to_local, today_local


def _wo(client, headers, **over):
    body = {"client_id": over.pop("client_id"), **over}
    r = client.post("/api/v1/work-orders", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _transition(client, headers, wo_id, to, **kw):
    return client.post(f"/api/v1/work-orders/{wo_id}/transition", json={"to_status": to, **kw}, headers=headers)


# ------------------------------------------------------------------ criação


def test_orcamento_nasce_sem_veiculo_e_sem_data(client, staff_headers, seed_cliente_veiculo, seed_servicos):
    c, _ = seed_cliente_veiculo
    lavagem, polimento = seed_servicos
    wo = _wo(client, staff_headers, client_id=c["id"], itens=[{"service_id": lavagem["id"]}, {"service_id": polimento["id"]}])
    assert wo["status"] == "orcamento" and wo["status_label"] == "Orçamento"
    assert wo["numero"] is None and wo["vehicle_id"] is None
    # itens copiam nome e valor do catálogo
    assert [i["descricao"] for i in wo["itens"]] == ["Lavagem Simples", "Polimento Técnico"]
    assert wo["valor_total_centavos"] == 12990 + 99990
    assert [e["para"] for e in wo["eventos"] if e["tipo"] == "status"] == ["orcamento"]


def test_agendamento_exige_veiculo_e_data(client, staff_headers, seed_cliente_veiculo, seed_servicos):
    c, v = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    quando = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    wo = _wo(client, staff_headers, client_id=c["id"], vehicle_id=v["id"], scheduled_at=quando, itens=[{"service_id": lavagem["id"]}])
    assert wo["status"] == "agendado"
    # previsão = horário marcado + duração do serviço (60 min)
    assert datetime.fromisoformat(wo["previsao_conclusao"]) - datetime.fromisoformat(wo["scheduled_at"]) == timedelta(minutes=60)
    # sem veículo não agenda
    r = client.post("/api/v1/work-orders", json={"client_id": c["id"], "scheduled_at": quando}, headers=staff_headers)
    assert r.status_code == 422
    # status=agendado sem data é recusado na validação do schema
    r = client.post("/api/v1/work-orders", json={"client_id": c["id"], "vehicle_id": v["id"], "status": "agendado"}, headers=staff_headers)
    assert r.status_code == 422


def test_veiculo_precisa_ser_do_cliente(client, staff_headers, seed_cliente_veiculo, staff):
    c, v = seed_cliente_veiculo
    outro = client.post("/api/v1/clients", json={"nome": "Outro Dono", "telefone": "82 95555-1111"}, headers=staff_headers).json()
    r = client.post("/api/v1/work-orders", json={"client_id": outro["id"], "vehicle_id": v["id"]}, headers=staff_headers)
    assert r.status_code == 422


def test_cliente_ou_veiculo_arquivado_recusa(client, staff_headers, seed_cliente_veiculo):
    c, v = seed_cliente_veiculo
    client.post(f"/api/v1/vehicles/{v['id']}/arquivar", headers=staff_headers)
    r = client.post("/api/v1/work-orders", json={"client_id": c["id"], "vehicle_id": v["id"]}, headers=staff_headers)
    assert r.status_code == 409
    client.post(f"/api/v1/vehicles/{v['id']}/desarquivar", headers=staff_headers)
    client.post(f"/api/v1/clients/{c['id']}/arquivar", headers=staff_headers)
    r = client.post("/api/v1/work-orders", json={"client_id": c["id"]}, headers=staff_headers)
    assert r.status_code == 409


# ------------------------------------------------------------------ itens, desconto e total


def test_itens_desconto_e_total(client, staff_headers, seed_cliente_veiculo, seed_servicos):
    c, _ = seed_cliente_veiculo
    lavagem, polimento = seed_servicos
    wo = _wo(client, staff_headers, client_id=c["id"], itens=[{"service_id": lavagem["id"]}])
    assert wo["valor_total_centavos"] == 12990

    # preço negociado no balcão vale mais que o catálogo
    r = client.post(f"/api/v1/work-orders/{wo['id']}/items", json=[{"service_id": polimento["id"], "valor_centavos": 80000}], headers=staff_headers)
    assert r.status_code == 200 and r.json()["valor_total_centavos"] == 12990 + 80000

    r = client.patch(f"/api/v1/work-orders/{wo['id']}", json={"desconto_centavos": 2990}, headers=staff_headers)
    assert r.status_code == 200 and r.json()["valor_total_centavos"] == 12990 + 80000 - 2990

    # desconto maior que a soma dos itens não passa
    r = client.patch(f"/api/v1/work-orders/{wo['id']}", json={"desconto_centavos": 999999}, headers=staff_headers)
    assert r.status_code == 422

    item_id = r.json() if False else client.get(f"/api/v1/work-orders/{wo['id']}", headers=staff_headers).json()["itens"][0]["id"]
    r = client.delete(f"/api/v1/work-orders/{wo['id']}/items/{item_id}", headers=staff_headers)
    assert r.status_code == 200 and r.json()["valor_total_centavos"] == 80000 - 2990
    tipos = [e["tipo"] for e in r.json()["eventos"]]
    assert tipos.count("item") == 3 and "desconto" in tipos  # 2 adições + 1 remoção


def test_servico_desativado_nao_entra_sem_preco_explicito(client, admin_headers, staff_headers, seed_cliente_veiculo, seed_servicos):
    c, _ = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    client.patch(f"/api/v1/services/{lavagem['id']}", json={"ativo": False}, headers=admin_headers)
    r = client.post("/api/v1/work-orders", json={"client_id": c["id"], "itens": [{"service_id": lavagem["id"]}]}, headers=staff_headers)
    assert r.status_code == 409
    # com preço explícito (repetir um serviço antigo) é permitido
    r = client.post("/api/v1/work-orders", json={"client_id": c["id"], "itens": [{"service_id": lavagem["id"], "valor_centavos": 12990}]}, headers=staff_headers)
    assert r.status_code == 201


# ------------------------------------------------------------------ máquina de estados


def test_fluxo_agenda_ate_conclusao(client, staff_headers, seed_cliente_veiculo, seed_servicos):
    c, v = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    quando = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    wo = _wo(client, staff_headers, client_id=c["id"], vehicle_id=v["id"], scheduled_at=quando, itens=[{"service_id": lavagem["id"]}])
    assert {a["status"] for a in wo["acoes"]} == {"confirmado", "recebido", "cancelado", "nao_compareceu"}

    r = _transition(client, staff_headers, wo["id"], "confirmado", expected_status="agendado")
    assert r.status_code == 200 and r.json()["status"] == "confirmado"

    r = _transition(client, staff_headers, wo["id"], "recebido")
    body = r.json()
    assert r.status_code == 200 and body["numero"] == 1 and body["entrada"] is not None
    # previsão passa a contar da entrada
    assert datetime.fromisoformat(body["previsao_conclusao"]) > datetime.fromisoformat(body["entrada"])

    r = _transition(client, staff_headers, wo["id"], "concluido")  # salto direto: lavagem rápida
    assert r.status_code == 200 and r.json()["conclusao"] is not None
    assert [e["para"] for e in r.json()["eventos"] if e["tipo"] == "status"] == ["agendado", "confirmado", "recebido", "concluido"]


def test_transicao_invalida_e_concorrencia(client, staff_headers, seed_cliente_veiculo):
    c, v = seed_cliente_veiculo
    wo = _wo(client, staff_headers, client_id=c["id"], vehicle_id=v["id"], scheduled_at=datetime.now(timezone.utc).isoformat())
    assert _transition(client, staff_headers, wo["id"], "concluido").status_code == 409  # agendado → concluído não existe
    assert _transition(client, staff_headers, wo["id"], "agendado").status_code == 400  # já está
    assert _transition(client, staff_headers, wo["id"], "voando").status_code == 422
    # o outro aparelho mudou antes: 409 com instrução de recarregar
    r = _transition(client, staff_headers, wo["id"], "confirmado", expected_status="orcamento")
    assert r.status_code == 409 and "Recarregue" in r.json()["detail"]


def test_cancelar_exige_motivo_e_encerra(client, staff_headers, seed_cliente_veiculo):
    c, v = seed_cliente_veiculo
    wo = _wo(client, staff_headers, client_id=c["id"], vehicle_id=v["id"], scheduled_at=datetime.now(timezone.utc).isoformat())
    assert _transition(client, staff_headers, wo["id"], "cancelado").status_code == 422
    r = _transition(client, staff_headers, wo["id"], "cancelado", motivo="Cliente desistiu")
    assert r.status_code == 200 and r.json()["acoes"] == []
    assert [e["motivo"] for e in r.json()["eventos"] if e["para"] == "cancelado"] == ["Cliente desistiu"]
    # encerrada: não edita mais
    assert client.patch(f"/api/v1/work-orders/{wo['id']}", json={"observacoes": "x"}, headers=staff_headers).status_code == 409


def test_nao_compareceu_e_remarcacao(client, staff_headers, seed_cliente_veiculo):
    c, v = seed_cliente_veiculo
    wo = _wo(client, staff_headers, client_id=c["id"], vehicle_id=v["id"], scheduled_at=datetime.now(timezone.utc).isoformat())
    r = _transition(client, staff_headers, wo["id"], "nao_compareceu", motivo="Não apareceu")
    assert r.status_code == 200 and [a["status"] for a in r.json()["acoes"]] == ["agendado"]
    # remarcar exige data nova no futuro (a antiga já passou)
    r = _transition(client, staff_headers, wo["id"], "agendado")
    assert r.status_code == 422 and "nova data" in r.json()["detail"]
    nova = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    assert client.patch(f"/api/v1/work-orders/{wo['id']}", json={"scheduled_at": nova}, headers=staff_headers).status_code == 200
    r = _transition(client, staff_headers, wo["id"], "agendado")
    assert r.status_code == 200 and r.json()["status"] == "agendado"
    # serviços continuam congelados enquanto está como não compareceu — mas agora voltou a ser agendamento
    assert client.get(f"/api/v1/work-orders/{wo['id']}", headers=staff_headers).json()["status"] == "agendado"


def test_reabrir_concluida_e_so_do_admin(client, admin_headers, staff_headers, seed_cliente_veiculo):
    c, v = seed_cliente_veiculo
    wo = _wo(client, staff_headers, client_id=c["id"], vehicle_id=v["id"], scheduled_at=datetime.now(timezone.utc).isoformat())
    _transition(client, staff_headers, wo["id"], "recebido")
    _transition(client, staff_headers, wo["id"], "concluido")
    detalhe = client.get(f"/api/v1/work-orders/{wo['id']}", headers=staff_headers).json()
    assert detalhe["acoes"] == []  # staff não vê a reabertura
    assert _transition(client, staff_headers, wo["id"], "aguardando_retirada").status_code == 403
    r = _transition(client, admin_headers, wo["id"], "aguardando_retirada", motivo="Faltou detalhe")
    assert r.status_code == 200 and r.json()["conclusao"] is None


def test_orcamento_vira_agendamento(client, staff_headers, seed_cliente_veiculo, seed_servicos):
    c, v = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    wo = _wo(client, staff_headers, client_id=c["id"], itens=[{"service_id": lavagem["id"]}])
    # aprovar o orçamento: define veículo e data, depois muda o status
    quando = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    r = client.patch(f"/api/v1/work-orders/{wo['id']}", json={"vehicle_id": v["id"], "scheduled_at": quando}, headers=staff_headers)
    assert r.status_code == 200
    r = _transition(client, staff_headers, wo["id"], "agendado", expected_status="orcamento")
    assert r.status_code == 200 and r.json()["status"] == "agendado"
    assert r.json()["numero"] is None  # orçamento e agendamento não consomem número


def test_numero_so_na_recepcao_e_sequencial(client, staff_headers, seed_cliente_veiculo):
    c, v = seed_cliente_veiculo
    ids = []
    for _ in range(3):
        wo = _wo(client, staff_headers, client_id=c["id"], vehicle_id=v["id"], scheduled_at=datetime.now(timezone.utc).isoformat())
        ids.append(wo["id"])
    # só o segundo é recebido
    r = _transition(client, staff_headers, ids[1], "recebido")
    assert r.json()["numero"] == 1
    r = _transition(client, staff_headers, ids[2], "recebido")
    assert r.json()["numero"] == 2
    assert client.get(f"/api/v1/work-orders/{ids[0]}", headers=staff_headers).json()["numero"] is None


# ------------------------------------------------------------------ agenda e listagem


def test_agenda_do_dia_usa_fuso_do_negocio(client, staff_headers, seed_cliente_veiculo):
    c, v = seed_cliente_veiculo
    hoje = today_local()
    ini, fim = day_bounds(hoje)
    # 00:30 local (03:30 UTC) e 23:30 local — os dois são "hoje" em Maceió
    cedo = (ini + timedelta(minutes=30)).isoformat()
    tarde = (fim - timedelta(minutes=30)).isoformat()
    ontem_tarde = (ini - timedelta(minutes=30)).isoformat()
    for quando in (cedo, tarde, ontem_tarde):
        _wo(client, staff_headers, client_id=c["id"], vehicle_id=v["id"], scheduled_at=quando)

    r = client.get("/api/v1/agenda", headers=staff_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["dia"] == hoje.isoformat()
    assert len(body["itens"]) == 2
    assert body["resumo"]["agendados"] == 2 and body["resumo"]["no_patio"] == 0
    # a agenda vem em ordem de horário
    assert body["itens"][0]["scheduled_at"] < body["itens"][1]["scheduled_at"]
    # ontem tem um
    r = client.get(f"/api/v1/agenda?dia={(hoje - timedelta(days=1)).isoformat()}", headers=staff_headers)
    assert len(r.json()["itens"]) == 1


def test_agenda_ignora_orcamento_e_conta_patio(client, staff_headers, seed_cliente_veiculo, seed_servicos):
    c, v = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    _wo(client, staff_headers, client_id=c["id"], itens=[{"service_id": lavagem["id"]}])  # orçamento
    wo = _wo(client, staff_headers, client_id=c["id"], vehicle_id=v["id"], scheduled_at=datetime.now(timezone.utc).isoformat())
    _transition(client, staff_headers, wo["id"], "recebido")
    body = client.get("/api/v1/agenda", headers=staff_headers).json()
    assert body["resumo"]["orcamentos_abertos"] == 1 and body["resumo"]["no_patio"] == 1
    assert [i["status"] for i in body["itens"]] == ["recebido"]  # o recebido continua na agenda do dia


def test_lista_com_filtros(client, staff_headers, seed_cliente_veiculo, seed_servicos):
    c, v = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    _wo(client, staff_headers, client_id=c["id"], itens=[{"service_id": lavagem["id"]}])
    wo = _wo(client, staff_headers, client_id=c["id"], vehicle_id=v["id"], scheduled_at=datetime.now(timezone.utc).isoformat())
    assert client.get("/api/v1/work-orders", headers=staff_headers).json()["total"] == 2
    assert client.get("/api/v1/work-orders?status=orcamento", headers=staff_headers).json()["total"] == 1
    assert client.get(f"/api/v1/work-orders?client_id={c['id']}", headers=staff_headers).json()["total"] == 2
    assert client.get(f"/api/v1/work-orders?vehicle_id={v['id']}", headers=staff_headers).json()["total"] == 1
    assert client.get("/api/v1/work-orders?q=BRA2E19", headers=staff_headers).json()["total"] == 1
    assert client.get("/api/v1/work-orders?q=ruan", headers=staff_headers).json()["total"] == 2
    hoje = today_local().isoformat()
    assert client.get(f"/api/v1/work-orders?de={hoje}&ate={hoje}", headers=staff_headers).json()["total"] >= 1
    # a OS aparece no histórico do cliente e do veículo (fase 2)
    ficha = client.get(f"/api/v1/clients/{c['id']}", headers=staff_headers).json()
    assert len(ficha["historico"]) == 2
    assert client.get(f"/api/v1/vehicles/{v['id']}", headers=staff_headers).json()["historico"][0]["id"] == wo["id"]


# ------------------------------------------------------------------ exclusão e permissões


def test_excluir_so_admin_e_so_antes_da_recepcao(client, admin_headers, staff_headers, seed_cliente_veiculo):
    c, v = seed_cliente_veiculo
    wo = _wo(client, staff_headers, client_id=c["id"], vehicle_id=v["id"], scheduled_at=datetime.now(timezone.utc).isoformat())
    assert client.delete(f"/api/v1/work-orders/{wo['id']}", headers=staff_headers).status_code == 403
    outra = _wo(client, staff_headers, client_id=c["id"], vehicle_id=v["id"], scheduled_at=datetime.now(timezone.utc).isoformat())
    _transition(client, staff_headers, outra["id"], "recebido")
    assert client.delete(f"/api/v1/work-orders/{outra['id']}", headers=admin_headers).status_code == 409
    assert client.delete(f"/api/v1/work-orders/{wo['id']}", headers=admin_headers).status_code == 204


def test_previsao_manual_para_de_ser_recalculada(client, staff_headers, seed_cliente_veiculo, seed_servicos):
    c, v = seed_cliente_veiculo
    lavagem, polimento = seed_servicos
    quando = datetime.now(timezone.utc).replace(microsecond=0)
    wo = _wo(client, staff_headers, client_id=c["id"], vehicle_id=v["id"], scheduled_at=quando.isoformat(), itens=[{"service_id": lavagem["id"]}])
    manual = (quando + timedelta(hours=5)).isoformat()
    r = client.patch(f"/api/v1/work-orders/{wo['id']}", json={"previsao_conclusao": manual}, headers=staff_headers)
    assert r.status_code == 200
    r = client.post(f"/api/v1/work-orders/{wo['id']}/items", json=[{"service_id": polimento["id"]}], headers=staff_headers)
    assert datetime.fromisoformat(r.json()["previsao_conclusao"]) == datetime.fromisoformat(manual)


@pytest.mark.parametrize(
    "method,path,body",
    [("GET", "/api/v1/agenda", None), ("GET", "/api/v1/work-orders", None), ("POST", "/api/v1/work-orders", {"client_id": 1})],
)
def test_requer_login(client, method, path, body):
    assert client.request(method, path, json=body).status_code == 401


# ------------------------------------------------------------------ correções da revisão


def test_agenda_mostra_quem_esta_no_patio(client, staff_headers, seed_cliente_veiculo):
    """Carro recebido (com ou sem agendamento) aparece na agenda enquanto estiver no pátio."""
    c, v = seed_cliente_veiculo
    ontem = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    wo = _wo(client, staff_headers, client_id=c["id"], vehicle_id=v["id"], scheduled_at=ontem)
    _transition(client, staff_headers, wo["id"], "recebido")
    body = client.get("/api/v1/agenda", headers=staff_headers).json()
    assert [i["id"] for i in body["itens"]] == [wo["id"]]  # marcado ontem, mas ainda está aqui
    assert body["resumo"]["no_patio"] == 1
    # concluído continua na agenda do dia em que entrou (o que passou pelo pátio hoje)
    _transition(client, staff_headers, wo["id"], "concluido")
    assert len(client.get("/api/v1/agenda", headers=staff_headers).json()["itens"]) == 1
    amanha = (today_local() + timedelta(days=1)).isoformat()
    assert client.get(f"/api/v1/agenda?dia={amanha}", headers=staff_headers).json()["itens"] == []


def test_orcamento_sem_veiculo_nao_oferece_receber(client, staff_headers, seed_cliente_veiculo, seed_servicos):
    """Botão que só levaria a 422 não é oferecido — e a numeração não ganha buracos."""
    c, v = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    orc = _wo(client, staff_headers, client_id=c["id"], itens=[{"service_id": lavagem["id"]}])
    assert [a["status"] for a in orc["acoes"]] == ["cancelado"]  # nem "agendar" nem "receber" sem veículo
    assert _transition(client, staff_headers, orc["id"], "recebido").status_code == 422
    # a sequence não foi consumida: a próxima OS recebida é a de número 1
    outra = _wo(client, staff_headers, client_id=c["id"], vehicle_id=v["id"], scheduled_at=datetime.now(timezone.utc).isoformat())
    assert _transition(client, staff_headers, outra["id"], "recebido").json()["numero"] == 1


def test_remarcar_gera_evento_e_derruba_confirmacao(client, staff_headers, seed_cliente_veiculo):
    c, v = seed_cliente_veiculo
    wo = _wo(client, staff_headers, client_id=c["id"], vehicle_id=v["id"], scheduled_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
    _transition(client, staff_headers, wo["id"], "confirmado")
    nova = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    r = client.patch(f"/api/v1/work-orders/{wo['id']}", json={"scheduled_at": nova}, headers=staff_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "agendado"  # a confirmação valia para a data antiga
    tipos = [e["tipo"] for e in body["eventos"]]
    assert "remarcacao" in tipos
    assert any("Remarcado:" in e["descricao"] for e in body["eventos"])


def test_reabrir_exige_motivo_e_registra(client, admin_headers, staff_headers, seed_cliente_veiculo):
    c, v = seed_cliente_veiculo
    wo = _wo(client, staff_headers, client_id=c["id"], vehicle_id=v["id"], scheduled_at=datetime.now(timezone.utc).isoformat())
    _transition(client, staff_headers, wo["id"], "recebido")
    _transition(client, staff_headers, wo["id"], "concluido")
    assert _transition(client, admin_headers, wo["id"], "aguardando_retirada").status_code == 422
    r = _transition(client, admin_headers, wo["id"], "aguardando_retirada", motivo="Faltou passar cera")
    assert r.status_code == 200
    reabertura = [e for e in r.json()["eventos"] if e["tipo"] == "reabertura"]
    assert len(reabertura) == 1 and reabertura[0]["motivo"] == "Faltou passar cera"
    assert reabertura[0]["de"] is not None  # guardou a conclusão apagada


def test_remover_item_com_desconto_avisa_em_vez_de_falhar(client, staff_headers, seed_cliente_veiculo, seed_servicos):
    c, _ = seed_cliente_veiculo
    lavagem, polimento = seed_servicos
    wo = _wo(client, staff_headers, client_id=c["id"], itens=[{"service_id": lavagem["id"]}, {"service_id": polimento["id"]}])
    client.patch(f"/api/v1/work-orders/{wo['id']}", json={"desconto_centavos": 20000}, headers=staff_headers)
    item = wo["itens"][1]["id"]  # remover o polimento deixaria a soma abaixo do desconto
    r = client.delete(f"/api/v1/work-orders/{wo['id']}/items/{item}", headers=staff_headers)
    assert r.status_code == 409 and "Reduza o desconto" in r.json()["detail"]
    # o item continua lá
    assert len(client.get(f"/api/v1/work-orders/{wo['id']}", headers=staff_headers).json()["itens"]) == 2


def test_data_sem_fuso_vira_horario_do_negocio(client, staff_headers, seed_cliente_veiculo):
    """O app pode mandar '2026-09-10T09:00' sem offset: é 9h em Maceió, não em UTC."""
    c, v = seed_cliente_veiculo
    r = client.post(
        "/api/v1/work-orders",
        json={"client_id": c["id"], "vehicle_id": v["id"], "scheduled_at": "2026-09-10T09:00:00"},
        headers=staff_headers,
    )
    assert r.status_code == 201
    # o que importa é o INSTANTE: 9h em Maceió (UTC-3) = 12h UTC, independente do fuso do servidor
    marcado = datetime.fromisoformat(r.json()["scheduled_at"])
    assert marcado.astimezone(timezone.utc) == datetime(2026, 9, 10, 12, tzinfo=timezone.utc)
    body = client.get("/api/v1/agenda?dia=2026-09-10", headers=staff_headers).json()
    assert len(body["itens"]) == 1


# ------------------------------------------------------------------ recepção (fase 4)


def _intake(client, headers, **over):
    # a chave virou obrigatória na API; quem não se importa com ela ganha uma gerada
    body = {
        "cliente": {"nome": "Chegou Agora", "telefone": "82 96666-1111"},
        "veiculo": {"modelo": "Gol", "placa": "NEW1A11"},
        "idempotency_key": uuid4().hex,
        **over,
    }
    return client.post("/api/v1/work-orders/intake", json=body, headers=headers)


def test_recepcao_cria_cliente_veiculo_e_os_numa_transacao(client, staff_headers, seed_servicos):
    lavagem, _ = seed_servicos
    r = _intake(client, staff_headers, itens=[{"service_id": lavagem["id"]}], observacoes_entrada="Risco no para-choque traseiro")
    assert r.status_code == 201, r.text
    wo = r.json()
    assert wo["status"] == "recebido" and wo["numero"] == 1 and wo["entrada"]
    assert wo["cliente"]["nome"] == "Chegou Agora" and wo["cliente"]["telefone"] == "5582966661111"
    assert wo["veiculo"]["placa"] == "NEW1A11"
    assert wo["observacoes_entrada"] == "Risco no para-choque traseiro"
    assert wo["valor_total_centavos"] == 12990
    assert client.get("/api/v1/clients", headers=staff_headers).json()["total"] == 1


def test_recepcao_falha_nao_deixa_rastro(client, staff_headers):
    """Serviço inexistente: nem cliente, nem veículo, nem OS são criados."""
    r = _intake(client, staff_headers, itens=[{"service_id": 9999}])
    assert r.status_code == 404
    assert client.get("/api/v1/clients", headers=staff_headers).json()["total"] == 0
    assert client.get("/api/v1/vehicles", headers=staff_headers).json()["total"] == 0
    assert client.get("/api/v1/work-orders", headers=staff_headers).json()["total"] == 0


def test_recepcao_reaproveita_cliente_e_veiculo_existentes(client, staff_headers, seed_cliente_veiculo):
    c, v = seed_cliente_veiculo
    r = _intake(client, staff_headers, cliente={"id": c["id"]}, veiculo={"id": v["id"]})
    assert r.status_code == 201
    assert client.get("/api/v1/clients", headers=staff_headers).json()["total"] == 1
    # mesmo telefone digitado de novo não duplica o cliente
    r = _intake(client, staff_headers, cliente={"nome": "Ruan de novo", "telefone": "82 99911-0001"}, veiculo={"modelo": "Outro"})
    assert r.status_code == 201 and r.json()["cliente"]["id"] == c["id"]
    assert client.get("/api/v1/clients", headers=staff_headers).json()["total"] == 1


def test_recepcao_placa_de_outro_dono_avisa(client, staff_headers, seed_cliente_veiculo):
    _, v = seed_cliente_veiculo
    r = _intake(client, staff_headers, veiculo={"modelo": "Civic", "placa": v["placa"]})
    assert r.status_code == 409 and "outro cliente" in r.json()["detail"]


def test_recepcao_e_idempotente(client, staff_headers):
    r1 = _intake(client, staff_headers, idempotency_key="abc-12345")
    r2 = _intake(client, staff_headers, idempotency_key="abc-12345")
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"]
    assert client.get("/api/v1/work-orders", headers=staff_headers).json()["total"] == 1


def test_recepcao_de_agendamento_nao_cria_outra_os(client, staff_headers, seed_cliente_veiculo, seed_servicos):
    c, v = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    ag = _wo(client, staff_headers, client_id=c["id"], vehicle_id=v["id"], scheduled_at=datetime.now(timezone.utc).isoformat(), itens=[{"service_id": lavagem["id"]}])
    r = client.post(
        "/api/v1/work-orders/intake",
        json={"work_order_id": ag["id"], "cliente": {"id": c["id"]}, "veiculo": {"id": v["id"]}, "observacoes_entrada": "Tanque pela metade", "idempotency_key": uuid4().hex},
        headers=staff_headers,
    )
    assert r.status_code == 201 and r.json()["id"] == ag["id"] and r.json()["numero"] == 1
    assert client.get("/api/v1/work-orders", headers=staff_headers).json()["total"] == 1
    # já recebida: recusa receber de novo
    r = client.post(
        "/api/v1/work-orders/intake",
        json={"work_order_id": ag["id"], "cliente": {"id": c["id"]}, "veiculo": {"id": v["id"]}, "idempotency_key": uuid4().hex},
        headers=staff_headers,
    )
    assert r.status_code == 409


def test_patio_agrupa_por_status(client, staff_headers):
    a = _intake(client, staff_headers, idempotency_key="p1-000001").json()
    b = _intake(client, staff_headers, cliente={"nome": "Outro", "telefone": "82 95555-2222"}, veiculo={"modelo": "Onix", "placa": "OUT2B22"}, idempotency_key="p2-000001").json()
    _transition(client, staff_headers, b["id"], "em_execucao")
    body = client.get("/api/v1/patio", headers=staff_headers).json()
    assert [w["id"] for w in body["recebido"]] == [a["id"]]
    assert [w["id"] for w in body["em_execucao"]] == [b["id"]]
    assert body["aguardando_retirada"] == []
    _transition(client, staff_headers, a["id"], "concluido")
    assert client.get("/api/v1/patio", headers=staff_headers).json()["recebido"] == []


def test_observacoes_de_entrada_congelam_apos_iniciar(client, admin_headers, staff_headers):
    wo = _intake(client, staff_headers, observacoes_entrada="Sem avarias").json()
    r = client.patch(f"/api/v1/work-orders/{wo['id']}", json={"observacoes_entrada": "Risco na porta"}, headers=staff_headers)
    assert r.status_code == 200  # ainda recebido: pode corrigir
    _transition(client, staff_headers, wo["id"], "em_execucao")
    r = client.patch(f"/api/v1/work-orders/{wo['id']}", json={"observacoes_entrada": "Nada aqui"}, headers=staff_headers)
    assert r.status_code == 403
    r = client.patch(f"/api/v1/work-orders/{wo['id']}", json={"observacoes_entrada": "Corrigido pelo dono"}, headers=admin_headers)
    assert r.status_code == 200


def test_recepcao_valida_dados_minimos(client, staff_headers):
    r = client.post("/api/v1/work-orders/intake", json={"cliente": {}, "veiculo": {"modelo": "X"}, "idempotency_key": uuid4().hex}, headers=staff_headers)
    assert r.status_code == 422
    r = client.post("/api/v1/work-orders/intake", json={"cliente": {"nome": "Alguém"}, "veiculo": {}, "idempotency_key": uuid4().hex}, headers=staff_headers)
    assert r.status_code == 422


def test_acoes_vem_na_ordem_do_fluxo_com_um_destaque(client, staff_headers, seed_cliente_veiculo):
    """A barra de ações é desenhada pela API: ordem do fluxo e um único botão em destaque."""
    c, v = seed_cliente_veiculo
    wo = _wo(client, staff_headers, client_id=c["id"], vehicle_id=v["id"], scheduled_at=datetime.now(timezone.utc).isoformat())
    recebida = _transition(client, staff_headers, wo["id"], "recebido").json()
    assert [a["status"] for a in recebida["acoes"]] == ["em_execucao", "aguardando_retirada", "concluido", "cancelado"]
    assert [a["status"] for a in recebida["acoes"] if a["principal"]] == ["em_execucao"]

    executando = _transition(client, staff_headers, wo["id"], "em_execucao").json()
    assert [a["status"] for a in executando["acoes"] if a["principal"]] == ["aguardando_retirada"]
    # voltar um passo ganha o verbo do caminho de volta — não "receber" um carro que já está no pátio
    volta = next(a for a in executando["acoes"] if a["status"] == "recebido")
    assert volta["acao_label"] == "Voltar para a fila"

    pronta = _transition(client, staff_headers, wo["id"], "aguardando_retirada").json()
    assert [a["status"] for a in pronta["acoes"] if a["principal"]] == ["concluido"]

    # encerrada: reabrir é um passo para trás, nunca destaque
    concluida = _transition(client, staff_headers, wo["id"], "concluido").json()
    assert all(not a["principal"] for a in concluida["acoes"])


def test_passo_natural_indisponivel_promove_o_proximo(client, staff_headers, seed_cliente_veiculo, seed_servicos):
    """Orçamento sem data não pode ser agendado: o destaque cai em receber, não some."""
    c, v = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    orc = _wo(client, staff_headers, client_id=c["id"], vehicle_id=v["id"], itens=[{"service_id": lavagem["id"]}])
    assert [a["status"] for a in orc["acoes"] if a["principal"]] == ["recebido"]


def test_recepcao_de_agendamento_sem_repetir_cliente_e_veiculo(client, staff_headers, seed_cliente_veiculo, seed_servicos):
    """Recebendo um agendamento, cliente e veículo já estão na OS — o balcão só manda o que mudou."""
    c, v = seed_cliente_veiculo
    lavagem, polimento = seed_servicos
    ag = _wo(
        client,
        staff_headers,
        client_id=c["id"],
        vehicle_id=v["id"],
        scheduled_at=datetime.now(timezone.utc).isoformat(),
        itens=[{"service_id": lavagem["id"]}],
    )
    r = client.post(
        "/api/v1/work-orders/intake",
        json={
            "work_order_id": ag["id"],
            "itens": [{"service_id": polimento["id"]}],
            "observacoes_entrada": "Risco no para-choque",
            "idempotency_key": uuid4().hex,
        },
        headers=staff_headers,
    )
    assert r.status_code == 201, r.text
    wo = r.json()
    assert wo["id"] == ag["id"] and wo["vehicle_id"] == v["id"]
    assert wo["observacoes_entrada"] == "Risco no para-choque"
    # o serviço lançado na chegada entra junto do que já estava marcado
    assert [i["descricao"] for i in wo["itens"]] == ["Lavagem Simples", "Polimento Técnico"]
    assert wo["valor_total_centavos"] == 12990 + 99990


def test_recepcao_de_agendamento_troca_o_carro_que_chegou(client, staff_headers, seed_cliente_veiculo):
    """Marcou com o Corolla, apareceu com outro carro: a OS passa a apontar para o que chegou."""
    c, v = seed_cliente_veiculo
    ag = _wo(client, staff_headers, client_id=c["id"], vehicle_id=v["id"], scheduled_at=datetime.now(timezone.utc).isoformat())
    r = client.post(
        "/api/v1/work-orders/intake",
        json={"work_order_id": ag["id"], "veiculo": {"modelo": "Saveiro", "placa": "SAV1A11"}, "idempotency_key": uuid4().hex},
        headers=staff_headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["veiculo"]["placa"] == "SAV1A11"
    # o carro novo ficou no cadastro do mesmo cliente
    veiculos = client.get(f"/api/v1/clients/{c['id']}/vehicles", headers=staff_headers).json()
    assert {x["placa"] for x in veiculos} == {v["placa"], "SAV1A11"}


def test_recepcao_de_orcamento_sem_veiculo_avisa(client, staff_headers, seed_cliente_veiculo, seed_servicos):
    """Orçamento não tem carro: receber sem dizer qual chegou é erro claro, não 500."""
    c, _ = seed_cliente_veiculo
    lavagem, _s = seed_servicos
    orc = _wo(client, staff_headers, client_id=c["id"], itens=[{"service_id": lavagem["id"]}])
    r = client.post("/api/v1/work-orders/intake", json={"work_order_id": orc["id"], "idempotency_key": uuid4().hex}, headers=staff_headers)
    assert r.status_code == 422
    assert "veículo" in r.json()["detail"].lower()


def test_recepcao_sem_os_ainda_exige_cliente_e_veiculo(client, staff_headers):
    r = client.post("/api/v1/work-orders/intake", json={"veiculo": {"modelo": "Gol"}, "idempotency_key": uuid4().hex}, headers=staff_headers)
    assert r.status_code == 422


# ------------------------------------------------------------------ correções da revisão da fase 4


def test_laudo_de_entrada_longo_cabe_no_historico(client, admin_headers, staff_headers):
    """Um laudo de verdade tem várias linhas — o evento guarda o texto inteiro, não 120 caracteres."""
    longo = "Risco no para-choque traseiro; amassado na porta do motorista; " * 20
    wo = _intake(client, staff_headers, observacoes_entrada=longo[:1900]).json()
    r = client.patch(f"/api/v1/work-orders/{wo['id']}", json={"observacoes_entrada": "Corrigido"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert longo[:1900].strip() in [e["descricao"] for e in r.json()["eventos"] if e["tipo"] == "entrada"][-1]


def test_laudo_de_entrada_nao_se_reescreve_voltando_para_a_fila(client, admin_headers, staff_headers, seed_servicos):
    """A trava vale pelo histórico: voltar a OS para "recebido" não reabre o laudo para o staff."""
    lavagem, _ = seed_servicos
    wo = _intake(client, staff_headers, itens=[{"service_id": lavagem["id"]}], observacoes_entrada="Risco no para-choque").json()
    _transition(client, staff_headers, wo["id"], "em_execucao")
    # a porta dos fundos: devolver para a fila e editar como se nada tivesse começado
    assert _transition(client, staff_headers, wo["id"], "recebido").status_code == 200
    r = client.patch(f"/api/v1/work-orders/{wo['id']}", json={"observacoes_entrada": "Sem avarias"}, headers=staff_headers)
    assert r.status_code == 403
    assert client.get(f"/api/v1/work-orders/{wo['id']}", headers=staff_headers).json()["observacoes_entrada"] == "Risco no para-choque"
    # o dono pode corrigir — e a correção fica no histórico
    r = client.patch(f"/api/v1/work-orders/{wo['id']}", json={"observacoes_entrada": "Risco já existia"}, headers=admin_headers)
    assert r.status_code == 200
    eventos = [e for e in r.json()["eventos"] if e["tipo"] == "entrada"]
    assert [e["para"] for e in eventos] == ["registrado", "alterado"]
    # o laudo antigo fica guardado por inteiro — é ele a prova numa reclamação
    assert eventos[-1]["descricao"] == "Estado do carro na chegada alterado — Antes: Risco no para-choque"


def test_orcamento_sem_veiculo_pode_ser_cancelado(client, staff_headers, seed_cliente_veiculo, seed_servicos):
    """Cliente recusou o orçamento: sem carro nenhum, ele ainda precisa ter uma saída."""
    c, _ = seed_cliente_veiculo
    lavagem, _s = seed_servicos
    orc = _wo(client, staff_headers, client_id=c["id"], itens=[{"service_id": lavagem["id"]}])
    assert [a["status"] for a in orc["acoes"]] == ["cancelado"]
    r = _transition(client, staff_headers, orc["id"], "cancelado", motivo="Cliente achou caro")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelado"


def test_carro_sem_servico_nao_nasce_atrasado(client, staff_headers, seed_servicos):
    """Recepção sem itens não tem duração: prever "agora" faria o carro chegar já atrasado."""
    lavagem, _ = seed_servicos
    wo = _intake(client, staff_headers).json()
    assert wo["previsao_conclusao"] is None
    # lançado o serviço, a previsão aparece; removido, some de novo
    com_item = client.post(f"/api/v1/work-orders/{wo['id']}/items", json=[{"service_id": lavagem["id"]}], headers=staff_headers).json()
    assert com_item["previsao_conclusao"] is not None
    item_id = com_item["itens"][0]["id"]
    sem_item = client.delete(f"/api/v1/work-orders/{wo['id']}/items/{item_id}", headers=staff_headers).json()
    assert sem_item["previsao_conclusao"] is None


def test_recepcao_recusada_nao_queima_o_numero(client, staff_headers):
    """nextval não volta atrás no rollback: o número só sai quando nada mais pode falhar."""
    assert _intake(client, staff_headers, itens=[{"service_id": 9999}]).status_code == 404
    assert _intake(client, staff_headers, veiculo={"modelo": "Gol", "placa": "OUT9Z99"}).json()["numero"] == 1


def test_previsao_do_intake_sem_fuso_e_horario_da_loja(client, staff_headers):
    """O aparelho manda "2026-09-10T15:00" sem offset: são 15h em Maceió, não em Londres."""
    r = _intake(client, staff_headers, previsao_conclusao="2026-09-10T15:00:00")
    assert r.status_code == 201, r.text
    previsao = datetime.fromisoformat(r.json()["previsao_conclusao"])
    assert to_local(previsao).strftime("%d/%m %H:%M") == "10/09 15:00"


def test_voltar_para_a_fila_continua_sendo_transicao(client, staff_headers, seed_servicos):
    """O botão de volta (em_execucao → recebido) não passa pela recepção: a OS já entrou."""
    lavagem, _ = seed_servicos
    wo = _intake(client, staff_headers, itens=[{"service_id": lavagem["id"]}]).json()
    _transition(client, staff_headers, wo["id"], "em_execucao")
    r = _transition(client, staff_headers, wo["id"], "recebido")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "recebido" and r.json()["numero"] == wo["numero"]
    # e a recepção recusa mesmo, que é o que o painel faria se desviasse para lá
    assert client.post(
        "/api/v1/work-orders/intake", json={"work_order_id": wo["id"], "idempotency_key": uuid4().hex}, headers=staff_headers
    ).status_code == 409


def test_trocar_veiculo_com_carro_no_patio_e_so_do_admin_e_vira_evento(client, admin_headers, staff_headers, seed_cliente_veiculo):
    """O laudo de entrada é do carro que chegou: trocar o veículo depois some com a prova."""
    c, v = seed_cliente_veiculo
    wo = _intake(
        client,
        staff_headers,
        cliente={"id": c["id"]},
        veiculo={"id": v["id"]},
        observacoes_entrada="Risco na porta",
    ).json()
    outro = client.post(
        "/api/v1/vehicles",
        json={"client_id": c["id"], "modelo": "Fachada", "placa": "FAC1A11"},
        headers=admin_headers,
    ).json()
    r = client.patch(f"/api/v1/work-orders/{wo['id']}", json={"vehicle_id": outro["id"]}, headers=staff_headers)
    assert r.status_code == 403
    r = client.patch(f"/api/v1/work-orders/{wo['id']}", json={"vehicle_id": outro["id"]}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["vehicle_id"] == outro["id"]
    assert [e["descricao"] for e in r.json()["eventos"] if e["tipo"] == "transferencia"] == ["Veículo da OS trocado"]


def test_recepcao_com_work_order_id_invalido_nao_quebra(client, staff_headers):
    assert _intake(client, staff_headers, work_order_id=0).status_code == 422
    assert _intake(client, staff_headers, work_order_id=999999).status_code == 404


def test_patio_e_agenda_trazem_as_acoes_de_cada_carro(client, staff_headers, seed_servicos):
    """O celular desenha o botão de status no próprio card: sem `acoes` na lista, ele teria de
    buscar OS por OS ou reimplementar TRANSITIONS — que é o que a casa proíbe."""
    lavagem, _ = seed_servicos
    wo = _intake(client, staff_headers, itens=[{"service_id": lavagem["id"]}]).json()

    patio = client.get("/api/v1/patio", headers=staff_headers).json()
    card = patio["recebido"][0]
    assert card["id"] == wo["id"]
    assert [a["status"] for a in card["acoes"] if a["principal"]] == ["em_execucao"]
    assert card["acoes"][0]["acao_label"] == "Iniciar execução"

    # o mesmo vale para a agenda e para a listagem
    agenda = client.get("/api/v1/agenda", headers=staff_headers).json()
    assert all("acoes" in i for i in agenda["itens"])
    lista = client.get("/api/v1/work-orders", headers=staff_headers).json()
    assert all("acoes" in i for i in lista["items"])


def test_acoes_da_lista_respeitam_o_papel(client, admin_headers, staff_headers, seed_servicos):
    """Reabrir OS concluída é só do admin — e a lista tem de dizer isso para cada usuário."""
    lavagem, _ = seed_servicos
    wo = _intake(client, staff_headers, itens=[{"service_id": lavagem["id"]}]).json()
    _transition(client, staff_headers, wo["id"], "concluido")

    def acoes(headers):
        itens = client.get("/api/v1/work-orders", params={"status": "concluido"}, headers=headers).json()["items"]
        return [a["status"] for a in next(i for i in itens if i["id"] == wo["id"])["acoes"]]

    assert acoes(staff_headers) == []
    assert acoes(admin_headers) == ["aguardando_retirada"]


def test_lancar_servico_duas_vezes_com_a_mesma_chave_nao_dobra_o_total(client, staff_headers, seed_servicos):
    """Era a única mutação que criava valor do nada: o toque repetido lançava o serviço de novo."""
    lavagem, _ = seed_servicos
    wo = _intake(client, staff_headers).json()
    corpo = [{"service_id": lavagem["id"], "idempotency_key": "item-0001"}]

    a = client.post(f"/api/v1/work-orders/{wo['id']}/items", json=corpo, headers=staff_headers)
    b = client.post(f"/api/v1/work-orders/{wo['id']}/items", json=corpo, headers=staff_headers)
    assert a.status_code == 200 and b.status_code == 200
    assert len(b.json()["itens"]) == 1
    assert b.json()["valor_total_centavos"] == 12990

    # sem chave, cada envio é um lançamento novo — dois do mesmo serviço é caso legítimo
    client.post(
        f"/api/v1/work-orders/{wo['id']}/items", json=[{"service_id": lavagem["id"]}], headers=staff_headers
    )
    depois = client.get(f"/api/v1/work-orders/{wo['id']}", headers=staff_headers).json()
    assert len(depois["itens"]) == 2 and depois["valor_total_centavos"] == 12990 * 2


def test_recepcao_sem_chave_de_idempotencia_recusa(client, staff_headers):
    """A chave deixou de ser opcional: depender da disciplina de cada cliente era o buraco."""
    r = client.post(
        "/api/v1/work-orders/intake",
        json={"cliente": {"nome": "Sem Chave", "telefone": "82 90000-0000"}, "veiculo": {"modelo": "Gol"}},
        headers=staff_headers,
    )
    assert r.status_code == 422


def test_chave_de_item_vazia_recusa(client, staff_headers, seed_servicos):
    """String vazia passava pela checagem, era gravada, e o SEGUNDO item vazio estourava o UNIQUE.

    O sintoma seria 409 num lançamento legítimo, sem nada de errado com ele.
    """
    lavagem, _ = seed_servicos
    wo = _intake(client, staff_headers).json()
    r = client.post(
        f"/api/v1/work-orders/{wo['id']}/items",
        json=[{"service_id": lavagem["id"], "idempotency_key": ""}],
        headers=staff_headers,
    )
    assert r.status_code == 422


def test_chave_de_item_de_outra_os_recusa(client, staff_headers, seed_servicos):
    """Engolir em silêncio devolveria 200 com o serviço faltando — e ninguém olharia de novo."""
    lavagem, _ = seed_servicos
    primeira = _intake(client, staff_headers).json()
    segunda = _intake(client, staff_headers).json()
    chave = uuid4().hex
    corpo = [{"service_id": lavagem["id"], "idempotency_key": chave}]

    assert client.post(f"/api/v1/work-orders/{primeira['id']}/items", json=corpo, headers=staff_headers).status_code == 200
    r = client.post(f"/api/v1/work-orders/{segunda['id']}/items", json=corpo, headers=staff_headers)
    assert r.status_code == 409
    assert "outra OS" in r.json()["detail"]


def test_aceita_pagamento_vem_na_lista_do_patio(client, staff_headers):
    """O card do celular escreve sobre dinheiro; a casa proíbe decidir isso pelo sinal do saldo."""
    _intake(client, staff_headers)
    card = client.get("/api/v1/patio", headers=staff_headers).json()["recebido"][0]
    assert card["aceita_pagamento"] is True
