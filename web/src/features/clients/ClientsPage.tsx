import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { Plus, Search } from 'lucide-react'
import { api, errorMessage } from '../../api/client'
import type { Client, Page } from '../../api/types'
import { Badge, Button, EmptyState, ErrorState, Input, PhoneLink, Spinner, Table, Td, Th, cx, rowClick } from '../../components/ui'
import { PageHeader } from '../../components/PageHeader'
import { useDebounced } from '../../lib/hooks'
import { date, plate } from '../../lib/format'
import { ClientForm } from './ClientForm'

const PAGE_SIZE = 50

export function ClientsPage() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const arquivados = params.get('arquivados') === '1'
  const page = Math.max(1, Number(params.get('page') ?? 1) || 1)
  const [formOpen, setFormOpen] = useState(false)
  const debounced = useDebounced(q, 250)

  const update = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(params)
    for (const [k, v] of Object.entries(patch)) {
      if (v === null || v === '' || v === '0' || v === '1' && k === 'page') next.delete(k)
      else next.set(k, v)
    }
    setParams(next, { replace: true })
  }

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['clients', { q: debounced, page, arquivados }],
    queryFn: () => api<Page<Client>>('/clients', { query: { q: debounced, page, page_size: PAGE_SIZE, arquivados } }),
    placeholderData: (prev) => prev,
  })

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  return (
    <>
      <PageHeader
        eyebrow="Cadastro"
        title="Clientes"
        subtitle="Ficha, veículos e histórico de cada cliente. Telefone é a chave: repetido, o sistema avisa."
        actions={
          <Button onClick={() => setFormOpen(true)}>
            <Plus className="h-4 w-4" /> Novo cliente
          </Button>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <Input value={q} onChange={(e) => update({ q: e.target.value, page: null })} placeholder="Nome ou telefone…" className="pl-9" />
        </div>
        <div className="flex rounded-md border border-line bg-surface p-0.5 text-[13px]">
          {[
            { v: false, l: 'Ativos' },
            { v: true, l: 'Arquivados' },
          ].map((o) => (
            <button
              key={String(o.v)}
              type="button"
              onClick={() => update({ arquivados: o.v ? '1' : null, page: null })}
              className={cx('rounded px-3 py-1.5 transition', arquivados === o.v ? 'bg-obsidian text-ivory' : 'text-ink-2 hover:bg-surface-2')}
            >
              {o.l}
            </button>
          ))}
        </div>
        {data && <span className="tabular text-[13px] text-muted">{data.total} cliente{data.total === 1 ? '' : 's'}</span>}
      </div>

      {isLoading ? (
        <Spinner />
      ) : isError ? (
        <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} />
      ) : !data || data.items.length === 0 ? (
        <div className="rounded-lg border border-line bg-surface">
          <EmptyState
            title={debounced ? 'Nenhum cliente encontrado' : arquivados ? 'Nenhum cliente arquivado' : 'Nenhum cliente ainda'}
            hint={debounced ? 'Tente parte do nome ou os últimos dígitos do telefone.' : 'Cadastre o primeiro cliente para começar.'}
            action={
              !debounced && !arquivados ? (
                <Button onClick={() => setFormOpen(true)}>
                  <Plus className="h-4 w-4" /> Novo cliente
                </Button>
              ) : undefined
            }
          />
        </div>
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Nome</Th>
              <Th>Telefone</Th>
              <Th>Veículos</Th>
              <Th>Cadastro</Th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((c) => {
              const ativos = c.veiculos.filter((v) => !v.arquivado_em)
              return (
                <tr key={c.id} className="cursor-pointer hover:bg-surface-2/60" onClick={rowClick(() => navigate(`/clientes/${c.id}`))}>
                  <Td>
                    <Link to={`/clientes/${c.id}`} className="font-medium text-ink hover:text-gold-deep">
                      {c.nome}
                    </Link>
                    {c.email && <div className="text-[12.5px] text-muted">{c.email}</div>}
                  </Td>
                  <Td>
                    <PhoneLink digits={c.telefone} />
                  </Td>
                  <Td>
                    <div className="flex flex-wrap gap-1.5">
                      {ativos.slice(0, 3).map((v) => (
                        <Badge key={v.id} tone="neutral" className="!tracking-[0.08em] !normal-case">
                          <span className="tabular">{plate(v.placa)}</span>&nbsp;· {v.modelo}
                        </Badge>
                      ))}
                      {ativos.length > 3 && <span className="text-[12px] text-muted">+{ativos.length - 3}</span>}
                      {ativos.length === 0 && <span className="text-[12.5px] text-muted">—</span>}
                    </div>
                  </Td>
                  <Td className="tabular whitespace-nowrap text-muted">{date(c.created_at)}</Td>
                </tr>
              )
            })}
          </tbody>
        </Table>
      )}

      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-end gap-2 text-[13px]">
          <Button variant="secondary" size="sm" disabled={page <= 1} onClick={() => update({ page: String(page - 1) })}>
            Anterior
          </Button>
          <span className="tabular text-muted">
            {page} / {totalPages}
          </span>
          <Button variant="secondary" size="sm" disabled={page >= totalPages} onClick={() => update({ page: String(page + 1) })}>
            Próxima
          </Button>
        </div>
      )}

      <ClientForm
        open={formOpen}
        onClose={() => setFormOpen(false)}
        onSaved={(c, criado) => navigate(`/clientes/${c.id}`, { state: criado ? { novoVeiculo: true } : undefined })}
      />
    </>
  )
}
