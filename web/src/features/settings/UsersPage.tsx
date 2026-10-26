import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { KeyRound, LogOut, Plus, UserCheck, UserX } from 'lucide-react'
import { api, errorMessage } from '../../api/client'
import type { Page, Role, User } from '../../api/types'
import { useAuth } from '../../app/auth'
import { Badge, Button, Dialog, ErrorState, Field, Input, Select, Spinner, Table, Td, Th, useToast } from '../../components/ui'
import { PageHeader } from '../../components/PageHeader'
import { date } from '../../lib/format'

export function UsersPage() {
  const qc = useQueryClient()
  const toast = useToast()
  const { user: me } = useAuth()
  const [createOpen, setCreateOpen] = useState(false)
  const [resetFor, setResetFor] = useState<User | null>(null)

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['users'],
    queryFn: () => api<Page<User>>('/users', { query: { page_size: 200 } }),
  })

  const invalidate = () => void qc.invalidateQueries({ queryKey: ['users'] })

  const patch = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<Pick<User, 'role' | 'is_active'>> }) => api<User>(`/users/${id}`, { method: 'PATCH', body }),
    onSuccess: () => {
      invalidate()
      toast.push('Usuário atualizado.')
    },
    onError: (e) => toast.push(errorMessage(e), 'danger'),
  })

  const logoutAll = useMutation({
    mutationFn: (id: number) => api<{ detail: string }>(`/users/${id}/logout-all`, { method: 'POST' }),
    onSuccess: (r) => toast.push(r.detail),
    onError: (e) => toast.push(errorMessage(e), 'danger'),
  })

  return (
    <>
      <PageHeader
        eyebrow="Administração"
        title="Usuários"
        subtitle="Quem acessa o painel e o aplicativo. Sócio (staff) opera tudo; administrador também gerencia catálogo, usuários e exclusões."
        actions={
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" /> Novo usuário
          </Button>
        }
      />

      {isLoading ? (
        <Spinner />
      ) : isError || !data ? (
        <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} />
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Nome</Th>
              <Th>E-mail</Th>
              <Th>Papel</Th>
              <Th>Situação</Th>
              <Th>Desde</Th>
              <Th className="text-right">Ações</Th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((u) => {
              const isMe = u.id === me?.id
              return (
                <tr key={u.id}>
                  <Td className="font-medium">
                    {u.nome} {isMe && <span className="text-[12px] text-muted">(você)</span>}
                  </Td>
                  <Td className="text-muted">{u.email}</Td>
                  <Td>
                    <Select
                      value={u.role}
                      disabled={isMe || patch.isPending}
                      onChange={(e) => patch.mutate({ id: u.id, body: { role: e.target.value as Role } })}
                      className="!w-auto !py-1 text-[13px]"
                      aria-label={`Papel de ${u.nome}`}
                    >
                      <option value="admin">Administrador</option>
                      <option value="staff">Sócio / staff</option>
                    </Select>
                  </Td>
                  <Td>
                    <div className="flex flex-wrap gap-1.5">
                      <Badge tone={u.is_active ? 'ok' : 'danger'}>{u.is_active ? 'Ativo' : 'Desativado'}</Badge>
                      {u.must_change_password && <Badge tone="warn">Senha temporária</Badge>}
                    </div>
                  </Td>
                  <Td className="tabular text-muted">{date(u.created_at)}</Td>
                  <Td>
                    <div className="flex justify-end gap-1">
                      <Button size="sm" variant="ghost" title="Definir senha temporária" onClick={() => setResetFor(u)}>
                        <KeyRound className="h-3.5 w-3.5" /> Senha
                      </Button>
                      {/* a própria sessão se encerra por "Sair" na barra lateral; aqui só terceiros */}
                      {!isMe && (
                        <Button
                          size="sm"
                          variant="ghost"
                          title="Sair de todos os aparelhos"
                          onClick={() => {
                            if (confirm(`Encerrar todas as sessões de ${u.nome}? Ele precisará entrar de novo no celular e no painel.`)) logoutAll.mutate(u.id)
                          }}
                        >
                          <LogOut className="h-3.5 w-3.5" /> Sessões
                        </Button>
                      )}
                      {!isMe &&
                        (u.is_active ? (
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => {
                              if (confirm(`Desativar ${u.nome}? Ele perde o acesso imediatamente.`)) patch.mutate({ id: u.id, body: { is_active: false } })
                            }}
                          >
                            <UserX className="h-3.5 w-3.5" /> Desativar
                          </Button>
                        ) : (
                          <Button size="sm" variant="ghost" onClick={() => patch.mutate({ id: u.id, body: { is_active: true } })}>
                            <UserCheck className="h-3.5 w-3.5" /> Reativar
                          </Button>
                        ))}
                    </div>
                  </Td>
                </tr>
              )
            })}
          </tbody>
        </Table>
      )}

      <CreateUserDialog open={createOpen} onClose={() => setCreateOpen(false)} />
      <ResetPasswordDialog user={resetFor} onClose={() => setResetFor(null)} />
    </>
  )
}

function CreateUserDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [form, setForm] = useState({ nome: '', email: '', senha: '', role: 'staff' as Role })
  const [error, setError] = useState<string | null>(null)

  const create = useMutation({
    mutationFn: () => api<User>('/users', { method: 'POST', body: form }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['users'] })
      toast.push('Usuário criado.')
      setForm({ nome: '', email: '', senha: '', role: 'staff' })
      onClose()
    },
    onError: (e) => setError(errorMessage(e)),
  })

  const submit = (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    create.mutate()
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Novo usuário"
      footer={
        <>
          <Button variant="ghost" type="button" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="submit" form="user-form" loading={create.isPending}>
            Criar
          </Button>
        </>
      }
    >
      <form id="user-form" onSubmit={submit} className="grid gap-4">
        <Field label="Nome">
          <Input required minLength={2} value={form.nome} onChange={(e) => setForm({ ...form, nome: e.target.value })} data-autofocus />
        </Field>
        <Field label="E-mail">
          <Input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Senha inicial" hint="Mínimo de 10 caracteres.">
            <Input type="password" required minLength={10} value={form.senha} onChange={(e) => setForm({ ...form, senha: e.target.value })} />
          </Field>
          <Field label="Papel">
            <Select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
              <option value="staff">Sócio / staff</option>
              <option value="admin">Administrador</option>
            </Select>
          </Field>
        </div>
        {error && <p className="rounded-md border border-danger/30 bg-danger-wash px-3 py-2 text-[13px] text-danger">{error}</p>}
      </form>
    </Dialog>
  )
}

function ResetPasswordDialog({ user, onClose }: { user: User | null; onClose: () => void }) {
  const toast = useToast()
  const qc = useQueryClient()
  const [senha, setSenha] = useState('')
  const [error, setError] = useState<string | null>(null)

  const reset = useMutation({
    mutationFn: () => api<{ detail: string }>(`/users/${user!.id}/reset-password`, { method: 'POST', body: { senha_nova: senha } }),
    onSuccess: (r) => {
      void qc.invalidateQueries({ queryKey: ['users'] })
      toast.push(r.detail)
      setSenha('')
      onClose()
    },
    onError: (e) => setError(errorMessage(e)),
  })

  return (
    <Dialog
      open={!!user}
      onClose={onClose}
      title={`Senha temporária — ${user?.nome ?? ''}`}
      footer={
        <>
          <Button variant="ghost" type="button" onClick={onClose}>
            Cancelar
          </Button>
          <Button type="button" onClick={() => reset.mutate()} disabled={senha.length < 10} loading={reset.isPending}>
            Definir
          </Button>
        </>
      }
    >
      <p className="mb-4 text-[14px] text-ink-2">
        O usuário será obrigado a trocar esta senha no próximo login e todas as sessões dele serão encerradas.
      </p>
      <Field label="Senha temporária" hint="Mínimo de 10 caracteres. Passe ao usuário por um canal seguro.">
        <Input type="text" autoComplete="off" value={senha} onChange={(e) => setSenha(e.target.value)} data-autofocus />
      </Field>
      {error && <p className="mt-3 rounded-md border border-danger/30 bg-danger-wash px-3 py-2 text-[13px] text-danger">{error}</p>}
    </Dialog>
  )
}
