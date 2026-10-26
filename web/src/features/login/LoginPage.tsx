import { useState, type FormEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router'
import { useAuth } from '../../app/auth'
import { errorMessage } from '../../api/client'
import { Button, Field, Input } from '../../components/ui'

export function LoginPage() {
  const { user, loading, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [senha, setSenha] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  if (!loading && user) return <Navigate to={user.must_change_password ? '/trocar-senha' : '/'} replace />

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const u = await login(email.trim(), senha)
      const from = (location.state as { from?: string } | null)?.from
      navigate(u.must_change_password ? '/trocar-senha' : from || '/', { replace: true })
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid min-h-full lg:grid-cols-[1.1fr_1fr]">
      <section className="hidden flex-col justify-between bg-obsidian p-12 text-ivory lg:flex">
        <div>
          <div className="font-display text-[30px] tracking-[0.14em]">
            KAD<span className="text-champagne">O</span>SH
          </div>
          <div className="mt-1 font-label text-[10px] tracking-[0.6em] text-champagne">DETAIL</div>
        </div>
        <div>
          <p className="font-display text-[44px] leading-[1.05] text-ivory text-balance">Painel de operação da estética.</p>
          <p className="mt-4 max-w-md text-[15px] text-ivory/60">
            Clientes, veículos, agenda, ordens de serviço e financeiro — o mesmo sistema que o aplicativo do pátio, visto do
            computador.
          </p>
        </div>
        <div className="label-dim !text-ivory/35">Sistema interno · acesso restrito</div>
      </section>

      <section className="flex items-center justify-center p-8">
        <form onSubmit={submit} className="w-full max-w-sm">
          <div className="mb-8 lg:hidden">
            <div className="font-display text-[26px] tracking-[0.14em]">
              KAD<span className="text-gold">O</span>SH
            </div>
          </div>
          <h1 className="font-display text-[32px] font-semibold leading-none">Entrar</h1>
          <p className="mt-2 text-[14px] text-muted">Use o e-mail e a senha cadastrados no sistema.</p>

          <div className="mt-7 grid gap-4">
            <Field label="E-mail">
              <Input type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} autoFocus />
            </Field>
            <Field label="Senha">
              <Input type="password" autoComplete="current-password" required value={senha} onChange={(e) => setSenha(e.target.value)} />
            </Field>
            {error && <p className="rounded-md border border-danger/30 bg-danger-wash px-3 py-2 text-[13px] text-danger">{error}</p>}
            <Button type="submit" loading={busy} className="mt-2 w-full">
              Entrar
            </Button>
          </div>
          <p className="mt-6 text-[12.5px] text-muted">Esqueceu a senha? Peça ao administrador para redefini-la.</p>
        </form>
      </section>
    </div>
  )
}
