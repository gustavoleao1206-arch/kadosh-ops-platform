import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { CarFront, Search, Timer } from 'lucide-react'
import { api, errorMessage } from '../../api/client'
import type { Page, WorkOrder } from '../../api/types'
import { Badge, Button, Card, EmptyState, ErrorState, Input, Spinner, Table, Td, Th, cx, rowClick } from '../../components/ui'
import { PageHeader } from '../../components/PageHeader'
import { useDebounced } from '../../lib/hooks'
import { dateTime, money, plate } from '../../lib/format'
import { hour } from '../../lib/datetime'
import { IntakeDialog } from './IntakeDialog'

interface Patio {
  recebido: WorkOrder[]
  em_execucao: WorkOrder[]
  aguardando_retirada: WorkOrder[]
}

const COLUNAS: Array<{ chave: keyof Patio; titulo: string; dica: string }> = [
  { chave: 'recebido', titulo: 'Recebidos', dica: 'chegaram e aguardam início' },
  { chave: 'em_execucao', titulo: 'Em execução', dica: 'serviço acontecendo agora' },
  { chave: 'aguardando_retirada', titulo: 'Prontos', dica: 'avise o cliente para buscar' },
]

const FILTROS = [
  { v: '', l: 'Todas' },
  { v: 'orcamento', l: 'Orçamentos' },
  { v: 'concluido', l: 'Concluídas' },
  { v: 'cancelado', l: 'Canceladas' },
]

const PAGE_SIZE = 50

export function WorkOrdersPage() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const status = params.get('status') ?? ''
  const page = Math.max(1, Number(params.get('page') ?? 1) || 1)
  const [intakeOpen, setIntakeOpen] = useState(false)
  const debounced = useDebounced(q, 250)

  const update = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(patch)) {
      if (v === null || v === '') next.delete(k)
      else next.set(k, v)
    }
    setParams(next, { replace: true })
  }

  const patio = useQuery({
    queryKey: ['patio'],
    queryFn: () => api<Patio>('/patio'),
    refetchInterval: 60_000, // o sócio muda o status pelo celular
  })

  const lista = useQuery({
    queryKey: ['work-orders', { q: debounced, status, page }],
    queryFn: () => api<Page<WorkOrder>>('/work-orders', { query: { q: debounced, status: status || undefined, page, page_size: PAGE_SIZE } }),
    placeholderData: (prev) => prev,
  })

  const totalPages = lista.data ? Math.max(1, Math.ceil(lista.data.total / PAGE_SIZE)) : 1
  const noPatio = patio.data ? COLUNAS.reduce((s, c) => s + patio.data[c.chave].length, 0) : 0

  return (
    <>
      <PageHeader
        eyebrow="Operação"
        title="Ordens de serviço"
        subtitle="Os carros que estão na loja agora e o histórico de tudo que passou por aqui."
        actions={
          <Button onClick={() => setIntakeOpen(true)}>
            <CarFront className="h-4 w-4" /> Receber veículo
          </Button>
        }
      />

      {/* pátio */}
      <div className="mb-7">
        <div className="mb-3 flex items-baseline gap-3">
          <h2 className="font-display text-[22px] font-semibold leading-none">No pátio</h2>
          <span className="tabular text-[13px] text-muted">{noPatio} veículo{noPatio === 1 ? '' : 's'}</span>
        </div>
        {patio.isLoading ? (
          <Spinner />
        ) : patio.isError ? (
          <ErrorState message={errorMessage(patio.error)} onRetry={() => void patio.refetch()} />
        ) : noPatio === 0 ? (
          <Card>
            <EmptyState
              title="Nenhum carro na loja agora"
              hint="Quando um veículo chegar, use Receber veículo — o cliente e o carro são cadastrados junto."
              action={
                <Button variant="secondary" onClick={() => setIntakeOpen(true)}>
                  <CarFront className="h-4 w-4" /> Receber veículo
                </Button>
              }
            />
          </Card>
        ) : (
          <div className="grid gap-4 lg:grid-cols-3">
            {COLUNAS.map(({ chave, titulo, dica }) => {
              const carros = patio.data![chave]
              return (
                <div key={chave} className={cx('rounded-lg border bg-surface shadow-card', chave === 'aguardando_retirada' ? 'border-ok/40' : 'border-line')}>
                  <div className="flex items-baseline justify-between border-b border-line px-4 py-2.5">
                    <span className="font-display text-[17px] font-semibold">{titulo}</span>
                    <span className="tabular text-[13px] text-muted">{carros.length}</span>
                  </div>
                  {carros.length === 0 ? (
                    <p className="px-4 py-5 text-[13px] text-muted">{dica}</p>
                  ) : (
                    <ul className="divide-y divide-line">
                      {carros.map((wo) => {
                        const atrasado = wo.previsao_conclusao && new Date(wo.previsao_conclusao) < new Date() && wo.status !== 'aguardando_retirada'
                        return (
                          <li key={wo.id}>
                            <Link to={`/os/${wo.id}`} className="block px-4 py-3 hover:bg-surface-2/60">
                              <div className="flex items-center justify-between gap-2">
                                <span className="tabular font-medium">{wo.veiculo ? plate(wo.veiculo.placa) : '—'}</span>
                                <span className="tabular text-[12.5px] text-muted">nº {String(wo.numero ?? 0).padStart(3, '0')}</span>
                              </div>
                              <div className="truncate text-[13px] text-ink-2">{wo.cliente.nome}</div>
                              <div className="truncate text-[12.5px] text-muted">
                                {wo.itens.map((i) => i.descricao).join(', ') || 'sem serviços lançados'}
                              </div>
                              <div className="mt-1.5 flex flex-wrap items-center gap-2">
                                {atrasado ? (
                                  <Badge tone="danger">
                                    <Timer className="mr-1 h-3 w-3" /> atrasado
                                  </Badge>
                                ) : wo.previsao_conclusao && wo.status !== 'aguardando_retirada' ? (
                                  // carro pronto não tem prazo a cumprir: o horário velho só confundiria
                                  <span className="tabular text-[12px] text-muted">até {hour(wo.previsao_conclusao)}</span>
                                ) : null}
                                <span className="tabular ml-auto text-[12.5px] text-ink-2">{money(wo.valor_total_centavos)}</span>
                              </div>
                            </Link>
                          </li>
                        )
                      })}
                    </ul>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* histórico */}
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <h2 className="font-display text-[22px] font-semibold leading-none">Histórico</h2>
        <div className="relative w-full max-w-xs">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <Input value={q} onChange={(e) => update({ q: e.target.value, page: null })} placeholder="Placa, cliente ou modelo…" className="pl-9" />
        </div>
        <div className="flex flex-wrap rounded-md border border-line bg-surface p-0.5 text-[13px]">
          {FILTROS.map((o) => (
            <button
              key={o.v}
              type="button"
              onClick={() => update({ status: o.v || null, page: null })}
              className={cx('rounded px-3 py-1.5 transition', status === o.v ? 'bg-obsidian text-ivory' : 'text-ink-2 hover:bg-surface-2')}
            >
              {o.l}
            </button>
          ))}
        </div>
        {lista.data && <span className="tabular text-[13px] text-muted">{lista.data.total} OS</span>}
      </div>

      {lista.isLoading ? (
        <Spinner />
      ) : lista.isError ? (
        <ErrorState message={errorMessage(lista.error)} onRetry={() => void lista.refetch()} />
      ) : !lista.data || lista.data.items.length === 0 ? (
        <div className="rounded-lg border border-line bg-surface">
          <EmptyState title="Nada aqui" hint={debounced ? 'Tente outra placa ou nome.' : 'As ordens de serviço aparecem aqui conforme forem criadas.'} />
        </div>
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>OS</Th>
              <Th>Cliente</Th>
              <Th>Veículo</Th>
              <Th>Status</Th>
              <Th>Quando</Th>
              <Th className="text-right">Valor</Th>
            </tr>
          </thead>
          <tbody>
            {lista.data.items.map((wo) => (
              <tr key={wo.id} className="cursor-pointer hover:bg-surface-2/60" onClick={rowClick(() => navigate(`/os/${wo.id}`))}>
                <Td className="tabular">
                  <Link to={`/os/${wo.id}`} className="font-medium hover:text-gold-deep">
                    {wo.numero ? `nº ${String(wo.numero).padStart(3, '0')}` : `#${wo.id}`}
                  </Link>
                </Td>
                <Td className="truncate">{wo.cliente.nome}</Td>
                <Td>
                  {wo.veiculo ? (
                    <>
                      <span className="tabular">{plate(wo.veiculo.placa)}</span> <span className="text-muted">{wo.veiculo.modelo}</span>
                    </>
                  ) : (
                    <span className="text-muted">—</span>
                  )}
                </Td>
                <Td>
                  <Badge tone={wo.status_tone}>{wo.status_label}</Badge>
                </Td>
                <Td className="tabular whitespace-nowrap text-muted">{dateTime(wo.entrada ?? wo.scheduled_at ?? wo.created_at)}</Td>
                <Td className="tabular text-right">{money(wo.valor_total_centavos)}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}

      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-end gap-2 text-[13px]">
          <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => update({ page: String(page - 1) })}>
            Anterior
          </Button>
          <span className="tabular text-muted">
            {page} / {totalPages}
          </span>
          <Button variant="secondary" size="sm" disabled={page >= totalPages} onClick={() => update({ page: String(page + 1) })}>
            Próxima
          </Button>
        </div>
      )}

      <IntakeDialog open={intakeOpen} onClose={() => setIntakeOpen(false)} onRecebido={(wo) => navigate(`/os/${wo.id}`)} />
    </>
  )
}
