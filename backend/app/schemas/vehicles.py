from datetime import datetime

from pydantic import AliasChoices, Field, field_validator

from app.core.text import normalize_placa
from app.schemas.base import InSchema, OutSchema
from app.schemas.clients import WorkOrderSummaryOut


class _PlacaMixin:
    @field_validator("placa", check_fields=False)
    @classmethod
    def _normalize_placa(cls, v: str | None) -> str | None:
        return normalize_placa(v)


class VehicleCreateIn(_PlacaMixin, InSchema):
    client_id: int
    placa: str | None = Field(default=None, max_length=12)
    marca: str | None = Field(default=None, max_length=60)
    modelo: str = Field(min_length=1, max_length=80)
    cor: str | None = Field(default=None, max_length=40)
    ano: int | None = Field(default=None, ge=1950, le=2100)
    observacoes: str | None = Field(default=None, max_length=2000)


class VehicleUpdateIn(_PlacaMixin, InSchema):
    placa: str | None = Field(default=None, max_length=12)
    marca: str | None = Field(default=None, max_length=60)
    modelo: str | None = Field(default=None, min_length=1, max_length=80)
    cor: str | None = Field(default=None, max_length=40)
    ano: int | None = Field(default=None, ge=1950, le=2100)
    observacoes: str | None = Field(default=None, max_length=2000)
    # explícito para "remover a placa" (PATCH com placa: null não distingue de ausente)
    remover_placa: bool = False

    @field_validator("modelo")
    @classmethod
    def _modelo_obrigatorio(cls, v: str | None) -> str:
        if v is None:
            raise ValueError("O modelo não pode ficar vazio.")
        return v


class VehicleTransferIn(InSchema):
    client_id: int


class ClientMiniOut(OutSchema):
    id: int
    nome: str
    telefone: str | None
    arquivado_em: datetime | None


class VehicleOut(OutSchema):
    id: int
    client_id: int
    placa: str | None
    marca: str | None
    modelo: str
    cor: str | None
    ano: int | None
    observacoes: str | None
    descricao: str
    arquivado_em: datetime | None
    created_at: datetime
    updated_at: datetime
    # atributo do modelo é `client`; na API o nome é `cliente`
    cliente: ClientMiniOut = Field(validation_alias=AliasChoices("cliente", "client"))


class VehicleDetailOut(VehicleOut):
    historico: list[WorkOrderSummaryOut] = []
