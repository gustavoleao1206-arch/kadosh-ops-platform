"""Clientes: cadastro, normalização de telefone, duplicidade, busca, ficha, arquivar, exclusão."""

from tests.conftest import login_android

RUAN = {"nome": "Ruan Oliveira", "telefone": "(82) 99911-0001", "email": None, "observacoes": "Indicado pela Maria"}


def _create(client, headers, **over):
    body = {**RUAN, **over}
    r = client.post("/api/v1/clients", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_create_normalizes_phone_and_lists(client, staff_headers):
    c = _create(client, staff_headers)
    assert c["telefone"] == "5582999110001"
    assert c["veiculos"] == [] and c["arquivado_em"] is None
    r = client.get("/api/v1/clients", headers=staff_headers)
    assert r.status_code == 200 and r.json()["total"] == 1


def test_phone_validation(client, staff_headers):
    r = client.post("/api/v1/clients", json={**RUAN, "telefone": "123"}, headers=staff_headers)
    assert r.status_code == 422
    c = _create(client, staff_headers, telefone="+55 82 99911-0002")
    assert c["telefone"] == "5582999110002"
    c = _create(client, staff_headers, telefone=None, nome="Sem Telefone")
    assert c["telefone"] is None


def test_duplicate_phone_warns_then_force(client, staff_headers):
    first = _create(client, staff_headers)
    r = client.post("/api/v1/clients", json={**RUAN, "nome": "Esposa do Ruan"}, headers=staff_headers)
    assert r.status_code == 409
    assert r.json()["existente"]["id"] == first["id"]
    r = client.post("/api/v1/clients?force=true", json={**RUAN, "nome": "Esposa do Ruan"}, headers=staff_headers)
    assert r.status_code == 201


def test_search_by_name_without_accent_and_by_phone_digits(client, staff_headers):
    _create(client, staff_headers, nome="João Ângelo", telefone="82 98888-1234")
    _create(client, staff_headers, nome="Maria Souza", telefone="82 97777-0000")
    assert client.get("/api/v1/clients?q=joao angelo", headers=staff_headers).json()["total"] == 1
    assert client.get("/api/v1/clients?q=ÂNGELO", headers=staff_headers).json()["total"] == 1
    assert client.get("/api/v1/clients?q=1234", headers=staff_headers).json()["total"] == 1
    assert client.get("/api/v1/clients?q=988881234", headers=staff_headers).json()["total"] == 1
    assert client.get("/api/v1/clients?q=ninguem", headers=staff_headers).json()["total"] == 0


def test_detail_has_stats_and_history(client, staff_headers):
    c = _create(client, staff_headers)
    r = client.get(f"/api/v1/clients/{c['id']}", headers=staff_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["stats"] == {"atendimentos": 0, "total_gasto_centavos": 0, "ultimo_atendimento": None}
    assert body["historico"] == []
    assert client.get("/api/v1/clients/9999", headers=staff_headers).status_code == 404


def test_update_partial_and_unknown_field(client, staff_headers):
    c = _create(client, staff_headers)
    r = client.patch(f"/api/v1/clients/{c['id']}", json={"nome": "Ruan O."}, headers=staff_headers)
    assert r.status_code == 200 and r.json()["nome"] == "Ruan O." and r.json()["telefone"] == "5582999110001"
    r = client.patch(f"/api/v1/clients/{c['id']}", json={"role": "admin"}, headers=staff_headers)
    assert r.status_code == 422


def test_archive_hides_from_list_and_cascades_to_vehicles(client, staff_headers):
    c = _create(client, staff_headers)
    v = client.post(
        "/api/v1/vehicles", json={"client_id": c["id"], "modelo": "Civic", "placa": "BRA2E19"}, headers=staff_headers
    ).json()
    r = client.post(f"/api/v1/clients/{c['id']}/arquivar", headers=staff_headers)
    assert r.status_code == 200 and r.json()["arquivado_em"]
    assert client.get("/api/v1/clients", headers=staff_headers).json()["total"] == 0
    assert client.get("/api/v1/clients?arquivados=true", headers=staff_headers).json()["total"] == 1
    assert client.get(f"/api/v1/vehicles/{v['id']}", headers=staff_headers).json()["arquivado_em"]
    # a ficha continua acessível
    assert client.get(f"/api/v1/clients/{c['id']}", headers=staff_headers).status_code == 200
    r = client.post(f"/api/v1/clients/{c['id']}/desarquivar", headers=staff_headers)
    assert r.status_code == 200 and r.json()["arquivado_em"] is None


def test_delete_is_admin_only_and_blocked_by_history(client, admin_headers, staff_headers):
    c = _create(client, staff_headers)
    assert client.delete(f"/api/v1/clients/{c['id']}", headers=staff_headers).status_code == 403
    client.post("/api/v1/vehicles", json={"client_id": c["id"], "modelo": "Civic"}, headers=staff_headers)
    r = client.delete(f"/api/v1/clients/{c['id']}", headers=admin_headers)
    assert r.status_code == 409  # tem veículo → FK RESTRICT → 409 classificado
    other = _create(client, staff_headers, nome="Sem Nada", telefone="82 96666-0000")
    assert client.delete(f"/api/v1/clients/{other['id']}", headers=admin_headers).status_code == 204
    assert client.get(f"/api/v1/clients/{other['id']}", headers=admin_headers).status_code == 404


def test_requires_auth(client):
    assert client.get("/api/v1/clients").status_code == 401


def test_update_phone_duplicate_warns_then_force(client, staff_headers):
    a = _create(client, staff_headers)
    b = _create(client, staff_headers, nome="Maria", telefone="82 97777-0000")
    r = client.patch(f"/api/v1/clients/{b['id']}", json={"telefone": RUAN["telefone"]}, headers=staff_headers)
    assert r.status_code == 409 and r.json()["existente"]["id"] == a["id"]
    r = client.patch(f"/api/v1/clients/{b['id']}?force=true", json={"telefone": RUAN["telefone"]}, headers=staff_headers)
    assert r.status_code == 200 and r.json()["telefone"] == "5582999110001"
    # mesmo telefone do próprio cliente não é duplicidade
    assert client.patch(f"/api/v1/clients/{a['id']}", json={"telefone": RUAN["telefone"], "nome": "Ruan O."}, headers=staff_headers).status_code == 200


def test_unarchive_restores_vehicles_archived_together(client, staff_headers):
    c = _create(client, staff_headers)
    v_before = client.post("/api/v1/vehicles", json={"client_id": c["id"], "modelo": "Antigo"}, headers=staff_headers).json()
    client.post(f"/api/v1/vehicles/{v_before['id']}/arquivar", headers=staff_headers)  # arquivado individualmente antes
    v = client.post("/api/v1/vehicles", json={"client_id": c["id"], "modelo": "Civic", "placa": "BRA2E19"}, headers=staff_headers).json()
    client.post(f"/api/v1/clients/{c['id']}/arquivar", headers=staff_headers)
    client.post(f"/api/v1/clients/{c['id']}/arquivar", headers=staff_headers)  # idempotente
    client.post(f"/api/v1/clients/{c['id']}/desarquivar", headers=staff_headers)
    assert client.get(f"/api/v1/vehicles/{v['id']}", headers=staff_headers).json()["arquivado_em"] is None
    assert client.get(f"/api/v1/vehicles/{v_before['id']}", headers=staff_headers).json()["arquivado_em"] is not None


def test_update_nome_null_is_rejected_with_field(client, staff_headers):
    c = _create(client, staff_headers)
    r = client.patch(f"/api/v1/clients/{c['id']}", json={"nome": None}, headers=staff_headers)
    assert r.status_code == 422
    err = r.json()["detail"][0]
    assert err["loc"] == ["nome"] and "vazio" in err["msg"] and "input" not in err


def test_validation_messages_are_portuguese_and_do_not_echo_input(client, staff_headers):
    r = client.post("/api/v1/clients", json={"nome": "Zé", "email": "joao@gmail"}, headers=staff_headers)
    assert r.status_code == 422
    errs = r.json()["detail"]
    assert any(e["loc"] == ["email"] and e["msg"] == "E-mail inválido." for e in errs)
    r = client.post("/api/v1/auth/login", json={"email": "a@b.com.br"})
    assert r.status_code == 422
    body = r.text
    assert "Campo obrigatório." in body and "input" not in r.json()["detail"][0]
