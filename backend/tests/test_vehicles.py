"""Veículos: placa normalizada e única só entre ativos, sem placa, transferência, arquivar, busca."""


def _client(client, headers, nome="Ruan", fone="82 99911-0001"):
    r = client.post("/api/v1/clients", json={"nome": nome, "telefone": fone}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _vehicle(client, headers, client_id, **over):
    body = {"client_id": client_id, "marca": "Honda", "modelo": "Civic EX", "cor": "Prata", "ano": 2001, "placa": "bra-2e19", **over}
    r = client.post("/api/v1/vehicles", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_normalizes_plate_and_embeds_client(client, staff_headers):
    c = _client(client, staff_headers)
    v = _vehicle(client, staff_headers, c["id"])
    assert v["placa"] == "BRA2E19"
    assert v["descricao"] == "Honda Civic EX Prata · BRA2E19"
    assert v["cliente"]["id"] == c["id"] and v["cliente"]["nome"] == "Ruan"
    # aparece na ficha do cliente
    ficha = client.get(f"/api/v1/clients/{c['id']}", headers=staff_headers).json()
    assert [x["placa"] for x in ficha["veiculos"]] == ["BRA2E19"]


def test_plate_validation(client, staff_headers):
    c = _client(client, staff_headers)
    r = client.post("/api/v1/vehicles", json={"client_id": c["id"], "modelo": "X", "placa": "ABCD12345"}, headers=staff_headers)
    assert r.status_code == 422
    v = _vehicle(client, staff_headers, c["id"], placa=None)
    assert v["placa"] is None and v["descricao"].endswith("(sem placa)")
    v2 = _vehicle(client, staff_headers, c["id"], placa="", modelo="Outro")
    assert v2["placa"] is None  # string vazia vira null — dois carros sem placa convivem


def test_plate_unique_only_among_active(client, staff_headers):
    c1 = _client(client, staff_headers)
    c2 = _client(client, staff_headers, nome="Novo Dono", fone="82 95555-0000")
    v = _vehicle(client, staff_headers, c1["id"])
    r = client.post("/api/v1/vehicles", json={"client_id": c2["id"], "modelo": "Civic", "placa": "BRA2E19"}, headers=staff_headers)
    assert r.status_code == 409 and "Ruan" in r.json()["detail"]
    client.post(f"/api/v1/vehicles/{v['id']}/arquivar", headers=staff_headers)
    r = client.post("/api/v1/vehicles", json={"client_id": c2["id"], "modelo": "Civic", "placa": "BRA2E19"}, headers=staff_headers)
    assert r.status_code == 201
    # desarquivar o antigo agora colide
    r = client.post(f"/api/v1/vehicles/{v['id']}/desarquivar", headers=staff_headers)
    assert r.status_code == 409


def test_transfer_keeps_vehicle_and_changes_owner(client, staff_headers):
    c1 = _client(client, staff_headers)
    c2 = _client(client, staff_headers, nome="Comprador", fone="82 95555-0000")
    v = _vehicle(client, staff_headers, c1["id"])
    r = client.post(f"/api/v1/vehicles/{v['id']}/transferir", json={"client_id": c2["id"]}, headers=staff_headers)
    assert r.status_code == 200 and r.json()["cliente"]["id"] == c2["id"]
    assert client.post(f"/api/v1/vehicles/{v['id']}/transferir", json={"client_id": c2["id"]}, headers=staff_headers).status_code == 400
    assert client.post(f"/api/v1/vehicles/{v['id']}/transferir", json={"client_id": 9999}, headers=staff_headers).status_code == 404
    assert client.get(f"/api/v1/clients/{c1['id']}", headers=staff_headers).json()["veiculos"] == []


def test_cannot_add_vehicle_to_archived_client(client, staff_headers):
    c = _client(client, staff_headers)
    client.post(f"/api/v1/clients/{c['id']}/arquivar", headers=staff_headers)
    r = client.post("/api/v1/vehicles", json={"client_id": c["id"], "modelo": "X"}, headers=staff_headers)
    assert r.status_code == 409


def test_update_and_remove_plate(client, staff_headers):
    c = _client(client, staff_headers)
    v = _vehicle(client, staff_headers, c["id"])
    r = client.patch(f"/api/v1/vehicles/{v['id']}", json={"cor": "Preto", "placa": "abc1d23"}, headers=staff_headers)
    assert r.status_code == 200 and r.json()["placa"] == "ABC1D23" and r.json()["cor"] == "Preto"
    r = client.patch(f"/api/v1/vehicles/{v['id']}", json={"remover_placa": True}, headers=staff_headers)
    assert r.status_code == 200 and r.json()["placa"] is None


def test_list_filters_and_search(client, staff_headers):
    c = _client(client, staff_headers)
    _vehicle(client, staff_headers, c["id"])
    _vehicle(client, staff_headers, c["id"], modelo="Corolla XEi", marca="Toyota", placa="ABC1D23")
    assert client.get("/api/v1/vehicles", headers=staff_headers).json()["total"] == 2
    assert client.get(f"/api/v1/vehicles?client_id={c['id']}", headers=staff_headers).json()["total"] == 2
    assert client.get("/api/v1/vehicles?q=2e19", headers=staff_headers).json()["total"] == 1
    assert client.get("/api/v1/vehicles?q=corolla", headers=staff_headers).json()["total"] == 1
    assert client.get("/api/v1/vehicles?q=toyota", headers=staff_headers).json()["total"] == 1
    r = client.get(f"/api/v1/clients/{c['id']}/vehicles", headers=staff_headers)
    assert r.status_code == 200 and len(r.json()) == 2


def test_detail_history_and_delete_rules(client, admin_headers, staff_headers):
    c = _client(client, staff_headers)
    v = _vehicle(client, staff_headers, c["id"])
    r = client.get(f"/api/v1/vehicles/{v['id']}", headers=staff_headers)
    assert r.status_code == 200 and r.json()["historico"] == []
    assert client.delete(f"/api/v1/vehicles/{v['id']}", headers=staff_headers).status_code == 403
    assert client.delete(f"/api/v1/vehicles/{v['id']}", headers=admin_headers).status_code == 204
    assert client.get(f"/api/v1/vehicles/{v['id']}", headers=admin_headers).status_code == 404


def test_search_with_long_text_does_not_500(client, staff_headers):
    c = _client(client, staff_headers)
    _vehicle(client, staff_headers, c["id"], modelo="Corolla XEi", marca="Toyota", placa="ABC1D23")
    r = client.get("/api/v1/vehicles?q=Corolla XEi", headers=staff_headers)
    assert r.status_code == 200 and r.json()["total"] == 1
    assert client.get("/api/v1/vehicles?q=Hilux SRX", headers=staff_headers).status_code == 200


def test_update_plate_collides_with_active(client, staff_headers):
    c = _client(client, staff_headers)
    _vehicle(client, staff_headers, c["id"])  # BRA2E19
    v2 = _vehicle(client, staff_headers, c["id"], placa="ABC1D23", modelo="Outro")
    r = client.patch(f"/api/v1/vehicles/{v2['id']}", json={"placa": "bra2e19"}, headers=staff_headers)
    assert r.status_code == 409


def test_transfer_to_archived_client_is_refused(client, staff_headers):
    c1 = _client(client, staff_headers)
    c2 = _client(client, staff_headers, nome="Arquivado", fone="82 95555-0000")
    v = _vehicle(client, staff_headers, c1["id"])
    client.post(f"/api/v1/clients/{c2['id']}/arquivar", headers=staff_headers)
    r = client.post(f"/api/v1/vehicles/{v['id']}/transferir", json={"client_id": c2["id"]}, headers=staff_headers)
    assert r.status_code == 409


def test_history_stats_and_blocks_with_work_orders(client, db, admin_headers, staff_headers):
    from datetime import datetime, timezone

    from app.models import WorkOrder

    c = _client(client, staff_headers)
    c2 = _client(client, staff_headers, nome="Comprador", fone="82 95555-0000")
    v = _vehicle(client, staff_headers, c["id"])
    db.add(
        WorkOrder(
            client_id=c["id"], vehicle_id=v["id"], status="concluido", valor_total_centavos=12990,
            entrada=datetime(2026, 8, 1, 12, tzinfo=timezone.utc), conclusao=datetime(2026, 8, 1, 15, tzinfo=timezone.utc),
        )
    )
    db.add(WorkOrder(client_id=c["id"], vehicle_id=v["id"], status="em_execucao", valor_total_centavos=39990,
                     entrada=datetime(2026, 8, 20, 9, tzinfo=timezone.utc)))
    db.commit()

    ficha = client.get(f"/api/v1/clients/{c['id']}", headers=staff_headers).json()
    assert ficha["stats"]["atendimentos"] == 1 and ficha["stats"]["total_gasto_centavos"] == 12990
    # datas vêm em ISO com offset (fuso da sessão do banco); o instante é o que importa
    assert datetime.fromisoformat(ficha["stats"]["ultimo_atendimento"]) == datetime(2026, 8, 1, 15, tzinfo=timezone.utc)
    assert [h["status_label"] for h in ficha["historico"]] == ["Em execução", "Concluído"]  # mais recente primeiro
    assert ficha["historico"][0]["veiculo"] == "Honda Civic EX Prata · BRA2E19"
    assert ficha["historico"][0]["cliente"] == "Ruan"

    vd = client.get(f"/api/v1/vehicles/{v['id']}", headers=staff_headers).json()
    assert len(vd["historico"]) == 2

    # OS em aberto bloqueia arquivar/transferir o veículo e arquivar o cliente
    assert client.post(f"/api/v1/vehicles/{v['id']}/arquivar", headers=staff_headers).status_code == 409
    assert client.post(f"/api/v1/vehicles/{v['id']}/transferir", json={"client_id": c2["id"]}, headers=staff_headers).status_code == 409
    assert client.post(f"/api/v1/clients/{c['id']}/arquivar", headers=staff_headers).status_code == 409
    # e a exclusão (admin) é barrada pela FK → 409
    assert client.delete(f"/api/v1/vehicles/{v['id']}", headers=admin_headers).status_code == 409
