from datetime import datetime

from pydantic import Field, field_validator

from app.schemas.base import InSchema, OutSchema


class ServiceCreateIn(InSchema):
    nome: str = Field(min_length=2, max_length=120)
    descricao: str | None = Field(default=None, max_length=2000)
    valor_base_centavos: int = Field(ge=0, le=100_000_000)
    duracao_estimada_min: int = Field(default=60, ge=0, le=10_080)
    ativo: bool = True


class ServiceUpdateIn(InSchema):
    nome: str | None = Field(default=None, min_length=2, max_length=120)
    descricao: str | None = Field(default=None, max_length=2000)
    valor_base_centavos: int | None = Field(default=None, ge=0, le=100_000_000)
    duracao_estimada_min: int | None = Field(default=None, ge=0, le=10_080)
    ativo: bool | None = None

    @field_validator("nome")
    @classmethod
    def _nome_obrigatorio(cls, v: str | None) -> str:
        if v is None:
            raise ValueError("O nome não pode ficar vazio.")
        return v


class ServiceOut(OutSchema):
    id: int
    nome: str
    descricao: str | None
    valor_base_centavos: int
    duracao_estimada_min: int
    ativo: bool
    created_at: datetime
    updated_at: datetime
    # Só vêm preenchidos quando a lista foi pedida com `client_id`. É o que permite ao seletor de
    # serviço da OS mostrar o preço certo JÁ preenchido e, principalmente, dizer de onde ele veio —
    # sem o rótulo de origem, um preço combinado parece erro do sistema.
    valor_cliente_centavos: int | None = None
    valor_efetivo_centavos: int | None = None
