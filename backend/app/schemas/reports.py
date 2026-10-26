"""Relatórios: só saída. Os rótulos vêm prontos daqui — o painel e o app não montam texto."""

from datetime import datetime

from app.schemas.base import OutSchema


class PeriodoOut(OutSchema):
    chave: str
    de: str
    ate: str
    label: str


class TotaisOut(OutSchema):
    # o serviço entregue no período
    faturado_centavos: int
    # ...e quanto dele já entrou / ainda falta. As duas partes fecham com o faturado.
    faturado_recebido_centavos: int
    faturado_a_receber_centavos: int
    # o dinheiro que entrou no período, venha da OS que vier
    recebido_centavos: int
    os_concluidas: int
    ticket_medio_centavos: int
    desconto_centavos: int
    cancelamentos: int
    nao_comparecimentos: int
    # o que foi estornado dentro da janela (por `pago_em`), para o dono conciliar
    estornos_centavos: int


class ServicoLinhaOut(OutSchema):
    service_id: int
    nome: str
    quantidade: int
    total_centavos: int


class DiaSemanaOut(OutSchema):
    dia: int
    dia_label: str
    os_concluidas: int
    faturado_centavos: int


class FormaLinhaOut(OutSchema):
    forma: str
    forma_label: str
    total_centavos: int


class MesLinhaOut(OutSchema):
    mes: str
    label: str
    # "Set/26" — o eixo do gráfico não comporta "Setembro de 2026"
    label_curto: str
    faturado_centavos: int
    recebido_centavos: int
    os_concluidas: int


class SerieMensalOut(OutSchema):
    meses: list[MesLinhaOut]


class RelatorioOut(OutSchema):
    periodo: PeriodoOut
    # false = a loja ainda não concluiu nenhuma OS na vida (vazio diferente de "mês parado")
    tem_historico: bool
    totais: TotaisOut
    # de onde veio o dinheiro do período — mesma quebra do caixa e do extrato
    por_forma: list[FormaLinhaOut]
    por_servico: list[ServicoLinhaOut]
    por_dia_semana: list[DiaSemanaOut]


class ClientesSumidosOut(OutSchema):
    # total antes do corte: a lista mostra os que mais gastaram, e a tela avisa quando há mais
    total: int
    itens: list["ClienteSumidoOut"]


class ClienteSumidoOut(OutSchema):
    client_id: int
    nome: str
    telefone: str | None
    atendimentos: int
    total_gasto_centavos: int
    ultimo_atendimento: datetime
    dias_sem_voltar: int


ClientesSumidosOut.model_rebuild()
