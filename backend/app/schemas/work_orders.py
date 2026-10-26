from datetime import datetime

from pydantic import Field, field_validator, model_validator

from app.services.periods import assume_business_tz, dentro_do_calendario

from app.schemas.base import InSchema, OutSchema
from app.schemas.clients import ClientOut
from app.schemas.payments import PaymentOut
from app.schemas.vehicles import VehicleOut


class ItemIn(InSchema):
    service_id: int
    # vazio = usa o valor do catálogo no momento do lançamento
    valor_centavos: int | None = Field(default=None, ge=0, le=100_000_000)
    # uma por toque em "lançar": repetir o toque não lança o serviço duas vezes.
    # `min_length=8` pelo mesmo motivo do pagamento, mais um: string vazia passaria pela checagem
    # (`if chave`), seria GRAVADA — no Postgres '' não é NULL — e o segundo item vazio estouraria
    # o UNIQUE, virando 409 num lançamento perfeitamente legítimo.
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=64)


class WorkOrderCreateIn(InSchema):
    client_id: int
    vehicle_id: int | None = None
    # sem data = orçamento; com data = agendamento
    scheduled_at: datetime | None = None
    status: str | None = Field(default=None, pattern="^(orcamento|agendado)$")
    itens: list[ItemIn] = Field(default_factory=list, max_length=30)
    desconto_centavos: int = Field(default=0, ge=0, le=100_000_000)
    observacoes: str | None = Field(default=None, max_length=2000)

    @field_validator("scheduled_at")
    @classmethod
    def _com_fuso(cls, v: datetime | None) -> datetime | None:
        return dentro_do_calendario(assume_business_tz(v))

    @model_validator(mode="after")
    def _coerencia(self):
        if self.status == "agendado" and self.scheduled_at is None:
            raise ValueError("Informe a data e a hora do agendamento.")
        return self


class WorkOrderUpdateIn(InSchema):
    vehicle_id: int | None = None
    scheduled_at: datetime | None = None
    previsao_conclusao: datetime | None = None
    # Data-limite para receber. `null` limpa o prazo — e é a única edição que uma OS já concluída
    # aceita, porque o carro entregue devendo é justamente o que precisa ganhar data.
    vencimento: datetime | None = None
    desconto_centavos: int | None = Field(default=None, ge=0, le=100_000_000)
    # Por que este cliente levou abatimento. Vai para o evento de desconto, não para a OS: quem
    # guarda o porquê é o histórico, que é imutável.
    desconto_motivo: str | None = Field(default=None, max_length=500)
    observacoes: str | None = Field(default=None, max_length=2000)
    observacoes_entrada: str | None = Field(default=None, max_length=2000)

    @field_validator("scheduled_at", "previsao_conclusao", "vencimento")
    @classmethod
    def _com_fuso(cls, v: datetime | None) -> datetime | None:
        return dentro_do_calendario(assume_business_tz(v))

    @model_validator(mode="after")
    def _motivo_precisa_de_desconto(self):
        # motivo sozinho não tem onde ser gravado: o evento só nasce quando o valor muda
        if self.desconto_motivo is not None and self.desconto_centavos is None:
            raise ValueError("Informe o desconto junto com o motivo.")
        return self


class TransitionIn(InSchema):
    to_status: str = Field(max_length=24)
    # o cliente manda o status que viu na tela; se mudou, a API responde 409
    expected_status: str | None = Field(default=None, max_length=24)
    motivo: str | None = Field(default=None, max_length=500)


class ItemOut(OutSchema):
    id: int
    service_id: int
    descricao: str
    valor_centavos: int
    created_at: datetime


class EventOut(OutSchema):
    id: int
    tipo: str
    descricao: str
    de: str | None
    para: str | None
    motivo: str | None
    user_id: int | None
    created_at: datetime


class TransitionOut(OutSchema):
    status: str
    label: str
    acao_label: str
    tone: str
    requer_motivo: bool
    principal: bool


class WorkOrderOut(OutSchema):
    id: int
    numero: int | None
    previsao_manual: bool
    status: str
    status_label: str
    status_tone: str
    client_id: int
    vehicle_id: int | None
    scheduled_at: datetime | None
    entrada: datetime | None
    previsao_conclusao: datetime | None
    conclusao: datetime | None
    vencimento: datetime | None
    desconto_centavos: int
    valor_total_centavos: int
    # o cliente nunca soma centavos: quanto entrou e quanto falta vêm prontos
    pago_centavos: int
    saldo_centavos: int
    # Vem na lista pelo mesmo motivo de `acoes`: o card do celular decide o que escrever sobre
    # dinheiro, e a casa proíbe decidir isso pelo sinal do saldo.
    aceita_pagamento: bool
    # A régua de cobrança pronta — pago / a receber / atrasado, com rótulo e cor. `None` quando esta
    # OS não é uma cobrança (orçamento, cancelada, total zero). O cliente NÃO recalcula: a data de
    # corte do atraso é do servidor, e um celular com o relógio errado inventaria atraso.
    situacao_cobranca: str | None
    situacao_cobranca_label: str | None
    situacao_cobranca_tone: str | None
    observacoes: str | None
    observacoes_entrada: str | None
    created_at: datetime
    updated_at: datetime
    itens: list[ItemOut]
    cliente: ClientOut
    veiculo: VehicleOut | None
    # O que dá para fazer com esta OS agora. Vem também na lista/pátio/agenda porque um cliente de
    # celular precisa do botão de status no próprio card — sem isto ele teria que buscar cada OS
    # uma a uma, ou reimplementar TRANSITIONS, que é justamente o que a casa proíbe.
    acoes: list["TransitionOut"]


class WorkOrderDetailOut(WorkOrderOut):
    eventos: list[EventOut]
    pagamentos: list[PaymentOut]


class AgendaResumoOut(OutSchema):
    agendados: int
    confirmados: int
    no_patio: int
    orcamentos_abertos: int


class AgendaOut(OutSchema):
    dia: str
    resumo: AgendaResumoOut
    itens: list[WorkOrderOut]


class PatioOut(OutSchema):
    """Carros na loja agora, agrupados por status."""

    recebido: list[WorkOrderOut]
    em_execucao: list[WorkOrderOut]
    aguardando_retirada: list[WorkOrderOut]
