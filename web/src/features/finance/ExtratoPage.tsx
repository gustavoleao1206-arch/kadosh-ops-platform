import { Link, useSearchParams } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { api, errorMessage } from '../../api/client'
import type { Extrato, FormaPagamento } from '../../api/types'
import { Button, Card, EmptyState, ErrorState, Input, Select, Table, Td, Th, cx, rowClick } from '../../components/ui'
import { BarraProporcao } from '../../components/charts'
import { Dinheiro, Skeleton } from '../../components/stats'
import { dateTime, money } from '../../lib/format'
import { addDays, dateOnly } from '../../lib/datetime'
import { useNavigate } from 'react-router'

const PAGE_SIZE = 50

/**
 * Presets de período. São os quatro recortes que o dono realmente pede — "quanto entrou hoje",
 * "e na semana", "e no mês", "e entre estas datas". Um seletor com doze opções obriga a escolher
 * antes de saber o que se procura.
 */
function presets() {
  const hoje = new Date()
  const d = (data: Date) => dateOnly(data)
  const primeiroDoMes = new Date(hoje.getFullYear(), hoje.getMonth(), 1)
  return [
    { chave: 'hoje', label: 'Hoje', de: d(hoje), ate: d(hoje) },
    { chave: '7dias', label: '7 dias', de: d(addDays(hoje, -6)), ate: d(hoje) },
    { chave: 'mes', label: 'Este mês', de: d(primeiroDoMes), ate: d(hoje) },
  ]
}

/**
 * O caixa esticado no tempo.
 *
 * Responde com o MESMO critério do caixa do dia — soma por quando o dinheiro entrou, e o estornado
 * aparece riscado mas fora do total. Se as duas telas divergissem, o dono somaria a semana aqui e
 * não bateria com os sete dias de lá; há teste no backend exigindo que fechem.
 *
 * O estado mora na URL (como já faz o relatório): assim o dono manda o link do período para si
 * mesmo, volta pelo histórico do navegador e recarrega sem perder o recorte.
 */
export function ExtratoPage() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const p = presets()
  const de = params.get('de') ?? p[0].de
  const ate = params.get('ate') ?? p[0].ate
  const forma = params.get('forma') ?? ''
  const page = Math.max(1, Number(params.get('page') ?? 1) || 1)

  const update = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(patch)) {
      if (v === null || v === '') next.delete(k)
      else next.set(k, v)
    }
    // trocar filtro volta para a primeira página: manter "página 4" num recorte novo mostra vazio
    if (!('page' in patch)) next.delete('page')
    setParams(next, { replace: true })
  }

  const formas = useQuery({
    queryKey: ['payment-methods'],
    queryFn: () => api<FormaPagamento[]>('/payment-methods'),
    staleTime: Infinity,
  })

  const extrato = useQuery({
    queryKey: ['extrato', { de, ate, forma, page }],
    queryFn: () =>
      api<Extrato>('/extrato', {
        query: { de, ate, forma: forma || undefined, page, page_size: PAGE_SIZE },
      }),
    placeholderData: (prev) => prev,
  })

  const d = extrato.data
  const totalPages = d ? Math.max(1, Math.ceil(d.total / PAGE_SIZE)) : 1
  const presetAtivo = p.find((x) => x.de === de && x.ate === ate)?.chave ?? 'personalizado'

  return (
    <>
      <div className="mb-5 flex flex-wrap items-end gap-3">
        <div className="inline-flex gap-1 rounded-lg border border-line bg-surface-2 p-1">
          {p.map((x) => (
            <button
              key={x.chave}
              type="button"
              onClick={() => update({ de: x.de, ate: x.ate })}
              className={cx(
                'rounded-md px-3 py-1.5 text-[13px] transition',
                presetAtivo === x.chave ? 'bg-surface text-ink shadow-card' : 'text-muted hover:text-ink',
              )}
            >
              {x.label}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-[13px] text-muted">
          De
          <Input
            type="date"
            value={de}
            max={ate}
            onChange={(e) => update({ de: e.target.value })}
            className="w-[150px]"
          />
        </label>
        <label className="flex items-center gap-2 text-[13px] text-muted">
          até
          <Input
            type="date"
            value={ate}
            min={de}
            onChange={(e) => update({ ate: e.target.value })}
            className="w-[150px]"
          />
        </label>
        <label className="flex items-center gap-2 text-[13px] text-muted">
          Forma
          <Select value={forma} onChange={(e) => update({ forma: e.target.value })} className="w-[170px]">
            <option value="">Todas</option>
            {(formas.data ?? []).map((f) => (
              <option key={f.valor} value={f.valor}>
                {f.label}
              </option>
            ))}
          </Select>
        </label>
      </div>

      {extrato.isError && !d ? (
        <ErrorState message={errorMessage(extrato.error)} onRetry={() => void extrato.refetch()} />
      ) : (
        <>
          <div className="mb-5 grid gap-4 lg:grid-cols-[1fr_1.3fr]">
            <Card title={d ? d.periodo.label : 'Período'}>
              {extrato.isPending ? (
                <Skeleton className="h-12 w-40" />
              ) : (
                <>
                  <div className="tabular font-display text-[40px] font-semibold leading-none text-ink">
                    {money(d!.total_centavos)}
                  </div>
                  <div className="mt-2 text-[13px] text-muted">
                    {d!.total === 0
                      ? 'Nenhum lançamento no período'
                      : `${d!.total} ${d!.total === 1 ? 'lançamento' : 'lançamentos'}`}
                  </div>
                  {d!.estornos_centavos > 0 && (
                    <div className="mt-3 flex items-center justify-between gap-3 rounded-md border border-line bg-surface-2 px-3 py-2 text-[13px]">
                      <span className="text-ink-2">Estornado no período</span>
                      <Dinheiro centavos={d!.estornos_centavos} className="text-muted line-through" />
                    </div>
                  )}
                </>
              )}
            </Card>

            <Card title="De onde veio">
              {extrato.isPending ? (
                <Skeleton className="h-24 w-full" />
              ) : d!.por_forma.length === 0 ? (
                <p className="text-[13.5px] text-muted">Nada entrou neste período.</p>
              ) : (
                <BarraProporcao
                  partes={d!.por_forma.map((f) => ({ label: f.forma_label, valor: f.total_centavos }))}
                />
              )}
            </Card>
          </div>

          <Card title="Lançamentos">
            {extrato.isPending ? (
              <div className="grid gap-2">
                {Array.from({ length: 5 }, (_, i) => (
                  <Skeleton key={i} className="h-9 w-full" />
                ))}
              </div>
            ) : d!.lancamentos.length === 0 ? (
              <EmptyState
                title="Nenhum lançamento neste período."
                hint="Pagamento se lança dentro da OS; aqui só se confere."
              />
            ) : (
              <>
                <Table>
                  <thead>
                    <tr>
                      <Th>Quando</Th>
                      <Th>OS</Th>
                      <Th>Cliente</Th>
                      <Th>Forma</Th>
                      <Th className="text-right">Valor</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {d!.lancamentos.map((l) => {
                      const estornado = l.estornado_em !== null
                      return (
                        <tr
                          key={l.id}
                          {...rowClick(() => navigate(`/os/${l.work_order_id}`))}
                          className={cx(estornado && 'text-muted')}
                          title={estornado ? `Estornado — ${l.estorno_motivo ?? 'sem motivo'}` : undefined}
                        >
                          <Td>
                            <span className="tabular">{dateTime(l.pago_em)}</span>
                          </Td>
                          <Td>{l.numero ? `nº ${String(l.numero).padStart(3, '0')}` : '—'}</Td>
                          <Td className="max-w-[220px] truncate">{l.cliente_nome}</Td>
                          <Td>{l.forma_label}</Td>
                          <Td className="text-right">
                            {/* riscado e fora do total: a linha continua visível porque sumir com
                                ela esconderia o rastro — o produto aqui é o histórico */}
                            <Dinheiro centavos={l.valor_centavos} className={cx(estornado && 'line-through')} />
                          </Td>
                        </tr>
                      )
                    })}
                  </tbody>
                </Table>

                {totalPages > 1 && (
                  <div className="mt-4 flex items-center justify-between gap-3 text-[13px] text-muted">
                    <span className="tabular">
                      Página {page} de {totalPages}
                    </span>
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={page <= 1}
                        onClick={() => update({ page: String(page - 1) })}
                      >
                        Anterior
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={page >= totalPages}
                        onClick={() => update({ page: String(page + 1) })}
                      >
                        Próxima
                      </Button>
                    </div>
                  </div>
                )}
                <p className="mt-4 text-[12.5px] text-muted">
                  O total soma pela data em que o dinheiro entrou, não pela data em que foi digitado — e não conta
                  os estornados, que continuam na lista riscados.{' '}
                  <Link to="/financeiro" className="underline decoration-line underline-offset-2 hover:text-gold-deep">
                    O caixa de um dia
                  </Link>{' '}
                  usa exatamente o mesmo critério.
                </p>
              </>
            )}
          </Card>
        </>
      )}
    </>
  )
}
