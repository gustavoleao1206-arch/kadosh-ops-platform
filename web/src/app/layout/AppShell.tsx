import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import {
  BarChart3,
  CalendarDays,
  Car,
  ClipboardList,
  LayoutDashboard,
  LogOut,
  Menu,
  Search,
  Settings,
  Sparkles,
  Users,
  Wallet,
  KeyRound,
} from 'lucide-react'
import { useAuth } from '../auth'
import { api } from '../../api/client'
import type { SearchResult } from '../../api/types'
import { cx, PhoneLink } from '../../components/ui'
import { useDebounced, useTelaEstreita } from '../../lib/hooks'
import { initials, plate } from '../../lib/format'

export { useDebounced }

const NAV = [
  { to: '/', label: 'Início', icon: LayoutDashboard, end: true },
  { to: '/agenda', label: 'Agenda', icon: CalendarDays },
  { to: '/os', label: 'Ordens de serviço', icon: ClipboardList },
  { to: '/clientes', label: 'Clientes', icon: Users },
  { to: '/veiculos', label: 'Veículos', icon: Car },
  { to: '/servicos', label: 'Serviços', icon: Sparkles },
  { to: '/financeiro', label: 'Financeiro', icon: Wallet },
  { to: '/relatorios', label: 'Relatórios', icon: BarChart3 },
]

const navClass = ({ isActive }: { isActive: boolean }) =>
  cx(
    'mb-0.5 flex items-center gap-3 rounded-md px-3 py-2 text-[13.5px] transition',
    isActive ? 'bg-white/[0.07] text-ivory' : 'text-ivory/60 hover:bg-white/[0.05] hover:text-ivory',
  )

export function AppShell() {
  const { user, logout } = useAuth()
  const [menuAberto, setMenuAberto] = useState(false)
  const { pathname } = useLocation()

  // Trocar de tela fecha a gaveta. Sem isto o menu fica aberto por cima da página que ele acabou
  // de abrir — o erro clássico de menu móvel, e o usuário acha que o toque não funcionou.
  useEffect(() => setMenuAberto(false), [pathname])

  // Com a gaveta aberta o corpo não rola: no iPhone, rolar "através" de um overlay leva a página de
  // trás junto e o menu parece deslizar sozinho.
  useEffect(() => {
    document.body.style.overflow = menuAberto ? 'hidden' : ''
    return () => {
      document.body.style.overflow = ''
    }
  }, [menuAberto])

  const barraLateral = (
    <>
      <div className="px-6 pb-5 pt-7">
        <div className="font-display text-[22px] tracking-[0.14em]">
          KAD<span className="text-champagne">O</span>SH
        </div>
        <div className="mt-1 font-label text-[9px] tracking-[0.6em] text-champagne">DETAIL</div>
      </div>
      <nav className="flex-1 px-3">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className={navClass}>
            {({ isActive }) => (
              <>
                <Icon className={cx('h-4 w-4', isActive ? 'text-champagne' : 'text-ivory/50')} />
                {label}
              </>
            )}
          </NavLink>
        ))}
        {user?.role === 'admin' && (
          <>
            <div className="label-dim mt-5 mb-1 px-3 !text-ivory/35">Administração</div>
            <NavLink to="/configuracoes/usuarios" className={navClass}>
              <Settings className="h-4 w-4 text-ivory/50" /> Usuários
            </NavLink>
          </>
        )}
      </nav>
      <div className="border-t border-white/10 px-4 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-full bg-champagne/15 font-label text-[12px] tracking-wider text-champagne">
            {user ? initials(user.nome) : '·'}
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[13px] text-ivory">{user?.nome}</div>
            <div className="label-dim !text-ivory/40 !tracking-[0.18em]">{user?.role === 'admin' ? 'Administrador' : 'Sócio'}</div>
          </div>
        </div>
        <div className="mt-3 flex gap-1">
          <NavLink to="/trocar-senha" className="flex flex-1 items-center justify-center gap-1.5 rounded px-2 py-2 text-[12px] text-ivory/60 hover:bg-white/[0.05] hover:text-ivory">
            <KeyRound className="h-3.5 w-3.5" /> Senha
          </NavLink>
          <button type="button" onClick={() => void logout()} className="flex flex-1 items-center justify-center gap-1.5 rounded px-2 py-2 text-[12px] text-ivory/60 hover:bg-white/[0.05] hover:text-ivory">
            <LogOut className="h-3.5 w-3.5" /> Sair
          </button>
        </div>
      </div>
    </>
  )

  return (
    <div className="flex min-h-full">
      {/* Computador: a lateral é parte do layout. */}
      <aside className="sticky top-0 hidden h-screen w-[232px] shrink-0 flex-col overflow-y-auto bg-obsidian text-ivory lg:flex">
        {barraLateral}
      </aside>

      {/* Celular: a mesma lateral vira gaveta. É a MESMA árvore de navegação, não uma segunda —
          duas listas de menu divergem no dia em que alguém acrescenta uma tela. */}
      {menuAberto && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            aria-label="Fechar menu"
            onClick={() => setMenuAberto(false)}
            className="absolute inset-0 bg-obsidian/60"
          />
          <aside className="safe-top safe-bottom absolute inset-y-0 left-0 flex w-[264px] max-w-[82vw] flex-col overflow-y-auto bg-obsidian text-ivory shadow-2xl">
            {barraLateral}
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="safe-top sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-line bg-surface px-4 lg:px-6">
          <button
            type="button"
            onClick={() => setMenuAberto(true)}
            aria-label="Abrir menu"
            aria-expanded={menuAberto}
            // 44px é o alvo de toque mínimo do iOS; abaixo disso erra-se o botão com o polegar
            className="-ml-1 flex h-11 w-11 shrink-0 items-center justify-center rounded-md text-ink-2 hover:bg-surface-2 lg:hidden"
          >
            <Menu className="h-5 w-5" />
          </button>
          <GlobalSearch />
        </header>
        {/* padding menor no celular: 32px de cada lado num iPhone é um quinto da tela */}
        <main className="flex-1 px-4 py-5 sm:px-6 lg:px-8 lg:py-7">
          <Outlet />
          {/* respiro sob a barra de gestos do iPhone; 0 em qualquer aparelho sem recorte.
              Vai num elemento próprio para não disputar `padding-bottom` com o `py-5` acima. */}
          <div className="safe-bottom" aria-hidden />
        </main>
      </div>
    </div>
  )
}

/** Busca única: placa, telefone ou nome. Enter abre o primeiro resultado; Esc fecha. */
function GlobalSearch() {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const navigate = useNavigate()
  const wrapRef = useRef<HTMLDivElement>(null)
  const debounced = useDebounced(q, 250)
  const active = debounced.trim().length >= 2
  const curto = useTelaEstreita()

  const { data, isFetching } = useQuery({
    queryKey: ['search', debounced],
    queryFn: () => api<SearchResult>('/search', { query: { q: debounced } }),
    enabled: active,
    staleTime: 10_000,
    placeholderData: keepPreviousData,
  })

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  const go = (path: string) => {
    setOpen(false)
    setQ('')
    navigate(path)
  }

  const first = data?.veiculos[0] ? `/veiculos/${data.veiculos[0].id}` : data?.clientes[0] ? `/clientes/${data.clientes[0].id}` : null
  const hasResults = !!data && (data.veiculos.length > 0 || data.clientes.length > 0)
  const encoded = encodeURIComponent(q.trim())

  return (
    <div
      ref={wrapRef}
      className="relative w-full max-w-xl"
      onBlur={(e) => {
        if (e.relatedTarget && !wrapRef.current?.contains(e.relatedTarget as Node)) setOpen(false)
      }}
    >
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
      <input
        value={q}
        onChange={(e) => {
          setQ(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') setOpen(false)
          if (e.key === 'Enter' && first) go(first)
        }}
        placeholder={curto ? 'Buscar placa, nome…' : 'Buscar por placa, telefone ou nome…  (Enter abre o primeiro)'}
        className="input h-9 pl-9"
        aria-label="Buscar"
        role="combobox"
        aria-expanded={open && active}
      />
      {open && active && (
        <div className={cx('absolute left-0 right-0 top-11 z-40 overflow-hidden rounded-lg border border-line bg-surface shadow-card', isFetching && 'opacity-70')}>
          {!data && isFetching && <div className="px-4 py-3 text-[13px] text-muted">Buscando…</div>}
          {data && !hasResults && (
            <div className="px-4 py-3 text-[13px] text-muted">
              Nada encontrado entre os ativos para "{debounced}".{' '}
              <Link to={`/clientes?q=${encoded}&arquivados=1`} onClick={() => setOpen(false)} className="text-gold-deep hover:underline">
                Procurar nos arquivados
              </Link>
            </div>
          )}
          {data?.veiculos.slice(0, 6).map((v) => (
            <button key={`v${v.id}`} type="button" onClick={() => go(`/veiculos/${v.id}`)} className="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-surface-2">
              <Car className="h-4 w-4 shrink-0 text-gold" />
              <span className="flex-1 truncate">
                <span className="tabular font-medium">{plate(v.placa)}</span>
                <span className="text-muted">
                  {' '}
                  · {v.marca ? `${v.marca} ` : ''}
                  {v.modelo}
                  {v.cor ? ` ${v.cor}` : ''}
                </span>
              </span>
              <span className="truncate text-[12.5px] text-muted">{v.cliente.nome}</span>
            </button>
          ))}
          {data?.clientes.slice(0, 5).map((c) => (
            <button key={`c${c.id}`} type="button" onClick={() => go(`/clientes/${c.id}`)} className="flex w-full items-center gap-3 px-4 py-2.5 text-left hover:bg-surface-2">
              <Users className="h-4 w-4 shrink-0 text-gold" />
              <span className="flex-1 truncate font-medium">{c.nome}</span>
              <PhoneLink digits={c.telefone} className="text-[12.5px] text-muted" />
            </button>
          ))}
          {hasResults && (
            <div className="flex gap-4 border-t border-line bg-paper px-4 py-2 text-[12.5px]">
              <Link to={`/veiculos?q=${encoded}`} onClick={() => setOpen(false)} className="text-gold-deep hover:underline">
                Ver todos os veículos
              </Link>
              <Link to={`/clientes?q=${encoded}`} onClick={() => setOpen(false)} className="text-gold-deep hover:underline">
                Ver todos os clientes
              </Link>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
