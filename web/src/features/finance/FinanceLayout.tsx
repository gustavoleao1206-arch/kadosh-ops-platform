import { NavLink, Outlet } from 'react-router'
import { PageHeader } from '../../components/PageHeader'
import { cx } from '../../components/ui'

/**
 * O financeiro tem três perguntas diferentes, e cada uma merece a própria tela:
 *
 *   Caixa      — "quanto entrou HOJE?"            (fechamento do dia, o mais consultado)
 *   Extrato    — "e no período X?"                (o caixa esticado no tempo)
 *   Cobranças  — "quem ainda me deve?"            (a régua: a receber / atrasado / pago)
 *
 * Ficam sob a mesma rota porque são o mesmo assunto e o dono alterna entre elas o tempo todo;
 * separá-las em três itens do menu lateral empurraria o resto da navegação para baixo e faria
 * "financeiro" parecer três produtos.
 */
const ABAS = [
  { to: '/financeiro', label: 'Caixa do dia', fim: true },
  { to: '/financeiro/extrato', label: 'Extrato' },
  { to: '/financeiro/cobrancas', label: 'Cobranças' },
]

export function FinanceLayout() {
  return (
    <>
      <PageHeader
        eyebrow="Financeiro"
        title="Dinheiro"
        subtitle="O que entrou hoje, o que entrou no período e quem ainda deve."
      />
      <nav className="mb-6 inline-flex flex-wrap gap-1 rounded-lg border border-line bg-surface-2 p-1">
        {ABAS.map((a) => (
          <NavLink
            key={a.to}
            to={a.to}
            end={a.fim}
            className={({ isActive }) =>
              cx(
                'rounded-md px-3.5 py-1.5 text-[13.5px] transition',
                isActive ? 'bg-surface text-ink shadow-card' : 'text-muted hover:text-ink',
              )
            }
          >
            {a.label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </>
  )
}
