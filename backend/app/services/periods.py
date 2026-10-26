"""Períodos no fuso do negócio (America/Maceio).

Regra: o banco guarda UTC; "hoje", "esta semana" e "este mês" são calculados aqui, uma vez só, e
viram um intervalo [início, fim) usado em `coluna >= ini AND coluna < fim` — assim o índice é usado
(nada de `AT TIME ZONE` dentro do WHERE).
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.config import get_settings


def tz() -> ZoneInfo:
    return ZoneInfo(get_settings().APP_TIMEZONE)


def now_local() -> datetime:
    return datetime.now(tz())


def today_local() -> date:
    return now_local().date()


# O calendário que o sistema cobre. Fora disso é dedo errado no campo de data, e o motivo de existir
# é concreto: `d + timedelta(days=1)` em date.max estoura OverflowError e vira 500 sem mensagem.
DATA_MIN = date(2000, 1, 1)
DATA_MAX = date(2100, 12, 31)


def day_bounds(d: date) -> tuple[datetime, datetime]:
    """[00:00, 24:00) do dia local, em UTC."""
    if not (DATA_MIN <= d <= DATA_MAX):
        raise ValueError("Data fora do período que o sistema cobre (2000 a 2100).")
    zone = tz()
    ini = datetime.combine(d, time.min, tzinfo=zone)
    fim = datetime.combine(d + timedelta(days=1), time.min, tzinfo=zone)
    return ini.astimezone(ZoneInfo("UTC")), fim.astimezone(ZoneInfo("UTC"))


def dentro_do_calendario(dt: datetime | None) -> datetime | None:
    """Recusa data/hora fora de 2000–2100, com a mesma régua de `day_bounds`.

    A guarda existia só para os parâmetros de query (`?de=`, `?dia=`), mas as datas que chegam pelo
    CORPO — agendamento, previsão, vencimento, data do pagamento — passavam direto. E o estrago é o
    mesmo motivo original: `_refresh_previsao` faz `base + timedelta(minutes=...)`, e somar minutos
    a 9999-12-31 estoura OverflowError, que não é HTTPException nem IntegrityError — vira 500 sem
    mensagem, no meio de uma recepção.

    Chamada de dentro dos validadores do Pydantic: o ValueError vira 422 em português pelo handler
    que já existe, sem tocar em rota nenhuma.
    """
    if dt is not None and not (DATA_MIN <= dt.date() <= DATA_MAX):
        raise ValueError("Data fora do período que o sistema cobre (2000 a 2100).")
    return dt


def range_bounds(inicio: date, fim: date) -> tuple[datetime, datetime]:
    """[00:00 do primeiro dia, 24:00 do último) — ambos inclusivos em dias locais."""
    ini_utc, _ = day_bounds(inicio)
    _, fim_utc = day_bounds(fim)
    return ini_utc, fim_utc


def month_bounds(d: date | None = None) -> tuple[datetime, datetime]:
    d = d or today_local()
    inicio = d.replace(day=1)
    fim = (inicio + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return range_bounds(inicio, fim)


MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)


def mes_referencia(mes: str) -> date:
    """"2026-06" -> 1º de junho de 2026. Formato do <input type="month"> do painel."""
    try:
        ano, m = mes.split("-")
        d = date(int(ano), int(m), 1)
    except (ValueError, AttributeError) as e:
        raise ValueError("Mês inválido. Use o formato AAAA-MM.") from e
    if not (DATA_MIN <= d <= DATA_MAX):
        raise ValueError("Mês fora do período que o sistema cobre (2000 a 2100).")
    return d


def rotulo_mes(d: date) -> str:
    """"Junho de 2026" — o texto do período sai do backend, não do painel."""
    return f"{MESES[d.month - 1].capitalize()} de {d.year}"


def meses_ate(fim: date, quantos: int) -> list[date]:
    """Os N primeiros-dias-de-mês que terminam em `fim`, do mais antigo ao mais recente."""
    ref = fim.replace(day=1)
    saida = [ref]
    for _ in range(quantos - 1):
        ref = (ref - timedelta(days=1)).replace(day=1)
        saida.append(ref)
    return list(reversed(saida))


def periodo_bounds(
    periodo: str, de: date | None = None, ate: date | None = None, mes: str | None = None
) -> tuple[datetime, datetime, dict]:
    """Resolve "este mês" / "mês passado" / um mês qualquer / intervalo livre num par [ini, fim) UTC.

    Devolve também o rótulo pronto: quem escreve "Setembro de 2026" é o backend, não o painel.
    """
    if periodo == "personalizado":
        if de is None or ate is None:
            raise ValueError("Informe as duas datas do período.")
        if ate < de:
            raise ValueError("A data final não pode ser anterior à inicial.")
        if (ate - de).days > 366:
            raise ValueError("O período não pode passar de um ano.")
        ini, fim = range_bounds(de, ate)
        rotulo = f"{de.strftime('%d/%m/%Y')} a {ate.strftime('%d/%m/%Y')}"
        return ini, fim, {"chave": periodo, "de": de.isoformat(), "ate": ate.isoformat(), "label": rotulo}

    hoje = today_local()
    if periodo == "mes_passado":
        primeiro = hoje.replace(day=1) - timedelta(days=1)
    elif periodo == "mes":
        primeiro = hoje
    elif periodo == "mes_especifico":
        if not mes:
            raise ValueError("Informe o mês.")
        primeiro = mes_referencia(mes)
    else:
        raise ValueError("Período inválido.")

    ini, fim = month_bounds(primeiro)
    ultimo = (primeiro.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    rotulo = rotulo_mes(primeiro)
    return ini, fim, {
        "chave": periodo,
        "de": primeiro.replace(day=1).isoformat(),
        "ate": ultimo.isoformat(),
        "label": rotulo,
    }


def to_local(dt: datetime | None) -> datetime | None:
    return dt.astimezone(tz()) if dt else None


def assume_business_tz(dt: datetime | None) -> datetime | None:
    """Data/hora sem fuso vira horário do negócio (nunca UTC) — o app pode mandar naive."""
    if dt is None:
        return None
    return dt.replace(tzinfo=tz()) if dt.tzinfo is None else dt
