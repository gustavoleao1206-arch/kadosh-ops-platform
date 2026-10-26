"""Busca única do pátio."""


def _seed(client, headers):
    ruan = client.post("/api/v1/clients", json={"nome": "Ruan Oliveira", "telefone": "82 99911-0001"}, headers=headers).json()
    maria = client.post("/api/v1/clients", json={"nome": "Maria Souza", "telefone": "82 97777-1234"}, headers=headers).json()
    client.post("/api/v1/vehicles", json={"client_id": ruan["id"], "modelo": "Civic EX", "marca": "Honda", "placa": "BRA2E19"}, headers=headers)
    client.post("/api/v1/vehicles", json={"client_id": maria["id"], "modelo": "Corolla", "marca": "Toyota", "placa": "ABC1D23"}, headers=headers)
    return ruan, maria


def test_search_by_partial_plate(client, staff_headers):
    _seed(client, staff_headers)
    r = client.get("/api/v1/search?q=2e1", headers=staff_headers)
    assert r.status_code == 200
    body = r.json()
    assert [v["placa"] for v in body["veiculos"]] == ["BRA2E19"]
    assert body["veiculos"][0]["cliente"]["nome"] == "Ruan Oliveira"


def test_search_by_phone_digits_returns_owner_and_vehicles(client, staff_headers):
    _seed(client, staff_headers)
    body = client.get("/api/v1/search?q=7777-1234", headers=staff_headers).json()
    assert [c["nome"] for c in body["clientes"]] == ["Maria Souza"]
    assert [v["placa"] for v in body["veiculos"]] == ["ABC1D23"]


def test_search_by_name_without_accent(client, staff_headers):
    _seed(client, staff_headers)
    body = client.get("/api/v1/search?q=oliveira", headers=staff_headers).json()
    assert len(body["clientes"]) == 1 and len(body["veiculos"]) == 1


def test_search_ignores_archived_and_short_queries(client, staff_headers):
    ruan, _ = _seed(client, staff_headers)
    client.post(f"/api/v1/clients/{ruan['id']}/arquivar", headers=staff_headers)
    body = client.get("/api/v1/search?q=ruan", headers=staff_headers).json()
    assert body["clientes"] == [] and body["veiculos"] == []
    body = client.get("/api/v1/search?q=r", headers=staff_headers).json()
    assert body["clientes"] == [] and body["veiculos"] == []
    assert client.get("/api/v1/search", headers=staff_headers).status_code == 422


def test_search_by_brand_and_long_text(client, staff_headers):
    _seed(client, staff_headers)
    body = client.get("/api/v1/search?q=toyota", headers=staff_headers).json()
    assert [v["placa"] for v in body["veiculos"]] == ["ABC1D23"]
    assert client.get("/api/v1/search?q=Corolla XEi Plus", headers=staff_headers).status_code == 200
