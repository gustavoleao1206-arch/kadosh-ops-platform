import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { useAuth } from '../../app/auth'
import { api, errorMessage } from '../../api/client'
import { Button, Card, Field, Input, useToast } from '../../components/ui'

export function ChangePasswordPage() {
  const { user, refresh } = useAuth()
  const navigate = useNavigate()
  const toast = useToast()
  const [atual, setAtual] = useState('')
  const [nova, setNova] = useState('')
  const [confirma, setConfirma] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const forced = !!user?.must_change_password

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (nova !== confirma) return setError('A confirmação não confere com a nova senha.')
    if (nova.length < 10) return setError('A nova senha precisa ter pelo menos 10 caracteres.')
    setBusy(true)
    setError(null)
    try {
      await api('/auth/change-password', { method: 'POST', body: { senha_atual: atual, senha_nova: nova } })
      await refresh()
      toast.push('Senha alterada. As outras sessões foram encerradas.')
      navigate('/', { replace: true })
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-full items-center justify-center bg-paper p-8">
      <Card className="w-full max-w-md">
        <h1 className="font-display text-[28px] font-semibold leading-none">{forced ? 'Defina sua nova senha' : 'Trocar senha'}</h1>
        <p className="mt-2 text-[14px] text-muted">
          {forced
            ? 'Sua senha é temporária. Escolha uma nova para continuar.'
            : 'Ao trocar, você continua conectado aqui e as outras sessões são encerradas.'}
        </p>
        <form onSubmit={submit} className="mt-6 grid gap-4">
          <Field label="Senha atual">
            <Input type="password" autoComplete="current-password" required value={atual} onChange={(e) => setAtual(e.target.value)} autoFocus />
          </Field>
          <Field label="Nova senha" hint="Mínimo de 10 caracteres.">
            <Input type="password" autoComplete="new-password" required minLength={10} value={nova} onChange={(e) => setNova(e.target.value)} />
          </Field>
          <Field label="Confirmar nova senha">
            <Input type="password" autoComplete="new-password" required value={confirma} onChange={(e) => setConfirma(e.target.value)} />
          </Field>
          {error && <p className="rounded-md border border-danger/30 bg-danger-wash px-3 py-2 text-[13px] text-danger">{error}</p>}
          <div className="flex justify-end gap-2">
            {!forced && (
              <Button type="button" variant="ghost" onClick={() => navigate(-1)}>
                Cancelar
              </Button>
            )}
            <Button type="submit" loading={busy}>
              Salvar nova senha
            </Button>
          </div>
        </form>
      </Card>
    </div>
  )
}
