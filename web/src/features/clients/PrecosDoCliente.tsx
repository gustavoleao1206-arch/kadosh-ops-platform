import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, RotateCcw } from 'lucide-react'
import { api, errorMessage } from '../../api/client'
import type { PrecoCliente } from '../../api/types'
import { Badge, Button, Card, ErrorState, Table, Td, Th, cx, useToast } from '../../components/ui'
import { MoneyInput } from '../../components/MoneyInput'
import { Dinheiro, Skeleton } from '../../components/stats'
import { useAuth } from '../../app/auth'
import { money } from '../../lib/format'

/**
 * Quanto ESTE cliente paga em cada serviço.
 *
 * É extensão do catálogo, não desconto — por isso quem edita é o dono, e o sócio só lê (ele precisa
 * saber por que a OS veio com outro valor). A diferença prática entre os dois: desconto é um
 * abatimento naquela OS, com valor e motivo no histórico; preço combinado é permanente e ninguém
 * precisa lembrar dele na hora de lançar.
 *
 * O aviso de que vale para as PRÓXIMAS OS não é detalhe de interface: o preço é copiado para o item
 * no lançamento e congela ali. Mudar aqui não reescreve nenhuma OS nem relatório fechado — e é
 * exatamente isso que o dono precisa saber antes de mexer.
 */
export function PrecosDoCliente({ clientId }: { clientId: number }) {
  const qc = useQueryClient()
  const toast = useToast()
  const { user } = useAuth()
  const podeEditar = user?.role === 'admin'
  const [editando, setEditando] = useState<number | null>(null)
  const [valor, setValor] = useState<number | null>(null)

  const precos = useQuery({
    queryKey: ['clients', clientId, 'service-prices'],
    queryFn: () => api<PrecoCliente[]>(`/clients/${clientId}/service-prices`),
  })

  const invalidar = () => {
    void qc.invalidateQueries({ queryKey: ['clients', clientId, 'service-prices'] })
    // o seletor de serviço da OS pede o catálogo já resolvido para este cliente
    void qc.invalidateQueries({ queryKey: ['services'] })
  }

  const definir = useMutation({
    mutationFn: (v: { serviceId: number; valor_centavos: number }) =>
      api<PrecoCliente>(`/clients/${clientId}/service-prices/${v.serviceId}`, {
        method: 'PUT',
        body: { valor_centavos: v.valor_centavos },
      }),
    onSuccess: (linha) => {
      invalidar()
      setEditando(null)
      toast.push(`${linha.servico_nome}: ${money(linha.valor_cliente_centavos ?? 0)} para este cliente.`)
    },
    onError: (e) => toast.push(errorMessage(e), 'danger'),
  })

  const remover = useMutation({
    mutationFn: (serviceId: number) =>
      api<void>(`/clients/${clientId}/service-prices/${serviceId}`, { method: 'DELETE' }),
    onSuccess: () => {
      invalidar()
      setEditando(null)
      toast.push('Voltou ao preço de tabela.')
    },
    onError: (e) => toast.push(errorMessage(e), 'danger'),
  })

  const abrir = (linha: PrecoCliente) => {
    setEditando(linha.service_id)
    setValor(linha.valor_efetivo_centavos)
  }

  const linhas = precos.data ?? []
  const combinados = linhas.filter((l) => l.valor_cliente_centavos !== null).length

  return (
    <Card
      title="Preços deste cliente"
      actions={
        combinados > 0 && (
          <span className="text-[13px] text-muted">
            {combinados} {combinados === 1 ? 'serviço combinado' : 'serviços combinados'}
          </span>
        )
      }
    >
      <p className="mb-4 text-[12.5px] text-muted">
        Vale para as <strong className="font-medium text-ink-2">próximas</strong> OS. As já lançadas guardam o valor
        do dia em que foram feitas e não mudam.
        {!podeEditar && ' Só o administrador altera preços.'}
      </p>

      {precos.isError ? (
        <ErrorState message={errorMessage(precos.error)} onRetry={() => void precos.refetch()} />
      ) : precos.isPending ? (
        <div className="grid gap-2">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-9 w-full" />
          ))}
        </div>
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Serviço</Th>
              <Th className="text-right">Tabela</Th>
              <Th className="text-right">Este cliente</Th>
              {podeEditar && <Th />}
            </tr>
          </thead>
          <tbody>
            {linhas.map((l) => {
              const emEdicao = editando === l.service_id
              const temCombinado = l.valor_cliente_centavos !== null
              return (
                <tr key={l.service_id} className={cx(!l.ativo && 'text-muted')}>
                  <Td>
                    <span className="flex items-center gap-2">
                      {l.servico_nome}
                      {/* só aparece para serviço desativado que AINDA tem combinado: some da tela
                          seria pior — viraria cadastro que o dono não vê nem alcança para apagar */}
                      {!l.ativo && <Badge tone="neutral">desativado</Badge>}
                    </span>
                  </Td>
                  <Td className="text-right text-muted">
                    <Dinheiro centavos={l.valor_base_centavos} />
                  </Td>
                  <Td className="text-right">
                    {emEdicao ? (
                      <div className="flex justify-end">
                        <div className="w-32">
                          <MoneyInput value={valor} onChange={setValor} autoFocus ariaLabel="Preço para este cliente" />
                        </div>
                      </div>
                    ) : temCombinado ? (
                      <Dinheiro centavos={l.valor_cliente_centavos!} className="font-medium text-gold-deep" />
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </Td>
                  {podeEditar && (
                    <Td className="text-right">
                      {emEdicao ? (
                        <div className="flex justify-end gap-1.5">
                          <Button
                            size="sm"
                            loading={definir.isPending}
                            disabled={valor === null}
                            onClick={() => definir.mutate({ serviceId: l.service_id, valor_centavos: valor ?? 0 })}
                          >
                            <Check className="h-3.5 w-3.5" /> Salvar
                          </Button>
                          <Button size="sm" variant="ghost" onClick={() => setEditando(null)}>
                            Cancelar
                          </Button>
                        </div>
                      ) : (
                        <div className="flex justify-end gap-1.5">
                          {l.ativo && (
                            <Button size="sm" variant="ghost" onClick={() => abrir(l)}>
                              {temCombinado ? 'Alterar' : 'Definir'}
                            </Button>
                          )}
                          {temCombinado && (
                            <Button
                              size="sm"
                              variant="ghost"
                              loading={remover.isPending}
                              onClick={() => remover.mutate(l.service_id)}
                              title="Volta ao preço de tabela nas próximas OS"
                            >
                              <RotateCcw className="h-3.5 w-3.5" />
                            </Button>
                          )}
                        </div>
                      )}
                    </Td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </Table>
      )}
    </Card>
  )
}
