/** Formatadores: centavos → R$, telefone, placa, datas (fuso do navegador; servidor manda ISO com offset). */

const brl = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })

export function money(centavos: number | null | undefined): string {
  return brl.format((centavos ?? 0) / 100)
}

/** "5582999110001" → "(82) 99911-0001"; números não nacionais ficam como vieram com "+" */
export function phone(digits: string | null | undefined): string {
  if (!digits) return '—'
  if (digits.startsWith('55') && (digits.length === 12 || digits.length === 13)) {
    const ddd = digits.slice(2, 4)
    const rest = digits.slice(4)
    const split = rest.length === 9 ? 5 : 4
    return `(${ddd}) ${rest.slice(0, split)}-${rest.slice(split)}`
  }
  return `+${digits}`
}

/** Link do WhatsApp para um telefone normalizado. */
export function whatsappUrl(digits: string, text?: string): string {
  const q = text ? `?text=${encodeURIComponent(text)}` : ''
  return `https://wa.me/${digits}${q}`
}

/** "BRA2E19" → "BRA-2E19" (visual apenas; o backend guarda sem hífen) */
export function plate(placa: string | null | undefined): string {
  if (!placa) return 'sem placa'
  if (placa.length === 7) return `${placa.slice(0, 3)}-${placa.slice(3)}`
  return placa
}

const TZ = 'America/Maceio' // a data que importa é a da loja, não a do computador
const dateFmt = new Intl.DateTimeFormat('pt-BR', { timeZone: TZ, day: '2-digit', month: '2-digit', year: 'numeric' })
const dateTimeFmt = new Intl.DateTimeFormat('pt-BR', {
  timeZone: TZ,
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

export function date(iso: string | null | undefined): string {
  return iso ? dateFmt.format(new Date(iso)) : '—'
}

export function dateTime(iso: string | null | undefined): string {
  return iso ? dateTimeFmt.format(new Date(iso)) : '—'
}

export function initials(nome: string): string {
  const parts = nome.trim().split(/\s+/)
  return ((parts[0]?.[0] ?? '') + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase()
}

/** "30min", "1h 30min", "2d 4h" — usada no catálogo e ao montar a OS. */
export function duracao(min: number | null | undefined): string {
  if (!min) return '—'
  const d = Math.floor(min / 1440)
  const h = Math.floor((min % 1440) / 60)
  const m = min % 60
  return [d && `${d}d`, h && `${h}h`, m && `${m}min`].filter(Boolean).join(' ')
}

/**
 * Variação percentual contra um período anterior, ou null quando não há base de comparação.
 *
 * O null importa: dividir por zero viraria "∞%" na tela, e "+320%" num mês que saiu de R$ 50 não
 * quer dizer nada — por isso quem mostra a variação mostra também o valor absoluto ao lado.
 */
export function variacaoPct(atual: number, anterior: number): number | null {
  if (anterior <= 0) return null
  return ((atual - anterior) / anterior) * 100
}
