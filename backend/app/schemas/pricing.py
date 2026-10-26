"""Preços combinados por cliente. O rótulo e o valor efetivo saem prontos daqui."""

from pydantic import Field

from app.schemas.base import InSchema, OutSchema


class ClientServicePriceIn(InSchema):
    valor_centavos: int = Field(ge=0, le=100_000_000)


class ClientServicePriceOut(OutSchema):
    service_id: int
    servico_nome: str
    valor_base_centavos: int
    # None = este cliente não tem preço combinado; paga a tabela
    valor_cliente_centavos: int | None
    # o que o lançamento vai usar quando ninguém digitar valor na hora
    valor_efetivo_centavos: int
    # False só aparece para um serviço desativado que AINDA tem combinado com este cliente — a tela
    # mostra para o dono poder remover; um serviço fora de linha não recebe preço novo.
    ativo: bool
