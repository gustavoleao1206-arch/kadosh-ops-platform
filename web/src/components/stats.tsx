/**
 * Peças de informação numérica: cartão de indicador, valor monetário, abas e esqueleto.
 *
 * Regra tipográfica da casa, aplicada aqui: UM número-herói por tela (o `destaque`), secundários
 * menores, rótulo em Oswald caixa-alta espaçada. Todo dígito com `tabular-nums`, senão coluna de
 * valores dança a cada centavo que muda.
 *
 * Regra de cor: ouro é MARCA e ação, nunca dinheiro. Valor monetário sai em `ink`. Quem fala de
 * estado financeiro é a tríade semântica — ok / warn / danger — e `danger` com parcimônia: se tudo
 * é vermelho, nada é urgente.
 */

import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { ArrowDownRight, ArrowRight, ArrowUpRight } from 'lucide-react'
import { cx } from './ui'
import { money } from '../lib/format'

/** Valor em reais com dígitos alinhados. Use em toda coluna e todo cartão. */
export function Dinheiro({ centavos, className }: { centavos: number | null | undefined; className?: string }) {
  return <span className={cx('tabular', className)}>{money(centavos)}</span>
}

export function StatCard({
  label,
  valor,
  detalhe,
  tone,
  destaque,
  to,
  variacao,
  icone,
}: {
  label: string
  /** já formatado: o cartão não decide se é dinheiro, contagem ou texto */
  valor: ReactNode
  detalhe?: ReactNode
  tone?: 'ok' | 'warn' | 'danger'
  /** o número-herói da tela — só um por página */
  destaque?: boolean
  to?: string
  /** variação percentual contra o período anterior; null quando não há base de comparação */
  variacao?: number | null
  icone?: ReactNode
}) {
  const corpo = (
    <div
      className={cx(
        'h-full rounded-lg border bg-surface px-4 py-3.5 shadow-card transition',
        tone === 'danger' ? 'border-danger/35' : tone === 'warn' ? 'border-warn/30' : 'border-line',
        to && 'group-hover:border-gold/50',
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="label-dim">{label}</div>
        {icone}
      </div>
      <div
        className={cx(
          'tabular mt-2 font-display font-semibold leading-none text-balance',
          destaque ? 'text-[40px]' : 'text-[26px]',
          tone === 'danger' ? 'text-danger' : tone === 'warn' ? 'text-warn' : tone === 'ok' ? 'text-ok' : 'text-ink',
        )}
      >
        {valor}
      </div>
      <div className="mt-2.5 flex items-center justify-between gap-2">
        <div className="min-w-0 truncate text-[12.5px] text-muted">{detalhe}</div>
        {variacao !== undefined && variacao !== null && <Variacao pct={variacao} />}
      </div>
      {to && (
        <div className="mt-3 flex items-center gap-1 text-[12.5px] text-muted group-hover:text-gold-deep">
          Abrir <ArrowRight className="h-3.5 w-3.5" />
        </div>
      )}
    </div>
  )
  return to ? (
    <Link to={to} className="group block">
      {corpo}
    </Link>
  ) : (
    corpo
  )
}

/**
 * Variação contra o período anterior.
 *
 * Verde/vermelho aqui é sobre DIREÇÃO, não sobre saúde: subir faturamento é bom, e é só isso que
 * a seta diz. Por isso o número vem sempre acompanhado do valor absoluto no cartão — "+320%" num
 * mês que saiu de R$ 50 não quer dizer nada sozinho.
 */
function Variacao({ pct }: { pct: number }) {
  const sobe = pct >= 0
  const Icone = sobe ? ArrowUpRight : ArrowDownRight
  return (
    <span
      className={cx(
        'tabular flex shrink-0 items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[11.5px] font-medium',
        sobe ? 'bg-ok-wash text-ok' : 'bg-danger-wash text-danger',
      )}
      title="Comparado ao mesmo período anterior"
    >
      <Icone className="h-3 w-3" />
      {sobe ? '+' : ''}
      {Math.round(pct)}%
    </span>
  )
}

export function SegmentedTabs<T extends string>({
  valor,
  opcoes,
  onChange,
}: {
  valor: T
  opcoes: { valor: T; label: string; contagem?: number }[]
  onChange: (v: T) => void
}) {
  return (
    <div className="inline-flex flex-wrap gap-1 rounded-lg border border-line bg-surface-2 p-1" role="tablist">
      {opcoes.map((o) => {
        const ativo = o.valor === valor
        return (
          <button
            key={o.valor}
            type="button"
            role="tab"
            aria-selected={ativo}
            onClick={() => onChange(o.valor)}
            className={cx(
              'rounded-md px-3 py-1.5 text-[13px] transition',
              ativo ? 'bg-surface text-ink shadow-card' : 'text-muted hover:text-ink',
            )}
          >
            {o.label}
            {o.contagem !== undefined && (
              <span className={cx('tabular ml-1.5 text-[12px]', ativo ? 'text-gold-deep' : 'text-muted')}>
                {o.contagem}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

/**
 * Esqueleto de carregamento no lugar do spinner.
 *
 * Um spinner centralizado apaga a página inteira e faz o layout pular quando os dados chegam; o
 * esqueleto mantém a forma e a posição do que está vindo.
 */
export function Skeleton({ className }: { className?: string }) {
  return <div className={cx('animate-pulse rounded-md bg-surface-2', className)} aria-hidden />
}

export function SkeletonCards({ quantos = 4 }: { quantos?: number }) {
  return (
    <>
      {Array.from({ length: quantos }, (_, i) => (
        <div key={i} className="rounded-lg border border-line bg-surface px-4 py-3.5 shadow-card">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="mt-3 h-8 w-32" />
          <Skeleton className="mt-3 h-3 w-20" />
        </div>
      ))}
    </>
  )
}

/** Etiqueta da régua de cobrança. O rótulo e o tom vêm do backend — aqui só se desenha. */
export function EtiquetaCobranca({
  label,
  tone,
  className,
}: {
  label: string | null | undefined
  tone: 'neutral' | 'gold' | 'ok' | 'warn' | 'danger' | null | undefined
  className?: string
}) {
  if (!label) return null
  const cores = {
    ok: 'bg-ok-wash text-ok',
    warn: 'bg-warn-wash text-warn',
    danger: 'bg-danger-wash text-danger',
    gold: 'bg-gold-wash text-gold-deep',
    neutral: 'bg-surface-2 text-ink-2',
  }
  return (
    <span
      className={cx(
        'inline-flex items-center rounded-full px-2 py-0.5 text-[11.5px] font-medium',
        cores[tone ?? 'neutral'],
        className,
      )}
    >
      {label}
    </span>
  )
}

/** Dinheiro com a cor da situação — usado onde o saldo é a informação principal da linha. */
export function SaldoDestacado({ centavos, tone }: { centavos: number; tone: string | null | undefined }) {
  return (
    <Dinheiro
      centavos={centavos}
      className={cx(
        'font-medium',
        tone === 'danger' ? 'text-danger' : tone === 'warn' ? 'text-warn' : 'text-ink',
      )}
    />
  )
}
