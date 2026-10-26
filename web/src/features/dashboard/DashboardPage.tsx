import { Link } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ArrowRight, CalendarDays, CarFront, FileText, Wallet } from 'lucide-react'
import { api } from '../../api/client'
import type { Dashboard, SerieMensal } from '../../api/types'
import { useAuth } from '../../app/auth'
import { Card, ErrorState, buttonClasses } from '../../components/ui'
import { PageHeader } from '../../components/PageHeader'
import { Barras } from '../../components/charts'
import { Dinheiro, SkeletonCards, StatCard } from '../../components/stats'
import { money, variacaoPct } from '../../lib/format'

/**
 * A tela inicial: o dia, o mês e quem deve — e daqui se vai para onde se resolve.
 *
 * Duas chamadas, não cinco: `/dashboard` já traz tudo agregado pelos MESMOS serviços do caixa, do
 * relatório e da agenda, e `/relatorios/mensal` traz a série do gráfico. A versão anterior desta
 * página compunha os números a partir de /agenda e /caixa com um comentário dizendo que um endpoint
 * próprio seria "o próximo desencontro entre telas". A fase 8 reverteu essa decisão de propósito,
 * e pelo motivo oposto: o endpoint NÃO faz conta nenhuma, ele reusa os services existentes, e há um
 * teste (test_caixa_extrato_relatorio_e_dashboard_fecham) exigindo que as quatro leituras deem o
 * mesmo número. O desencontro que se temia é justamente o que o teste agora impede.
 */
export function DashboardPage() {
  const { user } = useAuth()

  const resumo = useQuery({ queryKey: ['dashboard'], queryFn: () => api<Dashboard>('/dashboard') })
  const serie = useQuery({
    queryKey: ['relatorios', 'mensal', 12],
    queryFn: () => api<SerieMensal>('/relatorios/mensal?meses=12'),
  })

  const hora = new Date().getHours()
  const saudacao = hora < 12 ? 'Bom dia' : hora < 18 ? 'Boa tarde' : 'Boa noite'
  const d = resumo.data
  const atrasados = d?.cobranca.atrasados
  const pendentes = d?.cobranca.pendentes

  return (
    <>
      <PageHeader
        eyebrow="Início"
        title={`${saudacao}, ${user?.nome.split(' ')[0]}.`}
        subtitle="O dia, o mês e quem ainda deve. Cada número abre a tela que resolve."
        actions={
          // a recepção é um diálogo dentro de /os; daqui se leva o dono até lá, sem inventar rota
          <Link to="/os" className={buttonClasses('primary')}>
            <CarFront className="h-4 w-4" /> Pátio e OS
          </Link>
        }
      />

      {resumo.isError && (
        <div className="mb-5">
          <ErrorState message="Não deu para carregar o resumo." onRetry={() => resumo.refetch()} />
        </div>
      )}

      {/* Faixa de atraso: quando existe, é a primeira coisa da página — dinheiro entregue e não
          recebido não pode esperar o dono rolar a tela. */}
      {atrasados && atrasados.qtd > 0 && (
        <Link
          to="/financeiro/cobrancas?situacao=atrasado"
          className="mb-5 flex items-center justify-between gap-4 rounded-lg border border-danger/35 bg-danger-wash px-4 py-3 transition hover:border-danger/60"
        >
          <div className="flex items-center gap-3">
            <AlertTriangle className="h-5 w-5 shrink-0 text-danger" />
            <div>
              <div className="text-[14px] font-medium text-danger">
                {atrasados.qtd === 1 ? '1 cobrança atrasada' : `${atrasados.qtd} cobranças atrasadas`}
              </div>
              <div className="text-[13px] text-ink-2">
                <Dinheiro centavos={atrasados.total_centavos} /> entregues e ainda não recebidos.
              </div>
            </div>
          </div>
          <span className="flex shrink-0 items-center gap-1 text-[13px] text-danger">
            Ver <ArrowRight className="h-3.5 w-3.5" />
          </span>
        </Link>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {resumo.isPending ? (
          <SkeletonCards quantos={4} />
        ) : (
          d && (
            <>
              <StatCard
                label="Recebido hoje"
                valor={money(d.hoje.recebido_centavos)}
                destaque
                detalhe="Entrou no caixa de hoje"
                to="/financeiro"
              />
              <StatCard
                label={`Faturado — ${d.mes.label.toLowerCase()}`}
                valor={money(d.mes.faturado_centavos)}
                detalhe={`${d.mes.os_concluidas} ${d.mes.os_concluidas === 1 ? 'OS entregue' : 'OS entregues'}`}
                variacao={variacaoPct(d.mes.faturado_centavos, d.mes.mes_anterior.faturado_centavos)}
                to="/relatorios"
              />
              <StatCard
                label="A receber"
                valor={money(pendentes!.total_centavos)}
                tone={pendentes!.qtd > 0 ? 'warn' : undefined}
                detalhe={`${pendentes!.qtd} ${pendentes!.qtd === 1 ? 'cobrança em aberto' : 'cobranças em aberto'}`}
                to="/financeiro/cobrancas?situacao=pendente"
              />
              <StatCard
                label="Atrasado"
                valor={money(atrasados!.total_centavos)}
                tone={atrasados!.qtd > 0 ? 'danger' : undefined}
                detalhe={atrasados!.qtd > 0 ? 'Entregue sem receber' : 'Nada atrasado'}
                to="/financeiro/cobrancas?situacao=atrasado"
              />
            </>
          )
        )}
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-[2fr_1fr]">
        <Card title="Faturado e recebido nos últimos 12 meses">
          {serie.isPending ? (
            <div className="h-[168px] animate-pulse rounded-md bg-surface-2" aria-hidden />
          ) : serie.isError ? (
            <ErrorState message="Não deu para carregar a evolução." onRetry={() => serie.refetch()} />
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
            <strong className="font-medium text-ink-2">Faturado</strong> é serviço entregue no mês;{' '}
            <strong className="font-medium text-ink-2">recebido</strong> é dinheiro que entrou. Divergem quando o
            cliente paga o sinal num mês e leva o carro no outro — ou quando leva devendo.
          </p>
        </Card>

        <Card title="Agora na loja">
          <div className="grid gap-3">
            <LinhaAtalho
              to="/os"
              icone={<CarFront className="h-4 w-4 text-gold" />}
              label="No pátio"
              valor={d?.hoje.no_patio_qtd}
            />
            <LinhaAtalho
              to="/agenda"
              icone={<CalendarDays className="h-4 w-4 text-gold" />}
              label="Chegam hoje"
              valor={d?.hoje.chegam_qtd}
            />
            <LinhaAtalho
              to="/os?status=orcamento"
              icone={<FileText className="h-4 w-4 text-gold" />}
              label="Orçamentos abertos"
              valor={d?.hoje.orcamentos_abertos_qtd}
            />
            <LinhaAtalho
              to="/financeiro"
              icone={<Wallet className="h-4 w-4 text-gold" />}
              label="Ticket médio do mês"
              valor={d ? money(d.mes.ticket_medio_centavos) : undefined}
            />
          </div>
        </Card>
      </div>
    </>
  )
}

function LinhaAtalho({
  to,
  icone,
  label,
  valor,
}: {
  to: string
  icone: React.ReactNode
  label: string
  valor: number | string | undefined
}) {
  return (
    <Link
      to={to}
      className="group flex items-center justify-between gap-3 rounded-md border border-line px-3 py-2.5 transition hover:border-gold/50"
    >
      <span className="flex items-center gap-2.5 text-[13.5px] text-ink-2">
        {icone}
        {label}
      </span>
      <span className="tabular flex items-center gap-1.5 font-medium text-ink">
        {valor ?? '—'}
        <ArrowRight className="h-3.5 w-3.5 text-muted transition group-hover:text-gold-deep" />
      </span>
    </Link>
  )
}
