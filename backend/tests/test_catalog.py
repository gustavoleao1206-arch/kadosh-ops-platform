"""Catálogo de serviços: leitura para todos, alteração só para o admin, desativar em vez de excluir."""

SERVICO = {"nome": "Polimento Técnico", "descricao": "Correção da pintura em etapas.", "valor_base_centavos": 99990, "duracao_estimada_min": 480}


def _create(client, headers, **over):
    r = client.post("/api/v1/services", json={**SERVICO, **over}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_and_list(client, admin_headers, staff_headers):
    s = _create(client, admin_headers)
    assert s["valor_base_centavos"] == 99990 and s["ativo"] is True
    r = client.get("/api/v1/services", headers=staff_headers)  # staff lê
    assert r.status_code == 200 and r.json()["total"] == 1


def test_only_admin_writes(client, staff_headers):
    assert client.post("/api/v1/services", json=SERVICO, headers=staff_headers).status_code == 403


def test_duplicate_name_is_refused(client, admin_headers):
    _create(client, admin_headers)
    r = client.post("/api/v1/services", json={**SERVICO, "nome": "polimento técnico"}, headers=admin_headers)
    assert r.status_code == 409


def test_update_and_deactivate(client, admin_headers):
    s = _create(client, admin_headers)
    r = client.patch(f"/api/v1/services/{s['id']}", json={"valor_base_centavos": 109990}, headers=admin_headers)
    assert r.status_code == 200 and r.json()["valor_base_centavos"] == 109990
    r = client.patch(f"/api/v1/services/{s['id']}", json={"ativo": False}, headers=admin_headers)
    assert r.json()["ativo"] is False
    assert client.get("/api/v1/services?apenas_ativos=true", headers=admin_headers).json()["total"] == 0


def test_validations(client, admin_headers):
    assert client.post("/api/v1/services", json={**SERVICO, "valor_base_centavos": -1}, headers=admin_headers).status_code == 422
    assert client.post("/api/v1/services", json={**SERVICO, "nome": "X"}, headers=admin_headers).status_code == 422
    s = _create(client, admin_headers)
    r = client.patch(f"/api/v1/services/{s['id']}", json={"nome": None}, headers=admin_headers)
    assert r.status_code == 422


def test_delete_only_when_unused(client, admin_headers, staff_headers, seed_cliente_veiculo):
    s = _create(client, admin_headers)
    outro = _create(client, admin_headers, nome="Lavagem Simples", valor_base_centavos=12990)
    c, v = seed_cliente_veiculo
    client.post(
        "/api/v1/work-orders",
        json={"client_id": c["id"], "vehicle_id": v["id"], "itens": [{"service_id": s["id"]}]},
        headers=staff_headers,
    )
    r = client.delete(f"/api/v1/services/{s['id']}", headers=admin_headers)
    assert r.status_code == 409 and "desative" in r.json()["detail"]
    assert client.delete(f"/api/v1/services/{outro['id']}", headers=admin_headers).status_code == 204
