"""A primeira tela: o dia, o mês e quem deve — numa chamada só.

Este módulo NÃO tem contas próprias. Ele só junta o que o caixa, o relatório, a agenda e a régua de
cobrança já respondem, e a razão é dura: no minuto em que o dashboard somar dinheiro por conta
própria, ele vai discordar do caixa num centavo qualquer e o dono para de confiar nos dois. Se
faltar um número aqui, o lugar de criá-lo é o serviço dono do assunto — nunca este arquivo.

Existe como endpoint (e não como três chamadas do painel) porque a home do app abre no balcão, no
celular, muitas vezes por dia: uma requisição, um skeleton, um desenho.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.services import billing, reports
from app.services import work_orders as wo_service
from app.services.payments import recebido_centavos
from app.services.periods import day_bounds, month_bounds, rotulo_mes, today_local


def resumo(db: Session) -> dict:
    hoje = today_local()
    ini_dia, fim_dia = day_bounds(hoje)
    ini_mes, fim_mes = month_bounds(hoje)
    # último dia do mês passado = véspera do dia 1 deste (vale para janeiro sem caso especial)
    ini_ant, fim_ant = month_bounds(hoje.replace(day=1) - timedelta(days=1))

    # contadores, não a agenda inteira: aqui só se leem quatro números
    agenda = wo_service.contadores_do_dia(db, hoje)
    do_mes = reports.totais(db, ini_mes, fim_mes)
    anterior = reports.totais(db, ini_ant, fim_ant)
    cobranca = billing.resumo(db, datetime.now(timezone.utc))

    return {
        "hoje": {
            "dia": hoje.isoformat(),
            "recebido_centavos": recebido_centavos(db, ini_dia, fim_dia),
            "chegam_qtd": agenda["agendados"] + agenda["confirmados"],
            "no_patio_qtd": agenda["no_patio"],
            "orcamentos_abertos_qtd": agenda["orcamentos_abertos"],
        },
        "mes": {
            "label": rotulo_mes(hoje),
            "faturado_centavos": do_mes["faturado_centavos"],
            "recebido_centavos": do_mes["recebido_centavos"],
            "os_concluidas": do_mes["os_concluidas"],
            "ticket_medio_centavos": do_mes["ticket_medio_centavos"],
            "mes_anterior": {
                "faturado_centavos": anterior["faturado_centavos"],
                "recebido_centavos": anterior["recebido_centavos"],
            },
        },
        "cobranca": {
            "pendentes": cobranca["pendente"],
            "atrasados": cobranca["atrasado"],
        },
    }
