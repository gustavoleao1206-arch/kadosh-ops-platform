"""Relatórios do período e clientes sumidos.

Liberado para o sócio (`CurrentUser`), na mesma linha da decisão sobre o `/caixa`: staff vê e opera
tudo; só estorno de terceiros, catálogo, usuários e exclusões são do administrador.
"""

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.core.deps import DB, CurrentUser
from app.schemas.reports import ClientesSumidosOut, RelatorioOut, SerieMensalOut
from app.services import reports as svc
from app.services.periods import periodo_bounds

router = APIRouter(tags=["relatórios"])


@router.get("/relatorios", response_model=RelatorioOut)
def relatorio(
    db: DB,
    _user: CurrentUser,
    periodo: str = Query("mes", pattern="^(mes|mes_passado|mes_especifico|personalizado)$"),
    de: date | None = None,
    ate: date | None = None,
    mes: str | None = Query(None, pattern=r"^\d{4}-\d{2}$", description="AAAA-MM, com periodo=mes_especifico"),
) -> RelatorioOut:
    """Os números de um período. Quem resolve fuso e rótulo é `periodo_bounds`, não a rota."""
    try:
        ini, fim, meta = periodo_bounds(periodo, de, ate, mes)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return RelatorioOut(periodo=meta, tem_historico=svc.tem_historico(db), **svc.relatorio(db, ini, fim))


@router.get("/relatorios/clientes-sumidos", response_model=ClientesSumidosOut)
def clientes_sumidos(db: DB, _user: CurrentUser, dias: int = Query(90, ge=30, le=730)) -> ClientesSumidosOut:
    """Quem já foi cliente e não volta há mais de N dias — o relatório que vira ligação."""
    return ClientesSumidosOut(**svc.clientes_sumidos(db, dias))


@router.get("/relatorios/mensal", response_model=SerieMensalOut)
def serie_mensal(db: DB, _user: CurrentUser, meses: int = Query(12, ge=1, le=24)) -> SerieMensalOut:
    """Faturado e recebido mês a mês — a série do gráfico de evolução.

    Teto de 24 meses: dois anos é o que cabe num gráfico legível, e o que evita varrer a loja
    inteira para desenhar barras que ninguém consegue ler.
    """
    return SerieMensalOut(meses=svc.serie_mensal(db, meses))
