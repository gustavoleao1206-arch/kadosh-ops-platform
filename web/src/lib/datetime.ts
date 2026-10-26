/**
 * Datas no fuso do NEGÓCIO (America/Maceio), não no do computador.
 *
 * O painel pode ser aberto de qualquer lugar; a agenda é a da loja. Por isso as conversões entre
 * `<input type="datetime-local">` e o ISO da API passam sempre pelo fuso fixo abaixo.
 */

export const BUSINESS_TZ = 'America/Maceio'

const pad = (n: number) => String(n).padStart(2, '0')

/** Quanto o fuso do negócio está adiantado em relação ao UTC naquele instante (ms). */
function tzOffsetMs(instante: Date): number {
  const dtf = new Intl.DateTimeFormat('en-US', {
    timeZone: BUSINESS_TZ,
    hour12: false,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
  const p = Object.fromEntries(dtf.formatToParts(instante).map((x) => [x.type, x.value])) as Record<string, string>
  const comoUtc = Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour % 24, +p.minute, +p.second)
  return comoUtc - instante.getTime()
}

/** Campos de data/hora do instante, já no fuso do negócio. */
function partes(instante: Date) {
  const deslocado = new Date(instante.getTime() + tzOffsetMs(instante))
  return {
    ano: deslocado.getUTCFullYear(),
    mes: deslocado.getUTCMonth() + 1,
    dia: deslocado.getUTCDate(),
    hora: deslocado.getUTCHours(),
    min: deslocado.getUTCMinutes(),
  }
}

/** Instante → "2026-08-21T14:30" na hora da loja (valor do input). */
export function localInputValue(d: Date): string {
  const p = partes(d)
  return `${p.ano}-${pad(p.mes)}-${pad(p.dia)}T${pad(p.hora)}:${pad(p.min)}`
}

/** "2026-08-21T14:30" (hora da loja) → ISO UTC para a API. */
export function toIsoFromLocalInput(valor: string): string | null {
  if (!valor) return null
  const [data, hora] = valor.split('T')
  const [y, mo, d] = data.split('-').map(Number)
  const [h, mi] = (hora ?? '00:00').split(':').map(Number)
  if ([y, mo, d, h, mi].some((n) => Number.isNaN(n))) return null
  const comoUtc = Date.UTC(y, mo - 1, d, h, mi)
  // duas passadas cobrem a virada de horário de verão
  let ts = comoUtc - tzOffsetMs(new Date(comoUtc))
  ts = comoUtc - tzOffsetMs(new Date(ts))
  return new Date(ts).toISOString()
}

export function isoToLocalInput(iso: string | null | undefined): string {
  return iso ? localInputValue(new Date(iso)) : ''
}

/** "2026-08-21" na data da loja — o que a API espera em ?dia= */
export function dateOnly(d: Date): string {
  return localInputValue(d).slice(0, 10)
}

export function addDays(d: Date, dias: number): Date {
  const out = new Date(d)
  out.setDate(out.getDate() + dias)
  return out
}

const opts = { timeZone: BUSINESS_TZ } as const
const diaSemana = new Intl.DateTimeFormat('pt-BR', { ...opts, weekday: 'long' })
const diaCurto = new Intl.DateTimeFormat('pt-BR', { ...opts, weekday: 'short', day: '2-digit', month: '2-digit' })
const horaFmt = new Intl.DateTimeFormat('pt-BR', { ...opts, hour: '2-digit', minute: '2-digit' })
const dataCurta = new Intl.DateTimeFormat('pt-BR', { ...opts, day: '2-digit', month: '2-digit' })

export function weekdayLong(d: Date): string {
  return diaSemana.format(d)
}

export function weekdayShort(d: Date): string {
  return diaCurto.format(d).replace('.', '')
}

const diaMinusculo = new Intl.DateTimeFormat('pt-BR', { ...opts, weekday: 'short' })

/** Só o dia da semana ("sex"), para colunas estreitas. */
export function weekdayTiny(d: Date | string): string {
  return diaMinusculo.format(typeof d === 'string' ? new Date(d) : d).replace('.', '')
}

export function hour(iso: string | null | undefined): string {
  return iso ? horaFmt.format(new Date(iso)) : '—'
}

export function shortDate(d: Date | string): string {
  return dataCurta.format(typeof d === 'string' ? new Date(d) : d)
}

export function isToday(d: Date): boolean {
  return dateOnly(d) === dateOnly(new Date())
}

/** Mesmo dia da loja para dois instantes (ex.: entrada de ontem aparecendo hoje). */
export function sameBusinessDay(a: string | Date, b: string | Date): boolean {
  return dateOnly(typeof a === 'string' ? new Date(a) : a) === dateOnly(typeof b === 'string' ? new Date(b) : b)
}
