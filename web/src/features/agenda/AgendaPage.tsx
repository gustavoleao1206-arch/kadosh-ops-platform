import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { CalendarDays, CarFront, ChevronLeft, ChevronRight, Clock, FileText, Plus } from 'lucide-react'
import { api, errorMessage } from '../../api/client'
import type { Agenda, Page, WorkOrder } from '../../api/types'
import { Badge, Button, Card, EmptyState, ErrorState, Spinner, cx } from '../../components/ui'
import { PageHeader } from '../../components/PageHeader'
import { money, plate } from '../../lib/format'
import { addDays, dateOnly, hour, isToday, sameBusinessDay, shortDate, weekdayLong, weekdayShort, weekdayTiny } from '../../lib/datetime'
import { WorkOrderForm } from '../work-orders/WorkOrderForm'
import { WorkOrderDialog } from '../work-orders/WorkOrderDialog'
import { IntakeDialog } from '../work-orders/IntakeDialog'

export function AgendaPage() {
  const [dia, setDia] = useState(() => new Date())
  const [novoOpen, setNovoOpen] = useState(false)
  const [intakeOpen, setIntakeOpen] = useState(false)
  const [abertaId, setAbertaId] = useState<number | null>(null)
  const diaStr = dateOnly(dia)

  // o painel fica aberto o dia inteiro no balcão: quando vira a meia-noite, acompanha
  useEffect(() => {
    const t = window.setInterval(() => {
      setDia((atual) => (dateOnly(atual) === dateOnly(new Date()) ? atual : new Date()))
    }, 60_000)
    return () => window.clearInterval(t)
  }, [])

  const agenda = useQuery({
    queryKey: ['agenda', diaStr],
    queryFn: () => api<Agenda>('/agenda', { query: { dia: diaStr } }),
    placeholderData: (prev) => prev,
    refetchInterval: 60_000, // "quase tempo real": o pátio muda no celular do sócio
  })

  const orcamentos = useQuery({
    queryKey: ['work-orders', 'orcamentos'],
    queryFn: () => api<Page<WorkOrder>>('/work-orders', { query: { status: 'orcamento', page_size: 50 } }),
  })

  const proximos = useQuery({
    queryKey: ['work-orders', 'proximos', diaStr],
    queryFn: () =>
      api<Page<WorkOrder>>('/work-orders', {
        // confirmado também é compromisso da semana — sem os dois, confirmar faz sumir daqui
        query: { status: ['agendado', 'confirmado'], de: dateOnly(addDays(dia, 1)), ate: dateOnly(addDays(dia, 7)), page_size: 50 },
      }),
  })

  const resumo = agenda.data?.resumo
  const itens = agenda.data?.itens ?? []

  // Dois carros marcados para o mesmo horário é coisa para o dono ver antes de marcar o terceiro.
  // Só conta quem ainda não chegou: dois carros que entraram no mesmo minuto já estão no pátio,
  // não há conflito nenhum a resolver.
  const porHorario = useMemo(() => {
    const mapa = new Map<string, number>()
    itens.forEach((w) => {
      if (!w.scheduled_at || w.entrada) return
      const h = hour(w.scheduled_at)
      mapa.set(h, (mapa.get(h) ?? 0) + 1)
    })
    return mapa
  }, [itens])

  return (
    <>
      <PageHeader
        eyebrow="Operação"
        title="Agenda"
        subtitle="Quem chega hoje, o que está no pátio e os orçamentos esperando resposta."
        actions={
          <>
            <Button variant="secondary" onClick={() => setNovoOpen(true)}>
              <Plus className="h-4 w-4" /> Novo agendamento
            </Button>
            <Button onClick={() => setIntakeOpen(true)}>
              <CarFront className="h-4 w-4" /> Receber veículo
            </Button>
          </>
        }
      />

      <div className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Contador label="Agendados hoje" valor={resumo?.agendados} icon={CalendarDays} />
        <Contador label="Confirmados" valor={resumo?.confirmados} icon={Clock} tone="gold" />
        <Contador label="No pátio agora" valor={resumo?.no_patio} icon={Clock} tone="warn" />
        <Contador label="Orçamentos abertos" valor={resumo?.orcamentos_abertos} icon={FileText} />
      </div>

      <div className="grid gap-5 lg:grid-cols-[1.6fr_1fr]">
        <Card
          title={isToday(dia) ? 'Hoje' : weekdayLong(dia)}
          actions={
            <div className="flex items-center gap-1">
              <Button size="sm" variant="ghost" onClick={() => setDia((d) => addDays(d, -1))} aria-label="Dia anterior">
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="tabular min-w-[92px] text-center text-[13px] text-ink-2">
                {new Intl.DateTimeFormat('pt-BR', { timeZone: 'America/Maceio' }).format(dia)}
              </span>
              <Button size="sm" variant="ghost" onClick={() => setDia((d) => addDays(d, 1))} aria-label="Próximo dia">
                <ChevronRight className="h-4 w-4" />
              </Button>
              {!isToday(dia) && (
                <Button size="sm" variant="secondary" onClick={() => setDia(new Date())}>
                  Hoje
                </Button>
              )}
            </div>
          }
        >
          {agenda.isLoading && !agenda.data ? (
            <Spinner />
          ) : agenda.isError ? (
            <ErrorState message={errorMessage(agenda.error)} onRetry={() => void agenda.refetch()} />
          ) : itens.length === 0 ? (
            <EmptyState
              title="Nada marcado para este dia"
              hint="Carro que chegou sem marcar? Use Receber veículo — cliente e carro são cadastrados junto."
              action={
                <Button variant="secondary" onClick={() => setNovoOpen(true)}>
                  <Plus className="h-4 w-4" /> Agendar
                </Button>
              }
            />
          ) : (
            <ul className={cx('divide-y divide-line transition-opacity', agenda.isFetching && 'opacity-60')}>
              {itens.map((wo) => {
                const horario = hour(wo.scheduled_at ?? wo.entrada)
                const desdeOntem = !!wo.entrada && !sameBusinessDay(wo.entrada, dia)
                // um polimento longo termina depois da meia-noite: sem o dia, "até 05:00" engana
                const previsaoNoutroDia = !!wo.previsao_conclusao && !sameBusinessDay(wo.previsao_conclusao, dia)
                return (
                  <li key={wo.id}>
                    <button type="button" onClick={() => setAbertaId(wo.id)} className="flex w-full items-center gap-4 py-3 text-left hover:bg-surface-2/60">
                      <span className="w-[76px] shrink-0">
                        {/* carro que dormiu na loja aparece na lista de hoje: a hora sozinha seria de ontem */}
                        {desdeOntem && <span className="tabular block text-[11px] text-muted">{shortDate(wo.entrada!)}</span>}
                        <span className={cx('tabular block font-medium', desdeOntem ? 'text-[13px] text-ink-2' : 'text-ink')}>{horario}</span>
                        {wo.previsao_conclusao && (
                          <span className="tabular block text-[11.5px] text-muted">
                            até {previsaoNoutroDia && `${weekdayTiny(wo.previsao_conclusao)} `}
                            {hour(wo.previsao_conclusao)}
                          </span>
                        )}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate font-medium text-ink">{wo.cliente.nome}</span>
                        <span className="block truncate text-[13px] text-muted">
                          {wo.veiculo ? (
                            <>
                              <span className="tabular">{plate(wo.veiculo.placa)}</span> · {wo.veiculo.marca ? `${wo.veiculo.marca} ` : ''}
                              {wo.veiculo.modelo}
                            </>
                          ) : (
                            'sem veículo'
                          )}
                          {wo.itens.length > 0 && ` · ${wo.itens.map((i) => i.descricao).join(', ')}`}
                        </span>
                      </span>
                      {!wo.entrada && (porHorario.get(horario) ?? 0) > 1 && <Badge tone="warn">{porHorario.get(horario)} no mesmo horário</Badge>}
                      <span className="tabular hidden shrink-0 text-[13px] text-ink-2 sm:block">{money(wo.valor_total_centavos)}</span>
                      <Badge tone={wo.status_tone}>{wo.status_label}</Badge>
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </Card>

        <div className="grid gap-5">
          <Card title="Próximos 7 dias">
            {proximos.isLoading ? (
              <Spinner />
            ) : !proximos.data || proximos.data.items.length === 0 ? (
              <p className="text-[13.5px] text-muted">Nada agendado para a próxima semana.</p>
            ) : (
              <>
                <ul className="divide-y divide-line">
                  {proximos.data.items.map((wo) => (
                    <li key={wo.id}>
                      <button type="button" onClick={() => setAbertaId(wo.id)} className="flex w-full items-center gap-3 py-2.5 text-left hover:bg-surface-2/60">
                        <span className="w-[86px] shrink-0 text-[13px] text-muted">
                          {weekdayShort(new Date(wo.scheduled_at!))} · {hour(wo.scheduled_at)}
                        </span>
                        <span className="min-w-0 flex-1 truncate text-[13.5px]">{wo.cliente.nome}</span>
                        <Badge tone={wo.status_tone}>{wo.status_label}</Badge>
                      </button>
                    </li>
                  ))}
                </ul>
                {proximos.data.total > proximos.data.items.length && (
                  <p className="mt-2 text-[12.5px] text-muted">Mostrando {proximos.data.items.length} de {proximos.data.total}.</p>
                )}
              </>
            )}
          </Card>

          <Card title="Orçamentos abertos">
            {orcamentos.isLoading ? (
              <Spinner />
            ) : !orcamentos.data || orcamentos.data.items.length === 0 ? (
              <p className="text-[13.5px] text-muted">Nenhum orçamento esperando resposta.</p>
            ) : (
              <>
                <ul className="divide-y divide-line">
                  {orcamentos.data.items.map((wo) => (
                    <li key={wo.id}>
                      <button type="button" onClick={() => setAbertaId(wo.id)} className="flex w-full items-center gap-3 py-2.5 text-left hover:bg-surface-2/60">
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[13.5px] font-medium">{wo.cliente.nome}</span>
                          <span className="block truncate text-[12.5px] text-muted">{wo.itens.map((i) => i.descricao).join(', ') || 'sem serviços'}</span>
                        </span>
                        <span className="tabular shrink-0 text-[13px] text-gold-deep">{money(wo.valor_total_centavos)}</span>
                      </button>
                    </li>
                  ))}
                </ul>
                {orcamentos.data.total > orcamentos.data.items.length && (
                  <p className="mt-2 text-[12.5px] text-muted">Mostrando {orcamentos.data.items.length} de {orcamentos.data.total}.</p>
                )}
              </>
            )}
          </Card>
        </div>
      </div>

      <WorkOrderForm open={novoOpen} onClose={() => setNovoOpen(false)} onSaved={(wo) => setAbertaId(wo.id)} />
      <IntakeDialog open={intakeOpen} onClose={() => setIntakeOpen(false)} onRecebido={(wo) => setAbertaId(wo.id)} />
      <WorkOrderDialog id={abertaId} onClose={() => setAbertaId(null)} />
    </>
  )
}

function Contador({
  label,
  valor,
  icon: Icon,
  tone = 'neutral',
}: {
  label: string
  valor: number | undefined
  icon: typeof CalendarDays
  tone?: 'neutral' | 'gold' | 'warn'
}) {
  return (
    <div className="rounded-lg border border-line bg-surface px-4 py-3 shadow-card">
      <div className="flex items-start justify-between">
        <div>
          <div className="label-dim">{label}</div>
          <div className={cx('tabular mt-1 font-display text-[28px] font-semibold leading-none', tone === 'warn' && 'text-warn', tone === 'gold' && 'text-gold-deep')}>
            {valor ?? '—'}
          </div>
        </div>
        <Icon className={cx('h-4 w-4', tone === 'warn' ? 'text-warn' : 'text-gold')} />
      </div>
    </div>
  )
}
