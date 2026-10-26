import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, X } from 'lucide-react'
import { api, errorMessage } from '../../api/client'
import type { Page, Service, Vehicle, WorkOrderDetail } from '../../api/types'
import { Badge, Button, Dialog, Field, Input, Select, Textarea, cx, useToast } from '../../components/ui'
import { ClientPicker, type PickedClient } from '../../components/ClientPicker'
import { MoneyInput } from '../../components/MoneyInput'
import { duracao, money, plate } from '../../lib/format'
import { localInputValue, toIsoFromLocalInput } from '../../lib/datetime'

interface ItemDraft {
  service_id: number
  descricao: string
  valor_centavos: number
}

/** Novo orçamento (sem data) ou agendamento (com veículo e data). */
export function WorkOrderForm({
  open,
  onClose,
  clientId,
  onSaved,
}: {
  open: boolean
  onClose: () => void
  clientId?: number
  onSaved?: (wo: WorkOrderDetail) => void
}) {
  const qc = useQueryClient()
  const toast = useToast()
  const [owner, setOwner] = useState<PickedClient | null>(null)
  const [vehicleId, setVehicleId] = useState<string>('')
  const [quando, setQuando] = useState('')
  const [itens, setItens] = useState<ItemDraft[]>([])
  const [servicoId, setServicoId] = useState('')
  const [observacoes, setObservacoes] = useState('')
  const [error, setError] = useState<string | null>(null)

  const efetivoClientId = clientId ?? owner?.id ?? null

  useEffect(() => {
    if (!open) return
    setOwner(null)
    setVehicleId('')
    setQuando('')
    setItens([])
    setServicoId('')
    setObservacoes('')
    setError(null)
  }, [open, clientId])

  const servicos = useQuery({
    queryKey: ['services', 'ativos'],
    queryFn: () => api<Page<Service>>('/services', { query: { apenas_ativos: true, page_size: 200 } }),
    enabled: open,
    staleTime: 60_000,
  })

  const veiculos = useQuery({
    queryKey: ['vehicles', 'do-cliente', efetivoClientId],
    queryFn: () => api<Vehicle[]>(`/clients/${efetivoClientId}/vehicles`),
    enabled: open && !!efetivoClientId,
  })

  // trocou de cliente: o veículo do anterior não vale mais
  useEffect(() => {
    setVehicleId('')
  }, [efetivoClientId])

  // um veículo só: já vem escolhido
  useEffect(() => {
    if (veiculos.data?.length === 1) setVehicleId(String(veiculos.data[0].id))
  }, [veiculos.data])

  const total = useMemo(() => itens.reduce((soma, i) => soma + i.valor_centavos, 0), [itens])
  const duracaoMin = useMemo(
    () => itens.reduce((soma, i) => soma + (servicos.data?.items.find((s) => s.id === i.service_id)?.duracao_estimada_min ?? 0), 0),
    [itens, servicos.data],
  )

  const addServico = () => {
    const s = servicos.data?.items.find((x) => x.id === Number(servicoId))
    if (!s) return
    setItens((atual) => [...atual, { service_id: s.id, descricao: s.nome, valor_centavos: s.valor_base_centavos }])
    setServicoId('')
  }

  const save = useMutation({
    mutationFn: (comoOrcamento: boolean) =>
      api<WorkOrderDetail>('/work-orders', {
        method: 'POST',
        body: {
          client_id: efetivoClientId,
          vehicle_id: vehicleId ? Number(vehicleId) : null,
          // a data combinada por telefone fica guardada mesmo no orçamento
          scheduled_at: toIsoFromLocalInput(quando),
          status: comoOrcamento ? 'orcamento' : 'agendado',
          itens: itens.map((i) => ({ service_id: i.service_id, valor_centavos: i.valor_centavos })),
          observacoes: observacoes.trim() || null,
        },
      }),
    onSuccess: (wo) => {
      void qc.invalidateQueries({ queryKey: ['agenda'] })
      void qc.invalidateQueries({ queryKey: ['work-orders'] })
      void qc.invalidateQueries({ queryKey: ['clients'] })
      toast.push(wo.status === 'orcamento' ? 'Orçamento criado.' : 'Agendamento criado.')
      onSaved?.(wo)
      onClose()
    },
    onError: (e) => setError(errorMessage(e)),
  })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    if (!efetivoClientId) return setError('Escolha o cliente.')
    if (!vehicleId) return setError('Escolha o veículo.')
    if (!quando) return setError('Informe a data e a hora.')
    save.mutate(false)
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      width="lg"
      title="Novo agendamento"
      footer={
        <>
          <Button variant="ghost" type="button" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            variant="secondary"
            type="button"
            loading={save.isPending}
            disabled={!efetivoClientId}
            onClick={() => {
              setError(null)
              save.mutate(true)
            }}
            title="Guarda como orçamento: sem data marcada, pode virar agendamento depois"
          >
            Salvar como orçamento
          </Button>
          <Button type="submit" form="wo-form" loading={save.isPending}>
            Agendar
          </Button>
        </>
      }
    >
      <form id="wo-form" onSubmit={submit} className="grid gap-4">
        {!clientId && (
          <Field label="Cliente">
            <ClientPicker value={owner} onChange={setOwner} autoFocus />
          </Field>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Veículo" hint={!efetivoClientId ? 'Escolha o cliente primeiro.' : undefined}>
            <Select value={vehicleId} onChange={(e) => setVehicleId(e.target.value)} disabled={!efetivoClientId || veiculos.isLoading}>
              <option value="">{veiculos.data?.length === 0 ? 'Nenhum veículo cadastrado' : 'Selecione…'}</option>
              {veiculos.data?.map((v) => (
                <option key={v.id} value={v.id}>
                  {plate(v.placa)} · {v.marca ? `${v.marca} ` : ''}
                  {v.modelo}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Data e hora" hint="Se ainda não fechou, salve como orçamento — a data fica guardada.">
            <Input type="datetime-local" value={quando} onChange={(e) => setQuando(e.target.value)} min={localInputValue(new Date())} className="tabular" />
          </Field>
        </div>

        <div>
          <span className="label-dim mb-1.5 block">Serviços</span>
          <div className="flex gap-2">
            <Select value={servicoId} onChange={(e) => setServicoId(e.target.value)} className="flex-1">
              <option value="">Escolha um serviço do catálogo…</option>
              {servicos.data?.items.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.nome} — {money(s.valor_base_centavos)}
                </option>
              ))}
            </Select>
            <Button type="button" variant="secondary" onClick={addServico} disabled={!servicoId}>
              <Plus className="h-4 w-4" /> Adicionar
            </Button>
          </div>

          {itens.length > 0 && (
            <ul className="mt-3 divide-y divide-line rounded-md border border-line">
              {itens.map((item, idx) => (
                <li key={`${item.service_id}-${idx}`} className="flex items-center gap-3 px-3 py-2">
                  <span className="flex-1 truncate text-[14px]">{item.descricao}</span>
                  <div className="w-36">
                    <MoneyInput
                      value={item.valor_centavos}
                      onChange={(centavos) =>
                        setItens((atual) => atual.map((x, i) => (i === idx ? { ...x, valor_centavos: centavos ?? 0 } : x)))
                      }
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => setItens((atual) => atual.filter((_, i) => i !== idx))}
                    className="rounded p-1 text-muted hover:bg-surface-2 hover:text-danger"
                    aria-label={`Remover ${item.descricao}`}
                  >
                    <X className="h-4 w-4" />
                  </button>
                </li>
              ))}
            </ul>
          )}

          <div className={cx('mt-2 flex items-center justify-between text-[13px]', itens.length === 0 && 'text-muted')}>
            <span>
              {itens.length === 0 ? 'Nenhum serviço ainda — pode adicionar depois.' : `${itens.length} serviço(s) · cerca de ${duracao(duracaoMin)}`}
            </span>
            {itens.length > 0 && (
              <span className="tabular font-medium text-ink">
                Total <Badge tone="gold" className="ml-1 !text-[12px]">{money(total)}</Badge>
              </span>
            )}
          </div>
        </div>

        <Field label="Observações (opcional)">
          <Textarea value={observacoes} onChange={(e) => setObservacoes(e.target.value)} placeholder="Combinações com o cliente, pedidos especiais…" />
        </Field>

        {error && <p className="rounded-md border border-danger/30 bg-danger-wash px-3 py-2 text-[13px] text-danger">{error}</p>}
      </form>
    </Dialog>
  )
}
