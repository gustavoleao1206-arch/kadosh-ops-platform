import { useState } from 'react'
import { useSearchParams, useNavigate } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { api, errorMessage } from '../../api/client'
import type { Page, SituacaoCobranca, WorkOrder } from '../../api/types'
import { Button, Card, EmptyState, ErrorState, Table, Td, Th, cx, rowClick } from '../../components/ui'
import { Dinheiro, EtiquetaCobranca, SaldoDestacado, Skeleton } from '../../components/stats'
import { date, plate } from '../../lib/format'

const PAGE_SIZE = 50

const ABAS: { v: SituacaoCobranca; l: string; vazio: string; dica: string }[] = [
  {
    v: 'pendente',
    l: 'A receber',
    vazio: 'Nada em aberto.',
    dica: 'OS com saldo, dentro do prazo ou com o carro ainda na loja.',
  },
  {
    v: 'atrasado',
    l: 'Atrasadas',
    vazio: 'Nenhuma cobrança atrasada — tudo em dia.',
    dica: 'Prazo vencido, ou carro entregue sem receber e sem prazo combinado.',
  },
  { v: 'pago', l: 'Pagas', vazio: 'Nenhuma OS quitada por aqui ainda.', dica: 'Quitadas, para conferência.' },
]

/**
 * Quem ainda deve — e há quanto tempo.
 *
 * A situação de cada linha NÃO é calculada aqui: vem pronta do backend (`situacao_cobranca` com
 * rótulo e cor). O painel nem sabe a regra do atraso, e é de propósito: a data de corte é a do
 * servidor. Um computador com o relógio errado inventaria atraso que não existe.
 *
 * O filtro roda em SQL, no servidor, para a paginação bater: peneirar no navegador devolveria
 * "página 1 de 50" com seis linhas.
 */
export function CobrancasPage() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const situacao = (params.get('situacao') as SituacaoCobranca) ?? 'pendente'
  const valida = ABAS.some((a) => a.v === situacao) ? situacao : 'pendente'
  const page = Math.max(1, Number(params.get('page') ?? 1) || 1)
  // Um "agora" só, capturado na montagem: ler o relógio dentro de cada linha deixa o render impuro
  // e faz "há 3d" mudar sozinho no meio de uma leitura. A situação em si vem do servidor.
  const [agora] = useState(() => Date.now())

  const update = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(patch)) {
      if (v === null || v === '') next.delete(k)
      else next.set(k, v)
    }
    if (!('page' in patch)) next.delete('page')
    setParams(next, { replace: true })
  }

  const lista = useQuery({
    queryKey: ['work-orders', { cobranca: valida, page }],
    queryFn: () =>
      api<Page<WorkOrder>>('/work-orders', { query: { cobranca: valida, page, page_size: PAGE_SIZE } }),
    placeholderData: (prev) => prev,
  })

  const aba = ABAS.find((a) => a.v === valida)!
  const itens = lista.data?.items ?? []
  const totalPages = lista.data ? Math.max(1, Math.ceil(lista.data.total / PAGE_SIZE)) : 1
  const somaVisivel = itens.reduce((s, w) => s + w.saldo_centavos, 0)

  return (
    <>
      <div className="mb-5 inline-flex flex-wrap gap-1 rounded-lg border border-line bg-surface-2 p-1">
        {ABAS.map((a) => (
          <button
            key={a.v}
            type="button"
            onClick={() => update({ situacao: a.v })}
            className={cx(
              'rounded-md px-3.5 py-1.5 text-[13.5px] transition',
              a.v === valida ? 'bg-surface text-ink shadow-card' : 'text-muted hover:text-ink',
            )}
          >
            {a.l}
          </button>
        ))}
      </div>

      <Card
        title={aba.l}
        actions={
          itens.length > 0 &&
          valida !== 'pago' && (
            <span className="text-[13px] text-muted">
              Nesta página: <Dinheiro centavos={somaVisivel} className="font-medium text-ink" />
            </span>
          )
        }
      >
        <p className="mb-4 text-[12.5px] text-muted">{aba.dica}</p>

        {lista.isError && !lista.data ? (
          <ErrorState message={errorMessage(lista.error)} onRetry={() => void lista.refetch()} />
        ) : lista.isPending ? (
          <div className="grid gap-2">
            {Array.from({ length: 5 }, (_, i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))}
          </div>
        ) : itens.length === 0 ? (
          <EmptyState
            title={aba.vazio}
            hint={
              valida === 'atrasado'
                ? 'Quando um carro sai devendo sem prazo combinado, ele aparece aqui no dia seguinte.'
                : undefined
            }
          />
        ) : (
          <>
            <Table>
              <thead>
                <tr>
                  <Th>OS</Th>
                  <Th>Cliente</Th>
                  <Th>Veículo</Th>
                  <Th className="text-right">Total</Th>
                  <Th className="text-right">Pago</Th>
                  <Th className="text-right">Falta</Th>
                  <Th>Prazo</Th>
                  <Th>Situação</Th>
                </tr>
              </thead>
              <tbody>
                {itens.map((w) => (
                  <tr key={w.id} {...rowClick(() => navigate(`/os/${w.id}`))}>
                    <Td>
                      <span className="tabular">{w.numero ? String(w.numero).padStart(3, '0') : '—'}</span>
                    </Td>
                    <Td className="max-w-[200px] truncate">{w.cliente.nome}</Td>
                    <Td className="text-muted">
                      {w.veiculo ? `${w.veiculo.modelo} · ${plate(w.veiculo.placa)}` : '—'}
                    </Td>
                    <Td className="text-right">
                      <Dinheiro centavos={w.valor_total_centavos} />
                    </Td>
                    <Td className="text-right text-muted">
                      <Dinheiro centavos={w.pago_centavos} />
                    </Td>
                    <Td className="text-right">
                      <SaldoDestacado centavos={w.saldo_centavos} tone={w.situacao_cobranca_tone} />
                    </Td>
                    <Td>
                      <Prazo iso={w.vencimento} atrasado={w.situacao_cobranca === 'atrasado'} agora={agora} />
                    </Td>
                    <Td>
                      <EtiquetaCobranca label={w.situacao_cobranca_label} tone={w.situacao_cobranca_tone} />
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>

            {totalPages > 1 && (
              <div className="mt-4 flex items-center justify-between gap-3 text-[13px] text-muted">
                <span className="tabular">
                  Página {page} de {totalPages} · {lista.data!.total} no total
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
              Para dar prazo a uma OS entregue devendo, abra a OS e defina o vencimento — ela sai de "atrasada" e
              volta para "a receber" até a data combinada.
            </p>
          </>
        )}
      </Card>
    </>
  )
}

/** Prazo com os dias de atraso ao lado: "há 3 dias" é mais acionável que a data crua. */
function Prazo({ iso, atrasado, agora }: { iso: string | null; atrasado: boolean; agora: number }) {
  if (!iso) {
    return <span className="text-muted">{atrasado ? 'sem prazo' : '—'}</span>
  }
  const dias = Math.floor((agora - new Date(iso).getTime()) / 86_400_000)
  return (
    <span className={cx('tabular', atrasado && 'text-danger')}>
      {date(iso)}
      {atrasado && dias > 0 && <span className="ml-1.5 text-[12px]">há {dias}d</span>}
    </span>
  )
}
