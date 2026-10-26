"""Leitura do caixa. O lançamento acontece dentro da OS — aqui só se confere o dia.

Liberado para o sócio (CurrentUser), coerente com a decisão 4 da arquitetura: "staff vê e opera
tudo"; só estorno de terceiros, catálogo, usuários e exclusões são do administrador.
"""

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.core.deps import DB, CurrentUser
from app.models.enums import FORMAS_PAGAMENTO
from app.schemas.dashboard import DashboardOut
from app.schemas.payments import CaixaOut, ExtratoOut, FormaPagamentoOut
from app.services import dashboard as dashboard_svc
from app.services import payments as svc
from app.services.periods import periodo_bounds

router = APIRouter(tags=["financeiro"])


@router.get("/payment-methods", response_model=list[FormaPagamentoOut])
def payment_methods(_user: CurrentUser) -> list[FormaPagamentoOut]:
    """Formas de pagamento com rótulo pronto — nenhum literal "Pix" no painel ou no app."""
    return [FormaPagamentoOut(**f) for f in svc.formas()]


@router.get("/caixa", response_model=CaixaOut)
def caixa(db: DB, _user: CurrentUser, dia: date | None = None) -> CaixaOut:
    """Fechamento de um dia da loja: quanto entrou, em quê, e quem ainda deve."""
    try:
        return CaixaOut(**svc.caixa(db, dia))
    except ValueError as e:  # data fora do calendário do sistema
        raise HTTPException(422, str(e)) from e


@router.get("/extrato", response_model=ExtratoOut)
def extrato(
    db: DB,
    _user: CurrentUser,
    de: date,
    ate: date,
    forma: str | None = Query(None, description="filtra por forma de pagamento"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> ExtratoOut:
    """Os lançamentos de um intervalo. O caixa esticado no tempo, com o mesmo critério de soma.

    O limite de um ano é o mesmo do relatório, e vem do próprio `periodo_bounds`: intervalo maior é
    quase sempre dedo errado no campo de data, e traria a loja inteira para a memória.
    """
    if forma is not None and forma not in FORMAS_PAGAMENTO:
        raise HTTPException(422, "Forma de pagamento inválida.")
    try:
        ini, fim, meta = periodo_bounds("personalizado", de, ate)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    dados = svc.extrato(db, ini, fim, forma=forma, page=page, page_size=page_size)
    return ExtratoOut(
        periodo={"de": meta["de"], "ate": meta["ate"], "label": meta["label"]},
        page=page,
        page_size=page_size,
        **dados,
    )


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(db: DB, _user: CurrentUser) -> DashboardOut:
    """A primeira tela: o dia, o mês e quem deve — numa chamada só.

    Todos os números aqui saem dos mesmos serviços do caixa e do relatório. Se um dia divergirem,
    o bug é de reuso, não de arredondamento.
    """
    return DashboardOut(**dashboard_svc.resumo(db))
