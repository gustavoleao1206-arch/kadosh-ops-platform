import { Link, useSearchParams } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { AlertCircle, PhoneCall } from 'lucide-react'
import { api, errorMessage } from '../../api/client'
import type { ClientesSumidos, Relatorio, SerieMensal } from '../../api/types'
import { Card, EmptyState, ErrorState, Input, PhoneLink, Spinner, Table, Td, Th, cx } from '../../components/ui'
import { PageHeader } from '../../components/PageHeader'
import { date, money } from '../../lib/format'
import { Barras, BarraProporcao } from '../../components/charts'
import { Dinheiro } from '../../components/stats'

const PERIODOS = [
  { v: 'mes', l: 'Este mês' },
  { v: 'mes_passado', l: 'Mês passado' },
  { v: 'mes_especifico', l: 'Escolher mês' },
  { v: 'personalizado', l: 'Datas' },
]

/** Faturado x Recebido, serviços que dão dinheiro, movimento da semana e quem sumiu. */
export function ReportsPage() {
  const [params, setParams] = useSearchParams()
  const periodo = params.get('periodo') ?? 'mes'
  const de = params.get('de') ?? ''
  const ate = params.get('ate') ?? ''
  const mes = params.get('mes') ?? ''
  const personalizado = periodo === 'personalizado'
  const porMes = periodo === 'mes_especifico'
  const faltaData = (personalizado && (!de || !ate)) || (porMes && !mes)

  const update = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(patch)) {
      if (v === null || v === '') next.delete(k)
      else next.set(k, v)
    }
    setParams(next, { replace: true })
  }

  const rel = useQuery({
    queryKey: ['relatorios', { periodo, de, ate, mes }],
    queryFn: () =>
      api<Relatorio>('/relatorios', {
        query: { periodo, ...(personalizado ? { de, ate } : {}), ...(porMes ? { mes } : {}) },
      }),
    enabled: !faltaData,
    placeholderData: (prev) => prev,
  })

  // A série de 12 meses não depende do período escolhido: é o pano de fundo contra o qual o mês
  // selecionado ganha sentido. "R$ 8.400" sozinho não diz nada; ao lado dos onze anteriores, diz.
  const serie = useQuery({
    queryKey: ['relatorios', 'mensal', 12],
    queryFn: () => api<SerieMensal>('/relatorios/mensal?meses=12'),
  })

  const sumidos = useQuery({
    queryKey: ['relatorios', 'clientes-sumidos'],
    queryFn: () => api<ClientesSumidos>('/relatorios/clientes-sumidos'),
  })

  const d = rel.data
  const t = d?.totais

  return (
    <>
      <PageHeader
        eyebrow="Financeiro"
        title="Relatórios"
        subtitle="O que a loja entregou, o que entrou e o que os números dizem para decidir."
      />

      {/* período */}
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap rounded-md border border-line bg-surface p-0.5 text-[13px]">
          {PERIODOS.map((o) => (
            <button
              key={o.v}
              type="button"
              onClick={() => update({ periodo: o.v === 'mes' ? null : o.v })}
              className={cx(
                'rounded px-3 py-1.5 transition',
                periodo === o.v ? 'bg-obsidian text-ivory' : 'text-ink-2 hover:bg-surface-2',
              )}
            >
              {o.l}
            </button>
          ))}
        </div>
        {personalizado && (
          <div className="flex items-center gap-2 text-[13px]">
            <Input type="date" value={de} onChange={(e) => update({ de: e.target.value })} className="tabular w-[150px]" aria-label="Data inicial" />
            <span className="text-muted">até</span>
            <Input type="date" value={ate} onChange={(e) => update({ ate: e.target.value })} className="tabular w-[150px]" aria-label="Data final" />
          </div>
        )}
        {porMes && (
          <Input
            type="month"
            value={mes}
            onChange={(e) => update({ mes: e.target.value })}
            className="tabular w-[170px]"
            aria-label="Mês do relatório"
          />
        )}
        {d && !personalizado && !porMes && <span className="text-[13px] text-muted">{d.periodo.label}</span>}
      </div>

      {faltaData ? (
        <Card>
          <EmptyState
            title={porMes ? 'Escolha o mês' : 'Escolha as duas datas'}
            hint="O relatório aparece assim que o período estiver completo."
          />
        </Card>
      ) : rel.isLoading && !d ? (
        <Spinner />
      ) : rel.isError ? (
        <ErrorState message={errorMessage(rel.error)} onRetry={() => void rel.refetch()} />
      ) : !d || !t ? null : semNadaNoPeriodo(t) ? (
        <Card>
          <EmptyState
            title={
              d.tem_historico
                ? `Nada aconteceu em ${d.periodo.label.toLowerCase()}`
                : 'Os relatórios começam na primeira OS concluída'
            }
            hint={
              d.tem_historico
                ? 'Nenhuma entrega, nenhum pagamento e nenhum cancelamento no período.'
                : 'Assim que o primeiro carro for entregue, os números aparecem aqui.'
            }
            action={
              d.tem_historico ? (
                <button type="button" onClick={() => update({ periodo: 'mes_passado' })} className="text-[13.5px] text-gold-deep hover:underline">
                  Ver o mês passado
                </button>
              ) : (
                <Link to="/os" className="text-[13.5px] text-gold-deep hover:underline">
                  Ir para as ordens de serviço
                </Link>
              )
            }
          />
        </Card>
      ) : (
        <div className={cx('grid gap-5', rel.isFetching && 'opacity-60')}>
          {/* 1. os números do período */}
          <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
            <Card title="Faturado">
              <div className="tabular font-display text-[38px] font-semibold leading-none">
                {money(t.faturado_centavos)}
              </div>
              <p className="mt-2 text-[13px] text-muted">O que a loja entregou no período (OS concluídas).</p>
              {/* O vazio mora AQUI, não na página: um mês sem entrega ainda pode ter dinheiro
                  entrando (dívida do mês anterior) e cancelamento acontecendo. Esconder a tela
                  inteira apagava justamente a divergência que este relatório existe para mostrar. */}
              {t.os_concluidas === 0 ? (
                <div className="mt-4 border-t border-line pt-3 text-[13.5px] text-muted">
                  Nada concluído em {d.periodo.label.toLowerCase()}.{' '}
                  <button type="button" onClick={() => update({ periodo: 'mes_passado' })} className="text-gold-deep hover:underline">
                    Ver o mês passado
                  </button>
                </div>
              ) : (
                <div className="mt-4 grid gap-1.5 border-t border-line pt-3 text-[13.5px]">
                  <div className="flex justify-between">
                    <span className="text-ink-2">Desses, já recebido</span>
                    <span className="tabular">{money(t.faturado_recebido_centavos)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-ink-2">Ainda a receber</span>
                    <span className={cx('tabular', t.faturado_a_receber_centavos > 0 && 'font-medium text-warn')}>
                      {money(t.faturado_a_receber_centavos)}
                    </span>
                  </div>
                </div>
              )}
            </Card>

            <Card title="Recebido">
              <div className="tabular font-display text-[38px] font-semibold leading-none text-ink">
                {money(t.recebido_centavos)}
              </div>
              <p className="mt-2 text-[13px] text-muted">
                O dinheiro que entrou no caixa no período, venha da OS que vier — inclusive de serviço
                entregue em outro mês.
              </p>
              {d.por_forma.length > 0 && (
                <div className="mt-4 border-t border-line pt-3">
                  <div className="label-dim mb-2.5">De onde veio</div>
                  <BarraProporcao
                    partes={d.por_forma.map((f) => ({ label: f.forma_label, valor: f.total_centavos }))}
                  />
                </div>
              )}
              {/* Sem esta linha sobra uma diferença sem nome entre o bruto que o dono confere na
                  mão e o recebido que o sistema mostra. */}
              {t.estornos_centavos > 0 && (
                <div className="mt-3 flex items-center justify-between gap-3 border-t border-line pt-3 text-[13px]">
                  <span className="text-ink-2">Estornado no período</span>
                  <Dinheiro centavos={t.estornos_centavos} className="text-muted line-through" />
                </div>
              )}
            </Card>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <Numero label="OS concluídas" valor={String(t.os_concluidas)} />
            <Numero label="Ticket médio" valor={money(t.ticket_medio_centavos)} />
            <Numero label="Descontos" valor={money(t.desconto_centavos)} />
            <Numero label="Cancelamentos" valor={String(t.cancelamentos)} alerta={t.cancelamentos > 0} />
            <Numero label="Não compareceram" valor={String(t.nao_comparecimentos)} alerta={t.nao_comparecimentos > 0} />
          </div>

          {/* 2. serviços */}
          <Card title="Serviços do período">
            {d.por_servico.length === 0 ? (
              <p className="text-[13.5px] text-muted">Nenhum serviço lançado nas OS concluídas.</p>
            ) : (
              <>
                <Table>
                  <thead>
                    <tr>
                      <Th>Serviço</Th>
                      <Th className="text-right">Vezes</Th>
                      <Th className="text-right">Receita</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.por_servico.map((s) => (
                      <tr key={s.service_id}>
                        <Td>{s.nome}</Td>
                        <Td className="tabular text-right text-ink-2">{s.quantidade}</Td>
                        <Td className="tabular text-right font-medium">{money(s.total_centavos)}</Td>
                      </tr>
                    ))}
                    {t.desconto_centavos > 0 && (
                      <tr>
                        <Td className="text-muted">Descontos concedidos</Td>
                        <Td />
                        <Td className="tabular text-right text-muted">−{money(t.desconto_centavos)}</Td>
                      </tr>
                    )}
                  </tbody>
                </Table>
                <p className="mt-3 text-[12.5px] text-muted">
                  A receita por serviço é o valor cheio de cada item. O desconto fica na OS, não é dividido
                  entre os serviços — por isso a soma acima menos os descontos é que fecha com o Faturado.
                </p>
              </>
            )}
          </Card>

          {/* 3. movimento da semana */}
          <Card title="Faturado e recebido nos últimos 12 meses">
            {serie.isPending ? (
              <div className="h-[168px] animate-pulse rounded-md bg-surface-2" aria-hidden />
            ) : serie.isError ? (
              <ErrorState message="Não deu para carregar a evolução." onRetry={() => void serie.refetch()} />
            ) : (
              <Barras
                pontos={(serie.data?.meses ?? []).map((m) => ({
                  label: m.label_curto,
                  labelLongo: m.label,
                  valor: m.faturado_centavos,
                  valorSecundario: m.recebido_centavos,
                }))}
              />
            )}
            <p className="mt-3 text-[12.5px] text-muted">
              O período escolhido acima muda os números; esta série é sempre dos 12 meses até hoje — é ela que dá
              escala ao mês que você está lendo.
            </p>
          </Card>

          <Card title="Movimento por dia da semana">
            <SemanaBarras dias={d.por_dia_semana} />
          </Card>
        </div>
      )}

      {/* 4. quem sumiu */}
      <Card className="mt-5" title="Clientes que não voltam há mais de 90 dias">
        {sumidos.isLoading ? (
          <Spinner />
        ) : sumidos.isError ? (
          <ErrorState message={errorMessage(sumidos.error)} onRetry={() => void sumidos.refetch()} />
        ) : !sumidos.data || sumidos.data.itens.length === 0 ? (
          <p className="text-[13.5px] text-muted">
            Ninguém sumiu — todo cliente com histórico voltou, tem serviço marcado ou está com o carro aqui.
          </p>
        ) : (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>Cliente</Th>
                  <Th>Telefone</Th>
                  <Th className="text-right">Atendimentos</Th>
                  <Th className="text-right">Já gastou</Th>
                  <Th className="text-right">Sem voltar</Th>
                </tr>
              </thead>
              <tbody>
                {sumidos.data.itens.map((c) => (
                  <tr key={c.client_id}>
                    <Td>
                      <Link to={`/clientes/${c.client_id}`} className="font-medium hover:text-gold-deep">
                        {c.nome}
                      </Link>
                    </Td>
                    <Td>
                      <PhoneLink digits={c.telefone} />
                    </Td>
                    <Td className="tabular text-right text-ink-2">{c.atendimentos}</Td>
                    <Td className="tabular text-right">{money(c.total_gasto_centavos)}</Td>
                    <Td className="tabular whitespace-nowrap text-right text-muted">
                      {c.dias_sem_voltar} dias
                      <span className="ml-1 text-[12px]">· {date(c.ultimo_atendimento)}</span>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
            <p className="mt-3 flex items-center gap-1.5 text-[12.5px] text-muted">
              <PhoneCall className="h-3.5 w-3.5" />
              Toque no telefone para chamar no WhatsApp.
              {sumidos.data.total > sumidos.data.itens.length &&
                ` Mostrando os ${sumidos.data.itens.length} que mais gastaram, de ${sumidos.data.total}.`}
            </p>
          </>
        )}
      </Card>

      <p className="mt-4 flex items-center gap-1.5 text-[12.5px] text-muted">
        <AlertCircle className="h-3.5 w-3.5" />
        Estornos e reaberturas de OS alteram meses já fechados.
      </p>
    </>
  )
}

/** Vazio de verdade é período sem NADA: sem entrega, sem dinheiro e sem cancelamento. */
function semNadaNoPeriodo(t: Relatorio['totais']): boolean {
  return (
    t.os_concluidas === 0 && t.recebido_centavos === 0 && t.cancelamentos === 0 && t.nao_comparecimentos === 0
  )
}

function Numero({ label, valor, alerta }: { label: string; valor: string; alerta?: boolean }) {
  return (
    <div className="rounded-lg border border-line bg-surface px-4 py-3 shadow-card">
      <div className="label-dim">{label}</div>
      <div className={cx('tabular mt-1 font-display text-[24px] font-semibold leading-none', alerta && 'text-warn')}>
        {valor}
      </div>
    </div>
  )
}

/** Sete linhas com uma barra proporcional. A forma diz o que o número sozinho não diz: onde a
 *  semana afunda. A largura vai por `style` — React aplica pelo CSSOM, que a CSP não bloqueia
 *  (só o atributo `style=""` escrito no HTML é barrado). */
function SemanaBarras({ dias }: { dias: { dia: number; dia_label: string; os_concluidas: number; faturado_centavos: number }[] }) {
  const teto = Math.max(...dias.map((d) => d.faturado_centavos), 1)
  const vazio = dias.every((d) => d.os_concluidas === 0)

  if (vazio) return <p className="text-[13.5px] text-muted">Nenhuma OS concluída no período.</p>

  return (
    <ul className="grid gap-2.5">
      {dias.map((d) => (
        <li key={d.dia} className="flex items-center gap-3 text-[13.5px]">
          <span className="w-[68px] shrink-0 text-ink-2">{d.dia_label}</span>
          <span className="tabular w-[34px] shrink-0 text-right text-muted">{d.os_concluidas}</span>
          <span className="h-2.5 min-w-0 flex-1 overflow-hidden rounded-sm bg-surface-2">
            <span
              className="block h-full rounded-sm bg-gold/70"
              style={{ width: `${Math.round((d.faturado_centavos / teto) * 100)}%` }}
            />
          </span>
          <span className="tabular w-[104px] shrink-0 text-right">{money(d.faturado_centavos)}</span>
        </li>
      ))}
    </ul>
  )
}
