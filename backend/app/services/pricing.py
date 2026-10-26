"""Preço combinado com um cliente. Extensão do catálogo, não um desconto.

A diferença importa: desconto é um abatimento naquela OS, com valor e motivo registrados; preço de
cliente é quanto ESTE cliente paga naquele serviço, sempre, sem que ninguém precise lembrar.

A cadeia de preço, na ordem em que o lançamento resolve:

    1. valor digitado na hora   → vale só naquela OS ("combinei diferente hoje")
    2. preço deste cliente      → o combinado permanente
    3. valor_base do catálogo   → o preço de tabela

E o congelamento: o valor escolhido é COPIADO para o item da OS. Mexer neste cadastro amanhã não
altera nenhuma OS lançada nem nenhum relatório fechado — o passado não muda porque a tabela mudou.
Só o estorno mexe no passado, e ele deixa rastro.

Fronteira de transação: `definir` e `remover` comitam; o resto só lê.
"""

from sqlalchemy import delete, false, func, or_, select
from sqlalchemy.orm import Session

from app.models import Client, ClientServicePrice, Service, User


class PricingError(Exception):
    def __init__(self, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _cliente_ou_404(db: Session, client_id: int) -> Client:
    client = db.get(Client, client_id)
    if client is None:
        raise PricingError("Cliente não encontrado.", 404)
    return client


def precos_do_cliente(db: Session, client_id: int) -> dict[int, int]:
    """{service_id: valor_centavos} — uma consulta só, para o lançamento não perguntar item a item."""
    return {
        sid: int(valor)
        for sid, valor in db.execute(
            select(ClientServicePrice.service_id, ClientServicePrice.valor_centavos).where(
                ClientServicePrice.client_id == client_id
            )
        ).all()
    }


def valor_efetivo(service: Service, override: int | None) -> int:
    """Quanto este serviço custa para este cliente, ignorando ajuste pontual de OS."""
    return service.valor_base_centavos if override is None else override


def listar(db: Session, client_id: int) -> list[dict]:
    """Catálogo ativo do ponto de vista de um cliente: preço de tabela, preço dele e o que vale.

    Traz o catálogo INTEIRO (ativo), não só os serviços com preço combinado: a tela é onde o dono
    define preços, e uma lista que só mostra o que já existe não deixa cadastrar o resto.
    """
    overrides = precos_do_cliente(db, client_id)
    servicos = db.scalars(
        select(Service)
        # ativos + os desativados que ainda têm combinado com ESTE cliente: um serviço que saiu de
        # linha depois de ganhar preço sumiria da tela e deixaria o dono com um cadastro invisível,
        # que ele não vê para conferir nem alcança para apagar.
        .where(or_(Service.ativo.is_(True), Service.id.in_(overrides) if overrides else false()))
        .order_by(Service.ativo.desc(), func.unaccent(func.lower(Service.nome)), Service.id)
    ).all()
    return [
        {
            "service_id": s.id,
            "servico_nome": s.nome,
            "valor_base_centavos": s.valor_base_centavos,
            "valor_cliente_centavos": overrides.get(s.id),
            "valor_efetivo_centavos": valor_efetivo(s, overrides.get(s.id)),
            "ativo": s.ativo,
        }
        for s in servicos
    ]


def definir(db: Session, client_id: int, service_id: int, valor_centavos: int, *, user: User) -> dict:
    """Cria ou atualiza o preço deste cliente para este serviço.

    Upsert de propósito: a operação é naturalmente idempotente (mandar o mesmo preço duas vezes dá
    no mesmo), então não pede chave de idempotência — ao contrário de pagamento e item, onde repetir
    CRIA valor do nada.
    """
    _cliente_ou_404(db, client_id)
    service = db.get(Service, service_id)
    if service is None:
        raise PricingError("Serviço não encontrado.", 404)
    if not service.ativo:
        # Serviço desativado é serviço que a loja não vende mais; combinar preço nele criaria um
        # cadastro que nem aparece no catálogo do cliente nem chega a ser usado num lançamento.
        raise PricingError(f"O serviço “{service.nome}” está desativado.", 409)
    if valor_centavos < 0:
        raise PricingError("O preço não pode ser negativo.", 422)

    linha = db.scalar(
        select(ClientServicePrice).where(
            ClientServicePrice.client_id == client_id, ClientServicePrice.service_id == service_id
        )
    )
    if linha is None:
        linha = ClientServicePrice(
            client_id=client_id, service_id=service_id, valor_centavos=valor_centavos, created_by=user.id
        )
        db.add(linha)
    else:
        linha.valor_centavos = valor_centavos
    db.commit()
    return {
        "service_id": service.id,
        "servico_nome": service.nome,
        "valor_base_centavos": service.valor_base_centavos,
        "valor_cliente_centavos": valor_centavos,
        "valor_efetivo_centavos": valor_centavos,
        "ativo": service.ativo,
    }


def remover(db: Session, client_id: int, service_id: int) -> None:
    """Apaga o combinado: o cliente volta ao preço de tabela NAS PRÓXIMAS OS.

    As OS já lançadas ficam como estão — o valor delas foi copiado no lançamento. É por isso que
    apagar aqui é seguro e não precisa de histórico próprio.
    """
    _cliente_ou_404(db, client_id)
    apagadas = db.execute(
        delete(ClientServicePrice).where(
            ClientServicePrice.client_id == client_id, ClientServicePrice.service_id == service_id
        )
    ).rowcount
    if not apagadas:
        raise PricingError("Este cliente não tem preço combinado para este serviço.", 404)
    db.commit()
