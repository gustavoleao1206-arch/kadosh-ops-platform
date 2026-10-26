"""A tela inicial. Só saída, e nenhum número nasce aqui — tudo vem dos serviços do assunto."""

from app.schemas.base import OutSchema


class DashboardHojeOut(OutSchema):
    dia: str
    recebido_centavos: int
    chegam_qtd: int
    no_patio_qtd: int
    orcamentos_abertos_qtd: int


class DashboardMesAnteriorOut(OutSchema):
    faturado_centavos: int
    recebido_centavos: int


class DashboardMesOut(OutSchema):
    label: str
    faturado_centavos: int
    recebido_centavos: int
    os_concluidas: int
    ticket_medio_centavos: int
    # para a seta de comparação: quem calcula a variação é a tela, com os dois números na mão
    mes_anterior: DashboardMesAnteriorOut


class CobrancaGrupoOut(OutSchema):
    qtd: int
    total_centavos: int


class DashboardCobrancaOut(OutSchema):
    pendentes: CobrancaGrupoOut
    atrasados: CobrancaGrupoOut


class DashboardOut(OutSchema):
    hoje: DashboardHojeOut
    mes: DashboardMesOut
    cobranca: DashboardCobrancaOut
