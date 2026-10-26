import { useState } from 'react'
import { Link } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { Banknote, ChevronLeft, ChevronRight, Clock } from 'lucide-react'
import { api, errorMessage } from '../../api/client'
import type { Caixa } from '../../api/types'
import { Badge, Button, Card, EmptyState, ErrorState, Spinner, cx } from '../../components/ui'
import { money } from '../../lib/format'
import { addDays, dateOnly, hour, isToday, weekdayLong } from '../../lib/datetime'

/** O fim do dia no balcão: quanto entrou, em quê, e quem ainda deve. Lançar é dentro da OS. */
export function CaixaPage() {
  const [dia, setDia] = useState(() => new Date())
  const diaStr = dateOnly(dia)

  const caixa = useQuery({
    queryKey: ['caixa', diaStr],
    queryFn: () => api<Caixa>('/caixa', { query: { dia: diaStr } }),
    placeholderData: (prev) => prev,
  })

  const dados = caixa.data
  // um estado para a página inteira: sem isto, o erro só aparecia no primeiro cartão e os outros
  // dois ficavam girando para sempre, sem mensagem e sem botão de tentar de novo
  const falhou = caixa.isError && !dados
  const erro = <ErrorState message={errorMessage(caixa.error)} onRetry={() => void caixa.refetch()} />

  return (
    <>
      <div className="mb-5 grid gap-4 lg:grid-cols-[1fr_1.2fr]">
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
          {falhou ? (
            erro
          ) : !dados ? (
            <Spinner />
          ) : (
            <>
              <div className="label-dim">Recebido no dia</div>
              <div className="tabular mt-1 font-display text-[38px] font-semibold leading-none text-gold-deep">
                {money(dados?.recebido_centavos ?? 0)}
              </div>
              {dados && dados.por_forma.length > 0 ? (
                <ul className="mt-4 grid gap-1.5 border-t border-line pt-3 text-[13.5px]">
                  {dados.por_forma.map((f) => (
                    <li key={f.forma} className="flex justify-between">
                      <span className="text-ink-2">{f.forma_label}</span>
                      <span className="tabular">{money(f.total_centavos)}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-4 border-t border-line pt-3 text-[13px] text-muted">Nada recebido neste dia.</p>
              )}
            </>
          )}
        </Card>

        <Card title="A receber agora" actions={dados && <span className="tabular text-[13px] text-muted">{money(dados.a_receber_centavos)}</span>}>
          {falhou ? (
            erro
          ) : !dados ? (
            <Spinner />
          ) : dados.a_receber.length === 0 ? (
            <p className="text-[13.5px] text-muted">Ninguém devendo — pátio e concluídas estão quitados.</p>
          ) : (
            <ul className="divide-y divide-line">
              {dados.a_receber.map((d) => (
                <li key={d.work_order_id}>
                  <Link to={`/os/${d.work_order_id}`} className="flex items-center gap-3 py-2.5 hover:bg-surface-2/60">
                    <span className="tabular w-[62px] shrink-0 text-[13px] text-muted">
                      {d.numero ? `nº ${String(d.numero).padStart(3, '0')}` : `#${d.work_order_id}`}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-[13.5px]">{d.cliente_nome}</span>
                    <Badge tone={d.status_tone}>{d.status_label}</Badge>
                    <span className="tabular w-[92px] shrink-0 text-right text-[13.5px] font-medium text-warn">
                      {money(d.saldo_centavos)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card title="Lançamentos do dia">
        {falhou ? (
          erro
        ) : !dados ? (
          <Spinner />
        ) : dados.lancamentos.length === 0 ? (
          <EmptyState
            title="Nenhum lançamento neste dia"
            hint="O pagamento é lançado dentro da OS, no bloco de valores."
          />
        ) : (
          <ul className="divide-y divide-line">
            {dados.lancamentos.map((l) => (
              <li key={l.id} className="flex flex-wrap items-center gap-3 py-2.5">
                <span className="tabular w-[46px] shrink-0 text-[13px] text-muted">{hour(l.pago_em)}</span>
                <Link
                  to={`/os/${l.work_order_id}`}
                  className="tabular w-[62px] shrink-0 text-[13px] text-ink-2 hover:text-gold-deep"
                >
                  {l.numero ? `nº ${String(l.numero).padStart(3, '0')}` : `#${l.work_order_id}`}
                </Link>
                <span className={cx('min-w-0 flex-1 truncate text-[13.5px]', l.estornado_em && 'text-muted line-through')}>
                  {l.cliente_nome}
                </span>
                <span className={cx('shrink-0 text-[13px] text-muted', l.estornado_em && 'line-through')}>
                  {l.forma_label}
                </span>
                {l.estornado_em && (
                  <>
                    <Badge tone="danger">estornado</Badge>
                    {l.estorno_motivo && (
                      <span className="max-w-[220px] truncate text-[12px] text-muted" title={l.estorno_motivo}>
                        {l.estorno_motivo}
                      </span>
                    )}
                  </>
                )}
                <span
                  className={cx(
                    'tabular w-[92px] shrink-0 text-right text-[13.5px]',
                    l.estornado_em ? 'text-muted line-through' : 'font-medium',
                  )}
                >
                  {money(l.valor_centavos)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <p className="mt-4 flex items-center gap-1.5 text-[12.5px] text-muted">
        <Clock className="h-3.5 w-3.5" />
        O dia fecha no horário de Maceió e soma pela data em que o dinheiro entrou — um Pix de ontem lançado hoje
        aparece no caixa de ontem.
      </p>
      <p className="mt-1 flex items-center gap-1.5 text-[12.5px] text-muted">
        <Banknote className="h-3.5 w-3.5" />
        Faturamento por período, por serviço e comparativos chegam nos relatórios.
      </p>
    </>
  )
}
