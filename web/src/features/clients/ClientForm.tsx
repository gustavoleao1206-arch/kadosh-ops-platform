import { useEffect, useState, type FormEvent } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, ApiError, errorMessage } from '../../api/client'
import type { Client, ClientInput } from '../../api/types'
import { Button, Dialog, Field, Input, Textarea, useToast } from '../../components/ui'
import { phone } from '../../lib/format'

interface Props {
  open: boolean
  onClose: () => void
  client?: Client | null
  /** criado=true quando é um cadastro novo (a lista aproveita para já abrir o veículo) */
  onSaved?: (c: Client, criado: boolean) => void
}

export function ClientForm({ open, onClose, client, onSaved }: Props) {
  const qc = useQueryClient()
  const toast = useToast()
  const [form, setForm] = useState<ClientInput>({ nome: '', telefone: '', email: '', observacoes: '' })
  const [error, setError] = useState<string | null>(null)
  const [duplicate, setDuplicate] = useState<Client | null>(null)
  const clientId = client?.id

  // Preenche ao abrir e quando muda o registro — não a cada refetch da ficha (não sobrescreve o que está sendo digitado).
  useEffect(() => {
    if (!open) return
    setForm({
      nome: client?.nome ?? '',
      telefone: client?.telefone ?? '',
      email: client?.email ?? '',
      observacoes: client?.observacoes ?? '',
    })
    setError(null)
    setDuplicate(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, clientId])

  const save = useMutation({
    mutationFn: (force: boolean) => {
      const body: ClientInput = {
        nome: form.nome.trim(),
        telefone: form.telefone?.trim() || null,
        email: form.email?.trim() || null,
        observacoes: form.observacoes?.trim() || null,
      }
      const query = { force: force || undefined }
      return client
        ? api<Client>(`/clients/${client.id}`, { method: 'PATCH', body, query })
        : api<Client>('/clients', { method: 'POST', body, query })
    },
    onSuccess: (saved) => {
      void qc.invalidateQueries({ queryKey: ['clients'] })
      void qc.invalidateQueries({ queryKey: ['search'] })
      toast.push(client ? 'Cliente atualizado.' : 'Cliente cadastrado.')
      onSaved?.(saved, !client)
      onClose()
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 409 && err.data && typeof err.data === 'object' && 'existente' in err.data) {
        setDuplicate((err.data as { existente: Client }).existente)
        setError(null)
        return
      }
      setError(errorMessage(err))
    },
  })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    save.mutate(false)
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={client ? 'Editar cliente' : 'Novo cliente'}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} type="button">
            Cancelar
          </Button>
          <Button type="submit" form="client-form" loading={save.isPending}>
            {client ? 'Salvar' : 'Cadastrar'}
          </Button>
        </>
      }
    >
      <form id="client-form" onSubmit={submit} className="grid gap-4">
        <Field label="Nome">
          <Input required minLength={2} maxLength={120} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} data-autofocus />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Telefone" hint="Com DDD. Usado na busca e no WhatsApp.">
            <Input inputMode="tel" placeholder="(82) 99999-9999" value={form.telefone ?? ''} onChange={(e) => setForm({ ...form, telefone: e.target.value })} />
          </Field>
          <Field label="E-mail (opcional)">
            <Input type="email" value={form.email ?? ''} onChange={(e) => setForm({ ...form, email: e.target.value })} />
          </Field>
        </div>
        <Field label="Observações (opcional)">
          <Textarea value={form.observacoes ?? ''} onChange={(e) => setForm({ ...form, observacoes: e.target.value })} />
        </Field>

        {duplicate && (
          <div className="rounded-md border border-warn/30 bg-warn-wash px-4 py-3 text-[13.5px] text-ink">
            <p>
              Já existe um cliente com este telefone: <strong>{duplicate.nome}</strong> ({phone(duplicate.telefone)})
              {duplicate.arquivado_em ? ' — arquivado' : ''}.
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              {!client && (
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    onSaved?.(duplicate, false)
                    onClose()
                  }}
                >
                  Usar este cliente
                </Button>
              )}
              <Button type="button" size="sm" variant="ghost" onClick={() => save.mutate(true)} loading={save.isPending}>
                {client ? 'Salvar mesmo assim (mesmo número)' : 'Cadastrar mesmo assim (mesmo número)'}
              </Button>
            </div>
          </div>
        )}
        {error && <p className="rounded-md border border-danger/30 bg-danger-wash px-3 py-2 text-[13px] text-danger">{error}</p>}
      </form>
    </Dialog>
  )
}
