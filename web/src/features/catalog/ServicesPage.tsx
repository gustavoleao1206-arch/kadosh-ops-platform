import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Pencil, Plus, Search, Trash2 } from 'lucide-react'
import { api, errorMessage } from '../../api/client'
import type { Page, Service } from '../../api/types'
import { useAuth } from '../../app/auth'
import { Badge, Button, EmptyState, ErrorState, Input, Spinner, Table, Td, Th, cx, useToast } from '../../components/ui'
import { PageHeader } from '../../components/PageHeader'
import { useDebounced } from '../../lib/hooks'
import { duracao, money } from '../../lib/format'
import { ServiceForm } from './ServiceForm'

export function ServicesPage() {
  const qc = useQueryClient()
  const toast = useToast()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const [q, setQ] = useState('')
  const [apenasAtivos, setApenasAtivos] = useState(false)
  const [editing, setEditing] = useState<Service | null>(null)
  const [formOpen, setFormOpen] = useState(false)
  const debounced = useDebounced(q, 250)

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['services', { q: debounced, apenasAtivos }],
    queryFn: () => api<Page<Service>>('/services', { query: { q: debounced, apenas_ativos: apenasAtivos, page_size: 200 } }),
    placeholderData: (prev) => prev,
  })

  const toggle = useMutation({
    mutationFn: (s: Service) => api<Service>(`/services/${s.id}`, { method: 'PATCH', body: { ativo: !s.ativo } }),
    onSuccess: (s) => {
      void qc.invalidateQueries({ queryKey: ['services'] })
      toast.push(s.ativo ? 'Serviço reativado.' : 'Serviço desativado (some das novas OS).')
    },
    onError: (e) => toast.push(errorMessage(e), 'danger'),
  })

  const remove = useMutation({
    mutationFn: (s: Service) => api(`/services/${s.id}`, { method: 'DELETE' }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['services'] })
      toast.push('Serviço excluído.')
    },
    onError: (e) => toast.push(errorMessage(e), 'danger'),
  })

  const abrirNovo = () => {
    setEditing(null)
    setFormOpen(true)
  }

  return (
    <>
      <PageHeader
        eyebrow="Catálogo"
        title="Serviços"
        subtitle={
          isAdmin
            ? 'Nomes, preços e duração usados nas ordens de serviço. Preço alterado aqui não muda as OS já lançadas.'
            : 'Somente leitura. O administrador mantém preços e duração.'
        }
        actions={isAdmin && (
          <Button onClick={abrirNovo}>
            <Plus className="h-4 w-4" /> Novo serviço
          </Button>
        )}
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="relative w-full max-w-sm">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Nome do serviço…" className="pl-9" />
        </div>
        <div className="flex rounded-md border border-line bg-surface p-0.5 text-[13px]">
          {[
            { v: false, l: 'Todos' },
            { v: true, l: 'Só ativos' },
          ].map((o) => (
            <button
              key={String(o.v)}
              type="button"
              onClick={() => setApenasAtivos(o.v)}
              className={cx('rounded px-3 py-1.5 transition', apenasAtivos === o.v ? 'bg-obsidian text-ivory' : 'text-ink-2 hover:bg-surface-2')}
            >
              {o.l}
            </button>
          ))}
        </div>
        {data && <span className="tabular text-[13px] text-muted">{data.total} serviço{data.total === 1 ? '' : 's'}</span>}
      </div>

      {isLoading ? (
        <Spinner />
      ) : isError ? (
        <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} />
      ) : !data || data.items.length === 0 ? (
        <div className="rounded-lg border border-line bg-surface">
          <EmptyState
            title={debounced ? 'Nenhum serviço encontrado' : 'Catálogo vazio'}
            hint={debounced ? 'Tente outro termo.' : 'Cadastre os serviços que a estética oferece — eles aparecem ao montar uma OS.'}
            action={isAdmin && !debounced ? <Button onClick={abrirNovo}>Novo serviço</Button> : undefined}
          />
        </div>
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Serviço</Th>
              <Th className="text-right">Preço</Th>
              <Th className="text-right">Duração</Th>
              <Th>Situação</Th>
              {isAdmin && <Th className="text-right">Ações</Th>}
            </tr>
          </thead>
          <tbody>
            {data.items.map((s) => (
              <tr key={s.id} className={cx(!s.ativo && 'opacity-60')}>
                <Td>
                  <div className="font-medium text-ink">{s.nome}</div>
                  {s.descricao && <div className="max-w-xl text-[12.5px] text-muted">{s.descricao}</div>}
                </Td>
                <Td className="tabular whitespace-nowrap text-right font-medium">{money(s.valor_base_centavos)}</Td>
                <Td className="tabular whitespace-nowrap text-right text-muted">{duracao(s.duracao_estimada_min)}</Td>
                <Td>
                  <Badge tone={s.ativo ? 'ok' : 'neutral'}>{s.ativo ? 'Ativo' : 'Desativado'}</Badge>
                </Td>
                {isAdmin && (
                  <Td>
                    <div className="flex justify-end gap-1">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setEditing(s)
                          setFormOpen(true)
                        }}
                      >
                        <Pencil className="h-3.5 w-3.5" /> Editar
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => toggle.mutate(s)}>
                        {s.ativo ? 'Desativar' : 'Reativar'}
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        title="Só é possível se o serviço nunca foi usado"
                        onClick={() => {
                          if (confirm(`Excluir “${s.nome}”? Se já tiver sido usado em alguma OS, desative em vez de excluir.`)) remove.mutate(s)
                        }}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </Td>
                )}
              </tr>
            ))}
          </tbody>
        </Table>
      )}

      {data && data.total > data.items.length && (
        <p className="mt-2 text-[12.5px] text-muted">
          Mostrando {data.items.length} de {data.total}. Use a busca para chegar aos demais.
        </p>
      )}

      <ServiceForm open={formOpen} onClose={() => setFormOpen(false)} service={editing} />
    </>
  )
}
