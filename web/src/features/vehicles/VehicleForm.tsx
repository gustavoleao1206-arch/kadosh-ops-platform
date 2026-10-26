import { useEffect, useState, type FormEvent } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, errorMessage } from '../../api/client'
import type { Vehicle } from '../../api/types'
import { Button, Dialog, Field, Input, Textarea, useToast } from '../../components/ui'
import { ClientPicker, type PickedClient } from '../../components/ClientPicker'

interface Props {
  open: boolean
  onClose: () => void
  vehicle?: Vehicle | null
  /** cliente fixo (quando aberto a partir da ficha) */
  clientId?: number
  onSaved?: (v: Vehicle) => void
}

interface FormState {
  placa: string
  marca: string
  modelo: string
  cor: string
  ano: string
  observacoes: string
}

const ANO_MAX = new Date().getFullYear() + 1

export function VehicleForm({ open, onClose, vehicle, clientId, onSaved }: Props) {
  const qc = useQueryClient()
  const toast = useToast()
  const [form, setForm] = useState<FormState>({ placa: '', marca: '', modelo: '', cor: '', ano: '', observacoes: '' })
  const [owner, setOwner] = useState<PickedClient | null>(null)
  const [error, setError] = useState<string | null>(null)
  const vehicleId = vehicle?.id

  useEffect(() => {
    if (!open) return
    setForm({
      placa: vehicle?.placa ?? '',
      marca: vehicle?.marca ?? '',
      modelo: vehicle?.modelo ?? '',
      cor: vehicle?.cor ?? '',
      ano: vehicle?.ano ? String(vehicle.ano) : '',
      observacoes: vehicle?.observacoes ?? '',
    })
    setOwner(null)
    setError(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, vehicleId, clientId])

  const save = useMutation({
    mutationFn: () => {
      const base = {
        placa: form.placa.trim() || null,
        marca: form.marca.trim() || null,
        modelo: form.modelo.trim(),
        cor: form.cor.trim() || null,
        ano: form.ano ? Number(form.ano) : null,
        observacoes: form.observacoes.trim() || null,
      }
      if (vehicle) {
        const { placa, ...rest } = base
        const body = placa ? { ...rest, placa } : { ...rest, remover_placa: !!vehicle.placa }
        return api<Vehicle>(`/vehicles/${vehicle.id}`, { method: 'PATCH', body })
      }
      return api<Vehicle>('/vehicles', { method: 'POST', body: { ...base, client_id: clientId ?? owner!.id } })
    },
    onSuccess: (saved) => {
      void qc.invalidateQueries({ queryKey: ['vehicles'] })
      void qc.invalidateQueries({ queryKey: ['clients'] })
      void qc.invalidateQueries({ queryKey: ['search'] })
      toast.push(vehicle ? 'Veículo atualizado.' : 'Veículo cadastrado.')
      onSaved?.(saved)
      onClose()
    },
    onError: (err) => setError(errorMessage(err)),
  })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (!vehicle && !clientId && !owner) return setError('Escolha o cliente.')
    save.mutate()
  }

  const needsOwner = !vehicle && !clientId

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={vehicle ? 'Editar veículo' : 'Novo veículo'}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} type="button">
            Cancelar
          </Button>
          <Button type="submit" form="vehicle-form" loading={save.isPending}>
            {vehicle ? 'Salvar' : 'Cadastrar'}
          </Button>
        </>
      }
    >
      <form id="vehicle-form" onSubmit={submit} className="grid gap-4">
        {needsOwner && (
          <Field label="Cliente">
            <ClientPicker value={owner} onChange={setOwner} autoFocus />
          </Field>
        )}
        <div className="grid gap-4 sm:grid-cols-[140px_1fr]">
          <Field label="Placa" hint="Vazio = sem placa">
            <Input
              value={form.placa}
              onChange={(e) => setForm({ ...form, placa: e.target.value.toUpperCase() })}
              placeholder="ABC1D23"
              maxLength={8}
              className="tabular uppercase"
              data-autofocus={needsOwner ? undefined : ''}
            />
          </Field>
          <Field label="Modelo">
            <Input required maxLength={80} value={form.modelo} onChange={(e) => setForm({ ...form, modelo: e.target.value })} placeholder="Civic EX" />
          </Field>
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Marca">
            <Input maxLength={60} value={form.marca} onChange={(e) => setForm({ ...form, marca: e.target.value })} placeholder="Honda" />
          </Field>
          <Field label="Cor">
            <Input maxLength={40} value={form.cor} onChange={(e) => setForm({ ...form, cor: e.target.value })} placeholder="Prata" />
          </Field>
          <Field label="Ano">
            <Input inputMode="numeric" min={1950} max={ANO_MAX} type="number" value={form.ano} onChange={(e) => setForm({ ...form, ano: e.target.value })} />
          </Field>
        </div>
        <Field label="Observações (opcional)">
          <Textarea value={form.observacoes} onChange={(e) => setForm({ ...form, observacoes: e.target.value })} />
        </Field>
        {error && <p className="rounded-md border border-danger/30 bg-danger-wash px-3 py-2 text-[13px] text-danger">{error}</p>}
      </form>
    </Dialog>
  )
}

/** Transferir veículo para outro cliente (carro vendido). */
export function TransferDialog({ open, onClose, vehicle }: { open: boolean; onClose: () => void; vehicle: Vehicle | null }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [owner, setOwner] = useState<PickedClient | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setOwner(null)
      setError(null)
    }
  }, [open])

  const transfer = useMutation({
    mutationFn: () => api<Vehicle>(`/vehicles/${vehicle!.id}/transferir`, { method: 'POST', body: { client_id: owner!.id } }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['vehicles'] })
      void qc.invalidateQueries({ queryKey: ['clients'] })
      toast.push('Veículo transferido. O histórico de cada dono foi preservado.')
      onClose()
    },
    onError: (err) => setError(errorMessage(err)),
  })

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Transferir veículo"
      footer={
        <>
          <Button variant="ghost" type="button" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="button" onClick={() => transfer.mutate()} disabled={!owner} loading={transfer.isPending}>
            Transferir
          </Button>
        </>
      }
    >
      <p className="mb-4 text-[14px] text-ink-2">
        <strong>{vehicle?.descricao}</strong> passa a pertencer a outro cliente. As ordens de serviço antigas continuam na ficha do dono anterior.
      </p>
      <Field label="Novo dono">
        <ClientPicker value={owner} onChange={setOwner} exclude={vehicle?.client_id} autoFocus />
      </Field>
      {error && <p className="mt-3 rounded-md border border-danger/30 bg-danger-wash px-3 py-2 text-[13px] text-danger">{error}</p>}
    </Dialog>
  )
}
