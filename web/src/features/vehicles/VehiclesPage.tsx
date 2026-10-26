import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { Plus, Search } from 'lucide-react'
import { api, errorMessage } from '../../api/client'
import type { Page, Vehicle } from '../../api/types'
import { Button, EmptyState, ErrorState, Input, PhoneLink, Spinner, Table, Td, Th, cx, rowClick } from '../../components/ui'
import { PageHeader } from '../../components/PageHeader'
import { useDebounced } from '../../lib/hooks'
import { plate } from '../../lib/format'
import { VehicleForm } from './VehicleForm'

const PAGE_SIZE = 50

export function VehiclesPage() {
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
      if (v === null || v === '') next.delete(k)
      else next.set(k, v)
    }
    setParams(next, { replace: true })
  }

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['vehicles', { q: debounced, page, arquivados }],
    queryFn: () => api<Page<Vehicle>>('/vehicles', { query: { q: debounced, page, page_size: PAGE_SIZE, arquivados } }),
    placeholderData: (prev) => prev,
  })
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  return (
    <>
      <PageHeader
        eyebrow="Cadastro"
        title="Veículos"
        subtitle="Placa é opcional (carro 0 km) e única só entre veículos ativos. Carro vendido: transfira para o novo dono."
        actions={
          <Button onClick={() => setFormOpen(true)}>
            <Plus className="h-4 w-4" /> Novo veículo
          </Button>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <Input value={q} onChange={(e) => update({ q: e.target.value, page: null })} placeholder="Placa, modelo ou marca…" className="pl-9" />
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
        {data && <span className="tabular text-[13px] text-muted">{data.total} veículo{data.total === 1 ? '' : 's'}</span>}
      </div>

      {isLoading ? (
        <Spinner />
      ) : isError ? (
        <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} />
      ) : !data || data.items.length === 0 ? (
        <div className="rounded-lg border border-line bg-surface">
          <EmptyState
            title={debounced ? 'Nenhum veículo encontrado' : arquivados ? 'Nenhum veículo arquivado' : 'Nenhum veículo ainda'}
            hint={debounced ? 'Tente parte da placa ou o modelo.' : 'Cadastre o veículo a partir da ficha do cliente ou aqui.'}
          />
        </div>
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Placa</Th>
              <Th>Veículo</Th>
              <Th>Cliente</Th>
              <Th>Telefone</Th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((v) => (
              <tr key={v.id} className="cursor-pointer hover:bg-surface-2/60" onClick={rowClick(() => navigate(`/veiculos/${v.id}`))}>
                <Td className="tabular font-medium">
                  <Link to={`/veiculos/${v.id}`} className="hover:text-gold-deep">
                    {plate(v.placa)}
                  </Link>
                </Td>
                <Td>
                  {v.marca ? `${v.marca} ` : ''}
                  {v.modelo}
                  {v.cor ? <span className="text-muted"> · {v.cor}</span> : null}
                  {v.ano ? <span className="text-muted"> · {v.ano}</span> : null}
                </Td>
                <Td>
                  <Link to={`/clientes/${v.cliente.id}`} className="hover:text-gold-deep hover:underline">
                    {v.cliente.nome}
                  </Link>
                </Td>
                <Td>
                  <PhoneLink digits={v.cliente.telefone} className="text-muted" />
                </Td>
              </tr>
            ))}
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

      <VehicleForm open={formOpen} onClose={() => setFormOpen(false)} onSaved={(v) => navigate(`/veiculos/${v.id}`)} />
    </>
  )
}
