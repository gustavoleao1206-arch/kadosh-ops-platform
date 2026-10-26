"""Recepção do veículo: uma tela, uma transação.

O balcão manda tudo de uma vez — cliente (existente ou novo), veículo (existente ou novo), serviços e
o estado do carro na chegada. O backend cria o que faltar e abre a OS já recebida.
"""

from datetime import datetime

from pydantic import EmailStr, Field, field_validator, model_validator

from app.core.text import normalize_placa, normalize_telefone
from app.services.periods import assume_business_tz, dentro_do_calendario
from app.schemas.base import InSchema
from app.schemas.work_orders import ItemIn


class IntakeClienteIn(InSchema):
    """Um id (cliente já cadastrado) ou nome + telefone (cadastra na hora)."""

    id: int | None = None
    nome: str | None = Field(default=None, min_length=2, max_length=120)
    telefone: str | None = Field(default=None, max_length=30)
    email: EmailStr | None = None

    @field_validator("telefone")
    @classmethod
    def _normalize_telefone(cls, v: str | None) -> str | None:
        return normalize_telefone(v)

    @model_validator(mode="after")
    def _completo(self):
        if self.id is None and not self.nome:
            raise ValueError("Informe o cliente ou o nome de um novo.")
        return self


class IntakeVeiculoIn(InSchema):
    """Um id (veículo do cliente) ou os dados mínimos (modelo; placa é opcional)."""

    id: int | None = None
    placa: str | None = Field(default=None, max_length=12)
    marca: str | None = Field(default=None, max_length=60)
    modelo: str | None = Field(default=None, min_length=1, max_length=80)
    cor: str | None = Field(default=None, max_length=40)
    ano: int | None = Field(default=None, ge=1950, le=2100)

    @field_validator("placa")
    @classmethod
    def _normalize_placa(cls, v: str | None) -> str | None:
        return normalize_placa(v)

    @model_validator(mode="after")
    def _completo(self):
        if self.id is None and not self.modelo:
            raise ValueError("Informe o veículo ou o modelo de um novo.")
        return self


class IntakeIn(InSchema):
    # Recebendo um agendamento (work_order_id), cliente e veículo já estão na OS: só vêm aqui se
    # o carro que chegou for outro. Sem work_order_id, os dois são obrigatórios.
    cliente: IntakeClienteIn | None = None
    veiculo: IntakeVeiculoIn | None = None
    itens: list[ItemIn] = Field(default_factory=list, max_length=30)
    desconto_centavos: int = Field(default=0, ge=0, le=100_000_000)
    # estado do carro ao chegar: riscos, pertences, combustível — a defesa da loja numa reclamação
    observacoes_entrada: str | None = Field(default=None, max_length=2000)
    observacoes: str | None = Field(default=None, max_length=2000)
    previsao_conclusao: datetime | None = None
    # veio de um agendamento? então não cria OS nova: recebe aquela.
    # gt=0: sem isso, work_order_id=0 passa pelo validador (que testa `is None`) e cai no caminho
    # de OS nova sem cliente nenhum.
    work_order_id: int | None = Field(default=None, gt=0)

    @field_validator("previsao_conclusao")
    @classmethod
    def _com_fuso(cls, v: datetime | None) -> datetime | None:
        return dentro_do_calendario(assume_business_tz(v))
    # Obrigatória, pelo mesmo motivo do pagamento: sem ela o toque repetido abre uma segunda OS
    # com cliente e veículo duplicados, e o balcão só descobre depois.
    idempotency_key: str = Field(min_length=8, max_length=64)

    @model_validator(mode="after")
    def _completo(self):
        if self.work_order_id is None and (self.cliente is None or self.veiculo is None):
            raise ValueError("Informe o cliente e o veículo, ou a OS agendada que está sendo recebida.")
        return self
