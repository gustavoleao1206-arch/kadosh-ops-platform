"""Valores fixos do domínio. Guardados como texto + CHECK no banco (sem ENUM nativo, que é chato de migrar)."""

ROLES = ("admin", "staff")

SESSION_CLIENTS = ("web", "android")

AUTH_EVENTS = (
    "login_ok",
    "login_falha",
    "logout",
    "logout_todos",
    "senha_alterada",
    "senha_resetada",
    "acesso_negado",
    "usuario_criado",
    "usuario_alterado",
)

# Um fluxo só: orçamento → agenda → pátio → entregue.
WORK_ORDER_STATUSES = (
    "orcamento",
    "agendado",
    "confirmado",
    "recebido",
    "em_execucao",
    "aguardando_retirada",
    "concluido",
    "cancelado",
    "nao_compareceu",
)

# Rótulos e cores são a fonte única para web e Android (vêm na resposta da API).
WORK_ORDER_STATUS_LABELS = {
    "orcamento": "Orçamento",
    "agendado": "Agendado",
    "confirmado": "Confirmado",
    "recebido": "Recebido",
    "em_execucao": "Em execução",
    "aguardando_retirada": "Aguardando retirada",
    "concluido": "Concluído",
    "cancelado": "Cancelado",
    "nao_compareceu": "Não compareceu",
}

# Status em que o carro está fisicamente no pátio.
STATUSES_NO_PATIO = ("recebido", "em_execucao", "aguardando_retirada")
STATUSES_TERMINAIS = ("concluido", "cancelado", "nao_compareceu")

# Onde a OS pode existir sem veículo: um orçamento ainda não tem carro definido, e um orçamento
# recusado precisa poder ser cancelado. Os demais status só existem com carro.
STATUSES_SEM_VEICULO = ("orcamento", "cancelado")

# Dinheiro só entra a partir da recepção do veículo. Antes disso a OS ainda não tem número (e por
# isso pode ser excluída), e um sinal pago antes da chegada é lançado na recepção com a data real.
STATUSES_ACEITAM_PAGAMENTO = ("recebido", "em_execucao", "aguardando_retirada", "concluido")

WORK_ORDER_EVENT_TYPES = (
    "status",
    "desconto",
    "item",
    "pagamento",
    "reabertura",
    "remarcacao",
    "transferencia",
    "entrada",
    "vencimento",
)

FORMAS_PAGAMENTO = ("dinheiro", "pix", "debito", "credito", "transferencia", "outros")

FORMAS_PAGAMENTO_LABELS = {
    "dinheiro": "Dinheiro",
    "pix": "Pix",
    "debito": "Cartão de débito",
    "credito": "Cartão de crédito",
    "transferencia": "Transferência",
    "outros": "Outros",
}


def sql_in(values: tuple[str, ...]) -> str:
    """Gera a lista para CHECK (col IN (...))."""
    return ", ".join(f"'{v}'" for v in values)


# Situação de cobrança de uma OS. SEMPRE derivada de (total, recebido, vencimento, status) — nunca
# gravada: uma coluna "status de pagamento" vira mentira sozinha, no dia seguinte, quando o
# vencimento passa e ninguém tocou na linha.
SITUACOES_COBRANCA = ("pago", "pendente", "atrasado")

SITUACAO_COBRANCA_LABELS = {
    "pago": "Pago",
    "pendente": "A receber",
    "atrasado": "Atrasado",
}

# Mesma tríade semântica do resto do sistema. Vermelho com parcimônia: se tudo é perigo, nada urge.
SITUACAO_COBRANCA_TONES = {
    "pago": "ok",
    "pendente": "warn",
    "atrasado": "danger",
}
