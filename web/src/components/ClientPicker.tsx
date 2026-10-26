import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search, X } from 'lucide-react'
import { api } from '../api/client'
import type { Client, Page } from '../api/types'
import { useDebounced } from '../lib/hooks'
import { phone } from '../lib/format'
import { cx } from './ui'

export interface PickedClient {
  id: number
  nome: string
  telefone: string | null
}

/** Escolha de cliente por busca (nome ou telefone) — não depende de carregar a lista inteira. */
export function ClientPicker({
  value,
  onChange,
  exclude,
  autoFocus,
}: {
  value: PickedClient | null
  onChange: (c: PickedClient | null) => void
  exclude?: number
  autoFocus?: boolean
}) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const debounced = useDebounced(q, 200)
  const wrapRef = useRef<HTMLDivElement>(null)

  const { data, isFetching } = useQuery({
    queryKey: ['clients', 'picker', debounced],
    queryFn: () => api<Page<Client>>('/clients', { query: { q: debounced, page_size: 8 } }),
    enabled: open && debounced.trim().length >= 2,
    staleTime: 10_000,
  })

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  const items = (data?.items ?? []).filter((c) => c.id !== exclude)

  if (value) {
    return (
      <div className="flex items-center justify-between rounded-md border border-line bg-surface-2 px-3 py-2">
        <span>
          <span className="font-medium">{value.nome}</span>
          <span className="tabular ml-2 text-[13px] text-muted">{phone(value.telefone)}</span>
        </span>
        <button type="button" onClick={() => onChange(null)} className="rounded p-1 text-muted hover:bg-surface hover:text-ink" aria-label="Trocar cliente">
          <X className="h-4 w-4" />
        </button>
      </div>
    )
  }

  return (
    <div ref={wrapRef} className="relative">
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
          if (e.key === 'Enter' && items[0]) {
            e.preventDefault()
            onChange({ id: items[0].id, nome: items[0].nome, telefone: items[0].telefone })
          }
        }}
        placeholder="Nome ou telefone do cliente…"
        className="input pl-9"
        data-autofocus={autoFocus ? '' : undefined}
        aria-label="Buscar cliente"
      />
      {open && debounced.trim().length >= 2 && (
        <div className={cx('absolute left-0 right-0 top-11 z-40 overflow-hidden rounded-lg border border-line bg-surface shadow-card', isFetching && 'opacity-70')}>
          {items.length === 0 && !isFetching && <div className="px-4 py-3 text-[13px] text-muted">Nenhum cliente encontrado.</div>}
          {items.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => onChange({ id: c.id, nome: c.nome, telefone: c.telefone })}
              className="flex w-full items-center justify-between px-4 py-2.5 text-left hover:bg-surface-2"
            >
              <span className="font-medium">{c.nome}</span>
              <span className="tabular text-[12.5px] text-muted">{phone(c.telefone)}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
