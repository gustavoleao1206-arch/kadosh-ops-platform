import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Car, Check, Plus, Search, User, X } from 'lucide-react'
import { api, errorMessage } from '../../api/client'
import type { Page, SearchResult, Service, Vehicle, WorkOrderDetail } from '../../api/types'
import { Badge, Button, Dialog, Field, Input, Select, Spinner, Textarea, cx, useToast } from '../../components/ui'
import { MoneyInput } from '../../components/MoneyInput'
import { useDebounced } from '../../lib/hooks'
import { duracao, money, phone, plate } from '../../lib/format'

interface ItemDraft {
  service_id: number
  descricao: string
  valor_centavos: number
  duracao_min: number
}

interface Escolha {
  clientId?: number
  vehicleId?: number
  nome: string
  telefone: string
  placa: string
  marca: string
  modelo: string
  cor: string
}

const VAZIO: Escolha = { nome: '', telefone: '', placa: '', marca: '', modelo: '', cor: '' }

/** "ABC1D23" e "abc-1d23" são placa; "Maria" não — o campo de busca aceita os três. */
const pareceplaca = (texto: string) => /^[A-Za-z]{3}[- ]?\d/.test(texto.trim())

/** 10 dígitos ou mais (com ou sem parênteses e traço) é telefone, não nome de gente. */
const parecetelefone = (texto: string) => /^[\d\s()+-]+$/.test(texto.trim()) && texto.replace(/\D/g, '').length >= 10

/**
 * Recepção do veículo — uma tela só, do jeito que o pátio funciona:
 * busca pela placa (ou telefone/nome), o que não existir é cadastrado junto, e a OS já nasce recebida.
 */
export function IntakeDialog({
  open,
  onClose,
  workOrderId,
  onRecebido,
}: {
  open: boolean
  onClose: () => void
  /** recebendo um agendamento existente */
  workOrderId?: number
  onRecebido?: (wo: WorkOrderDetail) => void
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const [busca, setBusca] = useState('')
  const [escolha, setEscolha] = useState<Escolha>(VAZIO)
  const [itens, setItens] = useState<ItemDraft[]>([])
  const [observacoesEntrada, setObservacoesEntrada] = useState('')
  const [error, setError] = useState<string | null>(null)
  const chave = useRef<string>('')
  // veículo que a OS agendada já apontava: se não mudar, nem vai no corpo da requisição
  const veiculoOriginal = useRef<number | null>(null)
  const debounced = useDebounced(busca, 250)

  useEffect(() => {
    if (!open) return
    setBusca('')
    setEscolha(VAZIO)
    setItens([])
    setObservacoesEntrada('')
    setError(null)
    veiculoOriginal.current = null
    // uma chave por abertura: tocar duas vezes em "Receber" não abre duas OS
    chave.current = `intake-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  }, [open])

  // recebendo um agendamento: cliente e carro já estão na OS
  const agendada = useQuery({
    queryKey: ['work-orders', workOrderId],
    queryFn: () => api<WorkOrderDetail>(`/work-orders/${workOrderId}`),
    enabled: open && !!workOrderId,
  })

  useEffect(() => {
    const wo = agendada.data
    if (!open || !workOrderId || !wo || veiculoOriginal.current !== null) return
    veiculoOriginal.current = wo.veiculo?.id ?? 0
    setEscolha({
      clientId: wo.client_id,
      vehicleId: wo.veiculo?.id,
      nome: wo.cliente.nome,
      telefone: wo.cliente.telefone ?? '',
      placa: wo.veiculo?.placa ?? '',
      marca: wo.veiculo?.marca ?? '',
      modelo: wo.veiculo?.modelo ?? '',
      cor: wo.veiculo?.cor ?? '',
    })
  }, [open, workOrderId, agendada.data])

  const resultados = useQuery({
    queryKey: ['search', debounced],
    queryFn: () => api<SearchResult>('/search', { query: { q: debounced } }),
    enabled: open && debounced.trim().length >= 2 && !escolha.clientId,
    staleTime: 10_000,
  })

  const servicos = useQuery({
    queryKey: ['services', 'ativos'],
    queryFn: () => api<Page<Service>>('/services', { query: { apenas_ativos: true, page_size: 200 } }),
    enabled: open,
    staleTime: 60_000,
  })

  const veiculosDoCliente = useQuery({
    queryKey: ['vehicles', 'do-cliente', escolha.clientId],
    queryFn: () => api<Vehicle[]>(`/clients/${escolha.clientId}/vehicles`),
    enabled: open && !!escolha.clientId && !escolha.vehicleId,
  })

  const total = useMemo(() => itens.reduce((s, i) => s + i.valor_centavos, 0), [itens])
  const duracaoMin = useMemo(() => itens.reduce((s, i) => s + i.duracao_min, 0), [itens])

  const escolherVeiculo = (v: SearchResult['veiculos'][number]) => {
    setEscolha({
      clientId: v.cliente.id,
      vehicleId: v.id,
      nome: v.cliente.nome,
      telefone: v.cliente.telefone ?? '',
      placa: v.placa ?? '',
      marca: v.marca ?? '',
      modelo: v.modelo,
      cor: v.cor ?? '',
    })
    setBusca('')
  }

  const escolherCliente = (c: SearchResult['clientes'][number]) => {
    setEscolha({ ...VAZIO, clientId: c.id, nome: c.nome, telefone: c.telefone ?? '' })
    setBusca('')
  }

  const novo = () => {
    // o que foi digitado na busca já vai para o campo certo: placa, telefone ou nome
    const texto = busca.trim()
    if (pareceplaca(texto)) setEscolha({ ...VAZIO, placa: texto.toUpperCase().replace(/[^A-Z0-9]/g, '') })
    else if (parecetelefone(texto)) setEscolha({ ...VAZIO, telefone: texto })
    else setEscolha({ ...VAZIO, nome: texto })
    setBusca('')
  }

  const addServico = (id: string) => {
    const s = servicos.data?.items.find((x) => x.id === Number(id))
    if (!s) return
    setItens((atual) => [
      ...atual,
      { service_id: s.id, descricao: s.nome, valor_centavos: s.valor_base_centavos, duracao_min: s.duracao_estimada_min },
    ])
  }

  // o carro mudou em relação ao que estava marcado?
  const trocouOCarro = !!workOrderId && veiculoOriginal.current !== null && (escolha.vehicleId ?? 0) !== veiculoOriginal.current

  const veiculoBody = () =>
    escolha.vehicleId
      ? { id: escolha.vehicleId }
      : {
          placa: escolha.placa.trim() || null,
          marca: escolha.marca.trim() || null,
          modelo: escolha.modelo.trim(),
          cor: escolha.cor.trim() || null,
        }

  const receber = useMutation({
    mutationFn: () =>
      api<WorkOrderDetail>('/work-orders/intake', {
        method: 'POST',
        body: workOrderId
          ? {
              work_order_id: workOrderId,
              // só vai se o carro que chegou for outro — senão a OS mantém o que já tinha
              veiculo: trocouOCarro ? veiculoBody() : null,
              itens: itens.map((i) => ({ service_id: i.service_id, valor_centavos: i.valor_centavos })),
              observacoes_entrada: observacoesEntrada.trim() || null,
              idempotency_key: chave.current,
            }
          : {
              cliente: escolha.clientId
                ? { id: escolha.clientId }
                : { nome: escolha.nome.trim(), telefone: escolha.telefone.trim() || null },
              veiculo: veiculoBody(),
              itens: itens.map((i) => ({ service_id: i.service_id, valor_centavos: i.valor_centavos })),
              observacoes_entrada: observacoesEntrada.trim() || null,
              idempotency_key: chave.current,
            },
      }),
    onSuccess: (wo) => {
      void qc.invalidateQueries({ queryKey: ['work-orders'] })
      void qc.invalidateQueries({ queryKey: ['patio'] })
      void qc.invalidateQueries({ queryKey: ['agenda'] })
      void qc.invalidateQueries({ queryKey: ['clients'] })
      void qc.invalidateQueries({ queryKey: ['vehicles'] })
      void qc.invalidateQueries({ queryKey: ['search'] })
      toast.push(`Veículo recebido — OS nº ${String(wo.numero).padStart(3, '0')}.`)
      onRecebido?.(wo)
      onClose()
    },
    onError: (e) => setError(errorMessage(e)),
  })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!workOrderId && !escolha.clientId && !escolha.nome.trim()) return setError('Informe o cliente.')
    if (!escolha.vehicleId && !escolha.modelo.trim()) return setError('Informe o modelo do veículo.')
    receber.mutate()
  }

  const temEscolha = !!workOrderId || !!escolha.clientId || !!escolha.nome || !!escolha.telefone || !!escolha.modelo || !!escolha.placa
  const achouAlgo = !!resultados.data && (resultados.data.veiculos.length > 0 || resultados.data.clientes.length > 0)

  return (
    <Dialog
      open={open}
      onClose={onClose}
      width="lg"
      title={workOrderId ? 'Receber veículo agendado' : 'Receber veículo'}
      footer={
        <>
          <Button variant="ghost" type="button" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" form="intake-form" loading={receber.isPending} disabled={!temEscolha}>
            <Check className="h-4 w-4" /> Receber e abrir OS
          </Button>
        </>
      }
    >
      <form id="intake-form" onSubmit={submit} className="grid gap-4">
        {agendada.isLoading ? (
          <Spinner />
        ) : !temEscolha ? (
          <div>
            <Field label="Placa, telefone ou nome" hint="Se já for cliente, os dados vêm preenchidos.">
              <div className="relative">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
                <Input
                  value={busca}
                  onChange={(e) => setBusca(e.target.value)}
                  placeholder="BRA2E19"
                  className={cx('pl-9', pareceplaca(busca) && 'tabular uppercase')}
                  data-autofocus
                />
              </div>
            </Field>

            {debounced.trim().length >= 2 && (
              <div className="mt-2 overflow-hidden rounded-md border border-line">
                {resultados.data?.veiculos.slice(0, 5).map((v) => (
                  <button key={`v${v.id}`} type="button" onClick={() => escolherVeiculo(v)} className="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-surface-2">
                    <Car className="h-4 w-4 shrink-0 text-gold" />
                    <span className="tabular font-medium">{plate(v.placa)}</span>
                    <span className="flex-1 truncate text-muted">
                      {v.marca ? `${v.marca} ` : ''}
                      {v.modelo} · {v.cliente.nome}
                    </span>
                  </button>
                ))}
                {resultados.data?.clientes.slice(0, 4).map((c) => (
                  <button key={`c${c.id}`} type="button" onClick={() => escolherCliente(c)} className="flex w-full items-center gap-3 px-3 py-2.5 text-left hover:bg-surface-2">
                    <User className="h-4 w-4 shrink-0 text-gold" />
                    <span className="flex-1 truncate font-medium">{c.nome}</span>
                    <span className="tabular text-[12.5px] text-muted">{phone(c.telefone)}</span>
                  </button>
                ))}
                <button type="button" onClick={novo} className="flex w-full items-center gap-3 border-t border-line bg-paper px-3 py-2.5 text-left hover:bg-surface-2">
                  <Plus className="h-4 w-4 shrink-0 text-gold" />
                  <span className="text-[13.5px]">{achouAlgo ? 'Não é nenhum destes — cadastrar novo' : `Cadastrar novo com "${debounced}"`}</span>
                </button>
              </div>
            )}
          </div>
        ) : (
          <>
            {/* cliente */}
            <div className="rounded-md border border-line bg-surface-2 px-3 py-2.5">
              <div className="flex items-center justify-between gap-3">
                <span className="label-dim">Cliente</span>
                {!workOrderId && (
                  <button type="button" onClick={() => setEscolha(VAZIO)} className="rounded p-1 text-muted hover:bg-surface hover:text-ink" aria-label="Trocar cliente">
                    <X className="h-4 w-4" />
                  </button>
                )}
              </div>
              {escolha.clientId ? (
                <div className="mt-1 flex items-center gap-2 text-[14px]">
                  <span className="font-medium">{escolha.nome}</span>
                  <span className="tabular text-muted">{phone(escolha.telefone)}</span>
                  <Badge tone="ok">já cadastrado</Badge>
                </div>
              ) : (
                <div className="mt-2 grid gap-3 sm:grid-cols-2">
                  <Field label="Nome">
                    <Input required value={escolha.nome} onChange={(e) => setEscolha({ ...escolha, nome: e.target.value })} data-autofocus />
                  </Field>
                  <Field label="Telefone">
                    <Input inputMode="tel" placeholder="(82) 99999-9999" value={escolha.telefone} onChange={(e) => setEscolha({ ...escolha, telefone: e.target.value })} />
                  </Field>
                </div>
              )}
            </div>

            {/* veículo */}
            <div className="rounded-md border border-line bg-surface-2 px-3 py-2.5">
              <span className="label-dim">Veículo</span>
              {escolha.vehicleId ? (
                <div className="mt-1 flex items-center gap-2 text-[14px]">
                  <span className="tabular font-medium">{plate(escolha.placa)}</span>
                  <span className="text-muted">
                    {escolha.marca ? `${escolha.marca} ` : ''}
                    {escolha.modelo}
                    {escolha.cor ? ` · ${escolha.cor}` : ''}
                  </span>
                  <button type="button" onClick={() => setEscolha({ ...escolha, vehicleId: undefined, placa: '', marca: '', modelo: '', cor: '' })} className="ml-auto rounded p-1 text-muted hover:bg-surface hover:text-ink" aria-label="Trocar veículo">
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ) : (
                <>
                  {!!escolha.clientId && !!veiculosDoCliente.data?.length && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {veiculosDoCliente.data.map((v) => (
                        <button
                          key={v.id}
                          type="button"
                          onClick={() => setEscolha({ ...escolha, vehicleId: v.id, placa: v.placa ?? '', marca: v.marca ?? '', modelo: v.modelo, cor: v.cor ?? '' })}
                          className="rounded border border-line bg-surface px-2.5 py-1 text-[13px] hover:border-gold hover:text-gold-deep"
                        >
                          <span className="tabular">{plate(v.placa)}</span> · {v.modelo}
                        </button>
                      ))}
                    </div>
                  )}
                  <div className="mt-2 grid gap-3 sm:grid-cols-[130px_1fr_130px]">
                    <Field label="Placa">
                      <Input value={escolha.placa} onChange={(e) => setEscolha({ ...escolha, placa: e.target.value.toUpperCase() })} maxLength={8} className="tabular uppercase" />
                    </Field>
                    <Field label="Modelo">
                      <Input required value={escolha.modelo} onChange={(e) => setEscolha({ ...escolha, modelo: e.target.value })} placeholder="Civic EX" />
                    </Field>
                    <Field label="Cor">
                      <Input value={escolha.cor} onChange={(e) => setEscolha({ ...escolha, cor: e.target.value })} />
                    </Field>
                  </div>
                </>
              )}
            </div>

            {/* serviços em chips: um toque cada */}
            <div>
              <span className="label-dim mb-1.5 block">Serviços</span>
              {!!agendada.data?.itens.length && (
                <p className="mb-2 rounded-md border border-line bg-paper px-3 py-2 text-[13px] text-ink-2">
                  Já marcado: {agendada.data.itens.map((i) => i.descricao).join(', ')}.{' '}
                  <span className="text-muted">Os chips abaixo acrescentam o que for combinado agora.</span>
                </p>
              )}
              <div className="flex flex-wrap gap-1.5">
                {servicos.data?.items.slice(0, 8).map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => addServico(String(s.id))}
                    className="rounded-full border border-line bg-surface px-3 py-1.5 text-[13px] transition hover:border-gold hover:text-gold-deep"
                  >
                    + {s.nome} <span className="tabular text-muted">{money(s.valor_base_centavos)}</span>
                  </button>
                ))}
              </div>
              {(servicos.data?.items.length ?? 0) > 8 && (
                <Select value="" onChange={(e) => addServico(e.target.value)} className="mt-2 !py-1.5 text-[13px]" aria-label="Outros serviços">
                  <option value="">Outros serviços…</option>
                  {servicos.data?.items.slice(8).map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.nome} — {money(s.valor_base_centavos)}
                    </option>
                  ))}
                </Select>
              )}

              {itens.length > 0 && (
                <ul className="mt-3 divide-y divide-line rounded-md border border-line">
                  {itens.map((item, idx) => (
                    <li key={`${item.service_id}-${idx}`} className="flex items-center gap-3 px-3 py-2">
                      <span className="flex-1 truncate text-[14px]">{item.descricao}</span>
                      <div className="w-32">
                        <MoneyInput
                          value={item.valor_centavos}
                          ariaLabel={`Valor de ${item.descricao}`}
                          onChange={(c) => setItens((atual) => atual.map((x, i) => (i === idx ? { ...x, valor_centavos: c ?? 0 } : x)))}
                        />
                      </div>
                      <button type="button" onClick={() => setItens((a) => a.filter((_, i) => i !== idx))} className="rounded p-1 text-muted hover:bg-surface-2 hover:text-danger" aria-label={`Remover ${item.descricao}`}>
                        <X className="h-4 w-4" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
              <div className={cx('mt-2 flex items-center justify-between text-[13px]', itens.length === 0 && 'text-muted')}>
                <span>
                  {itens.length > 0
                    ? `${itens.length === 1 ? '1 serviço' : `${itens.length} serviços`} a mais · cerca de ${duracao(duracaoMin)}`
                    : agendada.data?.itens.length
                      ? ''
                      : 'Pode lançar os serviços depois, com o carro já no pátio.'}
                </span>
                {itens.length > 0 && (
                  <span className="tabular font-medium text-ink">
                    Total <Badge tone="gold" className="ml-1 !text-[12px]">{money(total)}</Badge>
                  </span>
                )}
              </div>
            </div>

            <Field
              label="Estado do carro na chegada"
              hint="Riscos, amassados, pertences, combustível. É a sua defesa se houver reclamação depois."
            >
              <Textarea
                value={observacoesEntrada}
                onChange={(e) => setObservacoesEntrada(e.target.value)}
                placeholder="Ex.: risco no para-choque traseiro, tanque pela metade, guarda-chuva no porta-malas"
              />
            </Field>
          </>
        )}

        {error && <p className="rounded-md border border-danger/30 bg-danger-wash px-3 py-2 text-[13px] text-danger">{error}</p>}
      </form>
    </Dialog>
  )
}
