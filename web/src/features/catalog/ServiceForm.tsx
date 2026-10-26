import { useEffect, useState, type FormEvent } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, errorMessage } from '../../api/client'
import type { Service } from '../../api/types'
import { Button, Dialog, Field, Input, Textarea, useToast } from '../../components/ui'
import { MoneyInput } from '../../components/MoneyInput'

export function ServiceForm({ open, onClose, service }: { open: boolean; onClose: () => void; service?: Service | null }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [nome, setNome] = useState('')
  const [descricao, setDescricao] = useState('')
  const [valor, setValor] = useState<number | null>(null)
  const [horas, setHoras] = useState('1')
  const [minutos, setMinutos] = useState('0')
  const [error, setError] = useState<string | null>(null)
  const serviceId = service?.id

  useEffect(() => {
    if (!open) return
    setNome(service?.nome ?? '')
    setDescricao(service?.descricao ?? '')
    setValor(service?.valor_base_centavos ?? null)
    const min = service?.duracao_estimada_min ?? 60
    setHoras(String(Math.floor(min / 60)))
    setMinutos(String(min % 60))
    setError(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, serviceId])

  const save = useMutation({
    mutationFn: () => {
      const body = {
        nome: nome.trim(),
        descricao: descricao.trim() || null,
        valor_base_centavos: valor ?? 0,
        duracao_estimada_min: Number(horas || 0) * 60 + Number(minutos || 0),
      }
      return service
        ? api<Service>(`/services/${service.id}`, { method: 'PATCH', body })
        : api<Service>('/services', { method: 'POST', body })
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['services'] })
      toast.push(service ? 'Serviço atualizado.' : 'Serviço cadastrado.')
      onClose()
    },
    onError: (e) => setError(errorMessage(e)),
  })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    save.mutate()
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={service ? 'Editar serviço' : 'Novo serviço'}
      footer={
        <>
          <Button variant="ghost" type="button" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" form="service-form" loading={save.isPending}>
            {service ? 'Salvar' : 'Cadastrar'}
          </Button>
        </>
      }
    >
      <form id="service-form" onSubmit={submit} className="grid gap-4">
        <Field label="Nome">
          <Input required minLength={2} maxLength={120} value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Lavagem Premium — Hatch/Sedan" data-autofocus />
        </Field>
        <Field label="Descrição (opcional)" hint="Aparece no catálogo e ajuda a lembrar o que está incluso.">
          <Textarea value={descricao} onChange={(e) => setDescricao(e.target.value)} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-[1fr_auto_auto]">
          <Field label="Preço sugerido">
            <MoneyInput value={valor} onChange={setValor} />
          </Field>
          <Field label="Duração (h)">
            <Input type="number" min={0} max={168} value={horas} onChange={(e) => setHoras(e.target.value)} className="tabular w-24 text-right" />
          </Field>
          <Field label="e (min)">
            <Input type="number" min={0} max={59} step={5} value={minutos} onChange={(e) => setMinutos(e.target.value)} className="tabular w-24 text-right" />
          </Field>
        </div>
        <p className="text-[12.5px] text-muted">A duração alimenta a previsão de conclusão da OS.</p>
        {error && <p className="rounded-md border border-danger/30 bg-danger-wash px-3 py-2 text-[13px] text-danger">{error}</p>}
      </form>
    </Dialog>
  )
}
