from datetime import datetime

from pydantic import AliasChoices, EmailStr, Field, field_validator

from app.core.text import normalize_telefone
from app.schemas.base import InSchema, OutSchema


class _TelefoneMixin:
    @field_validator("telefone", check_fields=False)
    @classmethod
    def _normalize_telefone(cls, v: str | None) -> str | None:
        return normalize_telefone(v)


class ClientCreateIn(_TelefoneMixin, InSchema):
    nome: str = Field(min_length=2, max_length=120)
    telefone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    observacoes: str | None = Field(default=None, max_length=2000)


class ClientUpdateIn(_TelefoneMixin, InSchema):
    nome: str | None = Field(default=None, min_length=2, max_length=120)
    telefone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None
    observacoes: str | None = Field(default=None, max_length=2000)

    @field_validator("nome")
    @classmethod
    def _nome_obrigatorio(cls, v: str | None) -> str:
        if v is None:
            raise ValueError("O nome não pode ficar vazio.")
        return v


class VehicleMiniOut(OutSchema):
    id: int
    placa: str | None
    marca: str | None
    modelo: str
    cor: str | None
    ano: int | None
    descricao: str
    arquivado_em: datetime | None


class ClientOut(OutSchema):
    id: int
    nome: str
    telefone: str | None
    email: str | None
    observacoes: str | None
    arquivado_em: datetime | None
    created_at: datetime
    updated_at: datetime
    # atributo do modelo é `vehicles`; na API o nome é `veiculos`
    veiculos: list[VehicleMiniOut] = Field(default_factory=list, validation_alias=AliasChoices("veiculos", "vehicles"))


class ClientStatsOut(OutSchema):
    atendimentos: int
    total_gasto_centavos: int
    ultimo_atendimento: datetime | None


class WorkOrderSummaryOut(OutSchema):
    """Resumo de OS para históricos (cliente, veículo). Completo na fase 4."""

    id: int
    numero: int | None
    status: str
    status_label: str
    scheduled_at: datetime | None
    entrada: datetime | None
    conclusao: datetime | None
    valor_total_centavos: int
    vehicle_id: int | None
    veiculo: str | None
    # quem era o dono na OS (veículo transferido mantém o histórico de cada dono)
    client_id: int
    cliente: str


class ClientDetailOut(ClientOut):
    stats: ClientStatsOut
    historico: list[WorkOrderSummaryOut] = []


class DuplicatePhoneOut(OutSchema):
    detail: str
    existente: ClientOut
