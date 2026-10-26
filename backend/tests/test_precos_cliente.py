"""Preço combinado por cliente e a cadeia de resolução no lançamento.

O teste que segura a casa é `test_mudar_o_combinado_nao_reescreve_os_ja_lancada`: o valor é copiado
para o item no momento do lançamento, então mexer no cadastro amanhã não pode alterar nenhuma OS
nem nenhum relatório fechado. Se esse congelamento cair, o histórico da loja passa a mudar sozinho.
"""

from tests.conftest import STAFF_EMAIL, STAFF_PASS, login_android


def _preco(client, headers, cliente_id, service_id, valor):
    return client.put(
        f"/api/v1/clients/{cliente_id}/service-prices/{service_id}",
        json={"valor_centavos": valor},
        headers=headers,
    )


def test_cadastrar_preco_do_cliente(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    cliente, _ = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    r = _preco(client, admin_headers, cliente["id"], lavagem["id"], 9900)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["valor_base_centavos"] == 12990
    assert corpo["valor_cliente_centavos"] == 9900
    assert corpo["valor_efetivo_centavos"] == 9900


def test_listagem_traz_o_catalogo_inteiro_com_e_sem_combinado(
    client, admin_headers, seed_cliente_veiculo, seed_servicos
):
    """A tela é onde o dono DEFINE preços: listar só o que já existe deixaria o resto inalcançável."""
    cliente, _ = seed_cliente_veiculo
    lavagem, polimento = seed_servicos
    _preco(client, admin_headers, cliente["id"], lavagem["id"], 9900)

    r = client.get(f"/api/v1/clients/{cliente['id']}/service-prices", headers=admin_headers)
    assert r.status_code == 200, r.text
    por_id = {linha["service_id"]: linha for linha in r.json()}
    assert por_id[lavagem["id"]]["valor_cliente_centavos"] == 9900
    assert por_id[polimento["id"]]["valor_cliente_centavos"] is None
    # sem combinado, o efetivo é a tabela
    assert por_id[polimento["id"]]["valor_efetivo_centavos"] == polimento["valor_base_centavos"]


def test_upsert_e_idempotente_por_natureza(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    """Mandar o mesmo preço duas vezes dá no mesmo — por isso não pede chave de idempotência."""
    cliente, _ = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    _preco(client, admin_headers, cliente["id"], lavagem["id"], 9900)
    _preco(client, admin_headers, cliente["id"], lavagem["id"], 8800)
    linhas = client.get(f"/api/v1/clients/{cliente['id']}/service-prices", headers=admin_headers).json()
    combinados = [linha for linha in linhas if linha["valor_cliente_centavos"] is not None]
    assert len(combinados) == 1
    assert combinados[0]["valor_cliente_centavos"] == 8800


def test_remover_volta_ao_preco_de_tabela(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    cliente, _ = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    _preco(client, admin_headers, cliente["id"], lavagem["id"], 9900)
    r = client.delete(
        f"/api/v1/clients/{cliente['id']}/service-prices/{lavagem['id']}", headers=admin_headers
    )
    assert r.status_code == 204
    linhas = client.get(f"/api/v1/clients/{cliente['id']}/service-prices", headers=admin_headers).json()
    por_id = {linha["service_id"]: linha for linha in linhas}
    assert por_id[lavagem["id"]]["valor_cliente_centavos"] is None
    assert por_id[lavagem["id"]]["valor_efetivo_centavos"] == 12990
    # remover de novo avisa em vez de fingir que deu certo
    assert client.delete(
        f"/api/v1/clients/{cliente['id']}/service-prices/{lavagem['id']}", headers=admin_headers
    ).status_code == 404


def test_so_admin_cadastra_preco(client, staff, seed_cliente_veiculo, seed_servicos):
    """Preço combinado é extensão do catálogo, e catálogo é do dono. Ler, o sócio pode."""
    headers = login_android(client, STAFF_EMAIL, STAFF_PASS)
    cliente, _ = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    assert _preco(client, headers, cliente["id"], lavagem["id"], 9900).status_code == 403
    assert client.delete(
        f"/api/v1/clients/{cliente['id']}/service-prices/{lavagem['id']}", headers=headers
    ).status_code == 403
    assert client.get(f"/api/v1/clients/{cliente['id']}/service-prices", headers=headers).status_code == 200


def test_cliente_ou_servico_inexistente_e_404(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    cliente, _ = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    assert _preco(client, admin_headers, 99999, lavagem["id"], 100).status_code == 404
    assert _preco(client, admin_headers, cliente["id"], 99999, 100).status_code == 404
    assert client.get("/api/v1/clients/99999/service-prices", headers=admin_headers).status_code == 404


def test_preco_negativo_e_422(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    cliente, _ = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    assert _preco(client, admin_headers, cliente["id"], lavagem["id"], -1).status_code == 422


# --------------------------------------------------------------- a cadeia no lançamento


def test_lancamento_usa_o_preco_do_cliente(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    """O app manda só o service_id e ganha o preço combinado de graça — sem mudar o contrato."""
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    _preco(client, admin_headers, cliente["id"], lavagem["id"], 9900)

    wo = client.post(
        "/api/v1/work-orders",
        json={"client_id": cliente["id"], "vehicle_id": veiculo["id"], "itens": [{"service_id": lavagem["id"]}]},
        headers=admin_headers,
    ).json()
    assert wo["itens"][0]["valor_centavos"] == 9900
    assert wo["valor_total_centavos"] == 9900


def test_valor_digitado_na_hora_vence_o_combinado(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    """A ponta da cadeia: "hoje combinei diferente" sobrepõe o preço permanente, só nesta OS."""
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    _preco(client, admin_headers, cliente["id"], lavagem["id"], 9900)

    wo = client.post(
        "/api/v1/work-orders",
        json={
            "client_id": cliente["id"],
            "vehicle_id": veiculo["id"],
            "itens": [{"service_id": lavagem["id"], "valor_centavos": 7000}],
        },
        headers=admin_headers,
    ).json()
    assert wo["itens"][0]["valor_centavos"] == 7000
    # e o combinado do cliente continua intacto para a próxima OS
    linhas = client.get(f"/api/v1/clients/{cliente['id']}/service-prices", headers=admin_headers).json()
    assert {linha["service_id"]: linha["valor_cliente_centavos"] for linha in linhas}[lavagem["id"]] == 9900


def test_sem_combinado_usa_a_tabela(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    wo = client.post(
        "/api/v1/work-orders",
        json={"client_id": cliente["id"], "vehicle_id": veiculo["id"], "itens": [{"service_id": lavagem["id"]}]},
        headers=admin_headers,
    ).json()
    assert wo["itens"][0]["valor_centavos"] == 12990


def test_combinado_vale_so_para_o_cliente_dele(client, admin_headers, seed_servicos, staff_headers):
    """Preço de um cliente não vaza para o outro — o óbvio que precisa estar preso."""
    lavagem, _ = seed_servicos
    a = client.post("/api/v1/clients", json={"nome": "Cliente A", "telefone": "82 98800-0001"}, headers=staff_headers).json()
    b = client.post("/api/v1/clients", json={"nome": "Cliente B", "telefone": "82 98800-0002"}, headers=staff_headers).json()
    va = client.post(
        "/api/v1/vehicles",
        json={"client_id": a["id"], "marca": "VW", "modelo": "Gol", "placa": "AAA1A11"},
        headers=staff_headers,
    ).json()
    vb = client.post(
        "/api/v1/vehicles",
        json={"client_id": b["id"], "marca": "Fiat", "modelo": "Argo", "placa": "BBB2B22"},
        headers=staff_headers,
    ).json()
    _preco(client, admin_headers, a["id"], lavagem["id"], 5000)

    os_a = client.post(
        "/api/v1/work-orders",
        json={"client_id": a["id"], "vehicle_id": va["id"], "itens": [{"service_id": lavagem["id"]}]},
        headers=admin_headers,
    ).json()
    os_b = client.post(
        "/api/v1/work-orders",
        json={"client_id": b["id"], "vehicle_id": vb["id"], "itens": [{"service_id": lavagem["id"]}]},
        headers=admin_headers,
    ).json()
    assert os_a["itens"][0]["valor_centavos"] == 5000
    assert os_b["itens"][0]["valor_centavos"] == 12990


def test_mudar_o_combinado_nao_reescreve_os_ja_lancada(
    client, admin_headers, seed_cliente_veiculo, seed_servicos
):
    """O congelamento. Sem ele, o relatório de ontem mudaria porque alguém mexeu no preço hoje."""
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    _preco(client, admin_headers, cliente["id"], lavagem["id"], 9900)
    wo = client.post(
        "/api/v1/work-orders",
        json={"client_id": cliente["id"], "vehicle_id": veiculo["id"], "itens": [{"service_id": lavagem["id"]}]},
        headers=admin_headers,
    ).json()
    assert wo["valor_total_centavos"] == 9900

    _preco(client, admin_headers, cliente["id"], lavagem["id"], 30000)
    depois = client.get(f"/api/v1/work-orders/{wo['id']}", headers=admin_headers).json()
    assert depois["itens"][0]["valor_centavos"] == 9900
    assert depois["valor_total_centavos"] == 9900


def test_apagar_o_combinado_tambem_nao_reescreve_os_ja_lancada(
    client, admin_headers, seed_cliente_veiculo, seed_servicos
):
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    _preco(client, admin_headers, cliente["id"], lavagem["id"], 9900)
    wo = client.post(
        "/api/v1/work-orders",
        json={"client_id": cliente["id"], "vehicle_id": veiculo["id"], "itens": [{"service_id": lavagem["id"]}]},
        headers=admin_headers,
    ).json()
    client.delete(f"/api/v1/clients/{cliente['id']}/service-prices/{lavagem['id']}", headers=admin_headers)
    depois = client.get(f"/api/v1/work-orders/{wo['id']}", headers=admin_headers).json()
    assert depois["itens"][0]["valor_centavos"] == 9900


def test_catalogo_com_client_id_mostra_o_preco_do_cliente(
    client, admin_headers, seed_cliente_veiculo, seed_servicos
):
    """O que o seletor de serviço da OS consome para já vir preenchido com o preço certo."""
    cliente, _ = seed_cliente_veiculo
    lavagem, polimento = seed_servicos
    _preco(client, admin_headers, cliente["id"], lavagem["id"], 9900)

    r = client.get(f"/api/v1/services?client_id={cliente['id']}", headers=admin_headers)
    assert r.status_code == 200, r.text
    por_id = {s["id"]: s for s in r.json()["items"]}
    assert por_id[lavagem["id"]]["valor_cliente_centavos"] == 9900
    assert por_id[lavagem["id"]]["valor_efetivo_centavos"] == 9900
    assert por_id[polimento["id"]]["valor_cliente_centavos"] is None
    assert por_id[polimento["id"]]["valor_efetivo_centavos"] == polimento["valor_base_centavos"]


def test_catalogo_sem_client_id_nao_inventa_preco(client, admin_headers, seed_servicos):
    """Sem cliente na consulta, os campos vêm nulos — nada de fingir que há combinado."""
    r = client.get("/api/v1/services", headers=admin_headers)
    assert all(s["valor_cliente_centavos"] is None for s in r.json()["items"])
    assert all(s["valor_efetivo_centavos"] is None for s in r.json()["items"])


def test_catalogo_com_cliente_inexistente_e_404(client, admin_headers, seed_servicos):
    assert client.get("/api/v1/services?client_id=99999", headers=admin_headers).status_code == 404


def test_lancar_servico_depois_tambem_usa_o_combinado(
    client, admin_headers, seed_cliente_veiculo, seed_servicos
):
    """O caminho do app: OS já aberta, serviço lançado no pátio pelo endpoint de itens."""
    cliente, veiculo = seed_cliente_veiculo
    lavagem, polimento = seed_servicos
    _preco(client, admin_headers, cliente["id"], polimento["id"], 50000)
    wo = client.post(
        "/api/v1/work-orders",
        json={"client_id": cliente["id"], "vehicle_id": veiculo["id"], "itens": [{"service_id": lavagem["id"]}]},
        headers=admin_headers,
    ).json()
    r = client.post(
        f"/api/v1/work-orders/{wo['id']}/items",
        json=[{"service_id": polimento["id"], "idempotency_key": "lanca-polimento-1"}],
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    valores = {i["service_id"]: i["valor_centavos"] for i in r.json()["itens"]}
    assert valores[polimento["id"]] == 50000
    assert valores[lavagem["id"]] == 12990


def test_socio_lanca_servico_com_o_preco_combinado_pelo_dono(
    client, staff, admin, seed_cliente_veiculo, seed_servicos
):
    """O combinado é do dono, mas quem lança no pátio é o sócio — e o preço tem de acompanhar."""
    from tests.conftest import ADMIN_EMAIL, ADMIN_PASS

    admin_h = login_android(client, ADMIN_EMAIL, ADMIN_PASS)
    staff_h = login_android(client, STAFF_EMAIL, STAFF_PASS)
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    _preco(client, admin_h, cliente["id"], lavagem["id"], 7777)

    wo = client.post(
        "/api/v1/work-orders",
        json={"client_id": cliente["id"], "vehicle_id": veiculo["id"], "itens": [{"service_id": lavagem["id"]}]},
        headers=staff_h,
    ).json()
    assert wo["itens"][0]["valor_centavos"] == 7777


# --------------------------------------------------------------- serviço desativado


def test_nao_cadastra_preco_em_servico_desativado(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    """Achado da revisão: serviço fora de linha aceitava preço combinado que nunca seria usado."""
    cliente, _ = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    client.patch(f"/api/v1/services/{lavagem['id']}", json={"ativo": False}, headers=admin_headers)
    r = _preco(client, admin_headers, cliente["id"], lavagem["id"], 9900)
    assert r.status_code == 409
    assert "desativado" in r.json()["detail"].lower()


def test_combinado_de_servico_desativado_depois_continua_visivel(
    client, admin_headers, seed_cliente_veiculo, seed_servicos
):
    """O outro lado: se o serviço saiu de linha DEPOIS, o combinado não pode virar cadastro fantasma.

    Some da tela e o dono fica com um preço que não vê para conferir nem alcança para apagar.
    """
    cliente, _ = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    _preco(client, admin_headers, cliente["id"], lavagem["id"], 9900)
    client.patch(f"/api/v1/services/{lavagem['id']}", json={"ativo": False}, headers=admin_headers)

    linhas = client.get(f"/api/v1/clients/{cliente['id']}/service-prices", headers=admin_headers).json()
    por_id = {linha["service_id"]: linha for linha in linhas}
    assert lavagem["id"] in por_id, "o combinado sumiu da tela e virou cadastro invisível"
    assert por_id[lavagem["id"]]["valor_cliente_centavos"] == 9900
    assert por_id[lavagem["id"]]["ativo"] is False
    # e continua removível
    assert client.delete(
        f"/api/v1/clients/{cliente['id']}/service-prices/{lavagem['id']}", headers=admin_headers
    ).status_code == 204


def test_servico_desativado_sem_combinado_nao_polui_a_lista(
    client, admin_headers, seed_cliente_veiculo, seed_servicos
):
    cliente, _ = seed_cliente_veiculo
    lavagem, polimento = seed_servicos
    client.patch(f"/api/v1/services/{polimento['id']}", json={"ativo": False}, headers=admin_headers)
    linhas = client.get(f"/api/v1/clients/{cliente['id']}/service-prices", headers=admin_headers).json()
    assert polimento["id"] not in {linha["service_id"] for linha in linhas}
