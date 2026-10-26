"""Pagamentos e fechamento do dia.

Não existe schema de edição: pagamento errado é estornado e relançado, nunca alterado.
"""

from datetime import datetime

from pydantic import Field, field_validator

from app.models.enums import FORMAS_PAGAMENTO
from app.schemas.base import InSchema, OutSchema
from app.services.periods import assume_business_tz, dentro_do_calendario, day_bounds, today_local


class PaymentIn(InSchema):
    valor_centavos: int = Field(gt=0, le=100_000_000)
    forma: str
    # Pix que caiu ontem e só foi lançado hoje: o caixa soma pela data real do dinheiro.
    pago_em: datetime | None = None
    observacao: str | None = Field(default=None, max_length=500)
    # Obrigatória: é dinheiro. Opcional, dependeria da disciplina de todo cliente presente e futuro,
    # e o cliente que esquecesse duplicaria pagamento em silêncio — o sintoma só apareceria no caixa.
    idempotency_key: str = Field(min_length=8, max_length=64)

    @field_validator("forma")
    @classmethod
    def _forma_valida(cls, v: str) -> str:
        if v not in FORMAS_PAGAMENTO:
            raise ValueError("Forma de pagamento inválida.")
        return v

    @field_validator("pago_em")
    @classmethod
    def _com_fuso(cls, v: datetime | None) -> datetime | None:
        v = dentro_do_calendario(assume_business_tz(v))
        if v is not None and v >= day_bounds(today_local())[1]:
            raise ValueError("A data do pagamento não pode ser no futuro.")
        return v


class EstornoIn(InSchema):
    motivo: str = Field(min_length=1, max_length=500)


class PaymentOut(OutSchema):
    id: int
    valor_centavos: int
    forma: str
    forma_label: str
    pago_em: datetime
    created_at: datetime
    observacao: str | None
    estornado_em: datetime | None
    estorno_motivo: str | None
    created_by: int | None
    # calculado para quem pediu: o cliente não reimplementa a regra de quem pode estornar
    pode_estornar: bool


class FormaPagamentoOut(OutSchema):
    valor: str
    label: str


class CaixaFormaOut(OutSchema):
    forma: str
    forma_label: str
    total_centavos: int


class CaixaLancamentoOut(OutSchema):
    id: int
    work_order_id: int
    numero: int | None
    cliente_nome: str
    valor_centavos: int
    forma: str
    forma_label: str
    pago_em: datetime
    created_at: datetime
    observacao: str | None
    estornado_em: datetime | None
    estorno_motivo: str | None


class CaixaDevedorOut(OutSchema):
    work_order_id: int
    numero: int | None
    cliente_nome: str
    status: str
    status_label: str
    status_tone: str
    valor_total_centavos: int
    pago_centavos: int
    saldo_centavos: int
    # a régua de cobrança, com rótulo e cor prontos: a lista do caixa fala a mesma língua da OS
    situacao_cobranca: str | None
    situacao_cobranca_label: str | None
    situacao_cobranca_tone: str | None
    vencimento: datetime | None


class CaixaOut(OutSchema):
    dia: str
    recebido_centavos: int
    por_forma: list[CaixaFormaOut]
    lancamentos: list[CaixaLancamentoOut]
    a_receber_centavos: int
    a_receber: list[CaixaDevedorOut]


class ExtratoOut(OutSchema):
    """O caixa esticado no tempo. Mesmo critério: soma por `pago_em`, estornado aparece e não conta."""

    periodo: "PeriodoExtratoOut"
    total_centavos: int
    # o que está riscado nesta janela — a linha que faz a conferência manual fechar
    estornos_centavos: int
    por_forma: list[CaixaFormaOut]
    lancamentos: list[CaixaLancamentoOut]
    # paginação: `total` conta TODOS os lançamentos da janela, inclusive os estornados listados
    total: int
    page: int
    page_size: int


class PeriodoExtratoOut(OutSchema):
    de: str
    ate: str
    label: str


ExtratoOut.model_rebuild()
