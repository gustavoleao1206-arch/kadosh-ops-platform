/**
 * Gráficos desenhados à mão, em SVG.
 *
 * Não é preciosismo: a CSP do backend é `style-src 'self'` sem `unsafe-inline` e não abre para
 * domínio externo, então nenhuma biblioteca de gráficos entra por CDN — teria de ser empacotada,
 * pesar no bundle e trazer a própria estética. Para duas formas (barras e linha) o SVG sai menor,
 * combina com a tipografia da casa e não some quando a CSP aperta.
 *
 * O que a CSP barra é o atributo `style=""` escrito no HTML; o prop `style` do React passa, porque
 * ele aplica via CSSOM. Ainda assim, aqui quase tudo é atributo de SVG (x, y, width, fill), que
 * nunca foi afetado.
 *
 * Regra de cor da casa: OURO É MARCA, não dinheiro. As barras usam ouro porque são o assunto da
 * página, e os valores em texto ficam em `ink` com `tabular-nums`.
 */

import { useId } from 'react'
import { money } from '../lib/format'

export interface Ponto {
  label: string
  /** rótulo por extenso, para o title do hover */
  labelLongo?: string
  valor: number
  /** segunda série, desenhada como barra fina sobreposta (ex.: recebido dentro do faturado) */
  valorSecundario?: number
}

/**
 * Barras verticais com grade discreta. `alturaMax` em px; a largura é fluida (viewBox + preserve).
 *
 * Sem eixo Y numérico de propósito: o número que importa está no cartão acima e no hover. Um eixo
 * cheio de "R$ 1.250,00" em pé rouba a leitura da forma, que é o que o gráfico existe para mostrar.
 */
export function Barras({
  pontos,
  rotuloSerie = 'Faturado',
  rotuloSerieSecundaria = 'Recebido',
  altura = 168,
}: {
  pontos: Ponto[]
  rotuloSerie?: string
  rotuloSerieSecundaria?: string
  altura?: number
}) {
  const id = useId()
  const max = Math.max(1, ...pontos.map((p) => Math.max(p.valor, p.valorSecundario ?? 0)))
  const temSecundaria = pontos.some((p) => p.valorSecundario !== undefined)

  const L = 8
  const R = 8
  const TOPO = 8
  const BASE = 22
  const largura = 640
  const util = largura - L - R
  const alturaUtil = altura - TOPO - BASE
  const passo = util / Math.max(1, pontos.length)
  const larguraBarra = Math.min(38, passo * 0.62)

  return (
    <figure className="m-0">
      <svg
        viewBox={`0 0 ${largura} ${altura}`}
        className="h-auto w-full"
        role="img"
        aria-labelledby={`${id}-t`}
        preserveAspectRatio="none"
      >
        <title id={`${id}-t`}>
          {rotuloSerie} por período{temSecundaria ? ` e ${rotuloSerieSecundaria.toLowerCase()}` : ''}
        </title>

        {/* grade: três linhas, o suficiente para dar escala sem virar papel milimetrado */}
        {[0.25, 0.5, 0.75].map((f) => (
          <line
            key={f}
            x1={L}
            x2={largura - R}
            y1={TOPO + alturaUtil * f}
            y2={TOPO + alturaUtil * f}
            stroke="currentColor"
            className="text-line"
            strokeWidth={1}
          />
        ))}
        <line
          x1={L}
          x2={largura - R}
          y1={TOPO + alturaUtil}
          y2={TOPO + alturaUtil}
          stroke="currentColor"
          className="text-line"
          strokeWidth={1}
        />

        {pontos.map((p, i) => {
          const centro = L + passo * i + passo / 2
          const x = centro - larguraBarra / 2
          const h = (p.valor / max) * alturaUtil
          const y = TOPO + alturaUtil - h
          const hSec = p.valorSecundario !== undefined ? (p.valorSecundario / max) * alturaUtil : 0
          return (
            <g key={`${p.label}-${i}`}>
              <rect x={x} y={y} width={larguraBarra} height={Math.max(h, p.valor > 0 ? 2 : 0)} rx={2} className="fill-gold/35" />
              {p.valorSecundario !== undefined && (
                <rect
                  x={x + larguraBarra * 0.25}
                  y={TOPO + alturaUtil - hSec}
                  width={larguraBarra * 0.5}
                  height={Math.max(hSec, p.valorSecundario > 0 ? 2 : 0)}
                  rx={2}
                  className="fill-gold-deep"
                />
              )}
              {/* área invisível de hover: cobre a coluna inteira, não só a barra desenhada */}
              <rect x={L + passo * i} y={TOPO} width={passo} height={alturaUtil} fill="transparent">
                <title>
                  {`${p.labelLongo ?? p.label}\n${rotuloSerie}: ${money(p.valor)}`}
                  {p.valorSecundario !== undefined ? `\n${rotuloSerieSecundaria}: ${money(p.valorSecundario)}` : ''}
                </title>
              </rect>
              <text
                x={centro}
                y={altura - 6}
                textAnchor="middle"
                className="fill-muted font-label"
                fontSize={11}
                letterSpacing="0.06em"
              >
                {p.label}
              </text>
            </g>
          )
        })}
      </svg>
      {temSecundaria && (
        <figcaption className="mt-2 flex items-center gap-4 text-[12px] text-muted">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-[2px] bg-gold/35" />
            {rotuloSerie}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-[2px] bg-gold-deep" />
            {rotuloSerieSecundaria}
          </span>
        </figcaption>
      )}
    </figure>
  )
}

/**
 * Barra horizontal de proporção — para "de onde veio o dinheiro" (formas de pagamento).
 *
 * Existe em vez de um gráfico de pizza porque a pergunta real é "quanto de cada", e comparar
 * comprimentos é mais fácil que comparar fatias.
 */
export function BarraProporcao({
  partes,
}: {
  partes: { label: string; valor: number; tone?: 'gold' | 'ok' | 'warn' | 'danger' }[]
}) {
  const total = partes.reduce((s, p) => s + p.valor, 0)
  if (total <= 0) return null
  const cor = { gold: 'bg-gold', ok: 'bg-ok', warn: 'bg-warn', danger: 'bg-danger' }
  // tons de ouro decrescentes: uma paleta só, o assunto é o mesmo
  const tonsOuro = ['bg-gold-deep', 'bg-gold', 'bg-gold/70', 'bg-gold/50', 'bg-gold/35', 'bg-gold/25']

  return (
    <div>
      <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-surface-2">
        {partes.map((p, i) => (
          <div
            key={p.label}
            className={p.tone ? cor[p.tone] : tonsOuro[i % tonsOuro.length]}
            style={{ width: `${(p.valor / total) * 100}%` }}
            title={`${p.label}: ${money(p.valor)}`}
          />
        ))}
      </div>
      <ul className="mt-3 grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
        {partes.map((p, i) => (
          <li key={p.label} className="flex items-center justify-between gap-3 text-[13px]">
            <span className="flex min-w-0 items-center gap-2">
              <span
                className={`inline-block h-2.5 w-2.5 shrink-0 rounded-[2px] ${p.tone ? cor[p.tone] : tonsOuro[i % tonsOuro.length]}`}
              />
              <span className="truncate text-ink-2">{p.label}</span>
            </span>
            <span className="tabular shrink-0 text-ink">{money(p.valor)}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
