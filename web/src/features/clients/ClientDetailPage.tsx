import { useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive, ArchiveRestore, Car, MessageCircle, Pencil, Plus, Trash2 } from 'lucide-react'
import { api, errorMessage, isNotFound } from '../../api/client'
import type { Client, ClientDetail, Vehicle } from '../../api/types'
import { useAuth } from '../../app/auth'
import { Badge, Button, Card, EmptyState, ErrorState, PhoneLink, Spinner, Table, Td, Th, buttonClasses, useToast } from '../../components/ui'
import { PrecosDoCliente } from './PrecosDoCliente'
import { PageHeader } from '../../components/PageHeader'
import { date, dateTime, money, plate, whatsappUrl } from '../../lib/format'
import { ClientForm } from './ClientForm'
import { VehicleForm } from '../vehicles/VehicleForm'

export function ClientDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const location = useLocation()
  const qc = useQueryClient()
  const toast = useToast()
  const { user } = useAuth()
  const [editOpen, setEditOpen] = useState(false)
  // vindo do cadastro: já abre o diálogo do veículo (cliente + carro é o fluxo do balcão)
  const [vehicleOpen, setVehicleOpen] = useState(!!(location.state as { novoVeiculo?: boolean } | null)?.novoVeiculo)

  const { data: c, isLoading, error, refetch } = useQuery({
    queryKey: ['clients', Number(id)],
    queryFn: () => api<ClientDetail>(`/clients/${id}`),
  })

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['clients'] })
    void qc.invalidateQueries({ queryKey: ['vehicles'] })
    void qc.invalidateQueries({ queryKey: ['search'] })
  }

  const archive = useMutation({
    mutationFn: (restore: boolean) => api<Client>(`/clients/${id}/${restore ? 'desarquivar' : 'arquivar'}`, { method: 'POST' }),
    onSuccess: (_, restore) => {
      invalidate()
      toast.push(restore ? 'Cliente reativado (e os veículos arquivados junto).' : 'Cliente arquivado (veículos também).')
    },
    onError: (e) => toast.push(errorMessage(e), 'danger'),
  })

  const remove = useMutation({
    mutationFn: () => api(`/clients/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      invalidate()
      toast.push('Cliente excluído.')
      navigate('/clientes', { replace: true })
    },
    onError: (e) => toast.push(errorMessage(e), 'danger'),
  })

  const closeVehicleDialog = () => {
    setVehicleOpen(false)
    if ((location.state as { novoVeiculo?: boolean } | null)?.novoVeiculo) navigate('.', { replace: true, state: null })
  }

  if (isLoading) return <Spinner />
  if (error && isNotFound(error)) {
    return <EmptyState title="Cliente não encontrado" action={<Link to="/clientes" className="text-gold-deep underline">Voltar para clientes</Link>} />
  }
  if (error || !c) return <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} />

  const ativos = c.veiculos.filter((v) => !v.arquivado_em)
  const arquivados = c.veiculos.filter((v) => v.arquivado_em)
  const arquivado = !!c.arquivado_em

  return (
    <>
      <PageHeader
        eyebrow={
          <span>
            <Link to="/clientes" className="hover:underline">
              Clientes
            </Link>{' '}
            / Ficha
          </span>
        }
        title={c.nome}
        subtitle={arquivado ? `Arquivado em ${dateTime(c.arquivado_em)}.` : undefined}
        actions={
          <>
            {c.telefone && (
              <a href={whatsappUrl(c.telefone)} target="_blank" rel="noreferrer" className={buttonClasses('secondary')}>
                <MessageCircle className="h-4 w-4" /> WhatsApp
              </a>
            )}
            <Button variant="secondary" onClick={() => setEditOpen(true)} disabled={arquivado}>
              <Pencil className="h-4 w-4" /> Editar
            </Button>
            {arquivado ? (
              <Button variant="secondary" onClick={() => archive.mutate(true)} loading={archive.isPending}>
                <ArchiveRestore className="h-4 w-4" /> Reativar
              </Button>
            ) : (
              <Button
                variant="ghost"
                onClick={() => {
                  if (confirm(`Arquivar ${c.nome}? Ele e seus veículos somem das listas; o histórico continua acessível.`)) archive.mutate(false)
                }}
                loading={archive.isPending}
              >
                <Archive className="h-4 w-4" /> Arquivar
              </Button>
            )}
            {user?.role === 'admin' && c.historico.length === 0 && c.veiculos.length === 0 && (
              <Button
                variant="danger"
                onClick={() => {
                  if (confirm(`Excluir ${c.nome}? Só é possível porque não há veículos nem histórico.`)) remove.mutate()
                }}
                loading={remove.isPending}
              >
                <Trash2 className="h-4 w-4" /> Excluir
              </Button>
            )}
          </>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[1fr_1.4fr]">
        <div className="grid gap-4">
          <Card title="Dados">
            <dl className="grid grid-cols-[110px_1fr] gap-y-2.5 text-[14px]">
              <dt className="label-dim self-center">Telefone</dt>
              <dd>
                <PhoneLink digits={c.telefone} />
              </dd>
              <dt className="label-dim self-center">E-mail</dt>
              <dd>{c.email || <span className="text-muted">—</span>}</dd>
              <dt className="label-dim self-center">Cliente desde</dt>
              <dd className="tabular">{date(c.created_at)}</dd>
              <dt className="label-dim self-start pt-0.5">Observações</dt>
              <dd className="whitespace-pre-wrap text-ink-2">{c.observacoes || <span className="text-muted">—</span>}</dd>
            </dl>
          </Card>

          <Card title="Resumo">
            <div className="grid grid-cols-3 gap-3">
              <Stat label="Atendimentos" value={String(c.stats.atendimentos)} />
              <Stat label="Total gasto" value={money(c.stats.total_gasto_centavos)} />
              <Stat label="Último" value={c.stats.ultimo_atendimento ? date(c.stats.ultimo_atendimento) : '—'} />
            </div>
          </Card>
        </div>

        <div className="grid gap-4">
          <Card
            title="Veículos"
            actions={
              !arquivado && (
                <Button size="sm" variant="secondary" onClick={() => setVehicleOpen(true)}>
                  <Plus className="h-4 w-4" /> Adicionar
                </Button>
              )
            }
          >
            {ativos.length === 0 && arquivados.length === 0 ? (
              <p className="text-[13.5px] text-muted">Nenhum veículo cadastrado.</p>
            ) : (
              <ul className="divide-y divide-line">
                {ativos.map((v) => (
                  <VehicleRow key={v.id} v={v} />
                ))}
                {arquivados.map((v) => (
                  <VehicleRow key={v.id} v={v} archived />
                ))}
              </ul>
            )}
          </Card>

          <PrecosDoCliente clientId={c.id} />

          <Card title="Histórico de serviços">
            {c.historico.length === 0 ? (
              <p className="text-[13.5px] text-muted">Nenhuma ordem de serviço ainda. (As OS chegam na fase 4.)</p>
            ) : (
              <Table className="!shadow-none">
                <thead>
                  <tr>
                    <Th>OS</Th>
                    <Th>Veículo</Th>
                    <Th>Status</Th>
                    <Th>Entrada</Th>
                    <Th className="text-right">Valor</Th>
                  </tr>
                </thead>
                <tbody>
                  {c.historico.map((h) => (
                    <tr key={h.id}>
                      <Td className="tabular">{h.numero ? `nº ${String(h.numero).padStart(3, '0')}` : `#${h.id}`}</Td>
                      <Td>{h.veiculo ?? '—'}</Td>
                      <Td>
                        <Badge tone={h.status === 'concluido' ? 'ok' : h.status === 'cancelado' ? 'danger' : 'gold'}>{h.status_label}</Badge>
                      </Td>
                      <Td className="tabular">{dateTime(h.entrada ?? h.scheduled_at)}</Td>
                      <Td className="tabular text-right">{money(h.valor_total_centavos)}</Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Card>
        </div>
      </div>

      <ClientForm open={editOpen} onClose={() => setEditOpen(false)} client={c} />
      <VehicleForm open={vehicleOpen} onClose={closeVehicleDialog} clientId={c.id} onSaved={(v: Vehicle) => navigate(`/veiculos/${v.id}`)} />
    </>
  )
}

function VehicleRow({ v, archived = false }: { v: ClientDetail['veiculos'][number]; archived?: boolean }) {
  return (
    <li>
      <Link to={`/veiculos/${v.id}`} className={`flex items-center gap-3 py-2.5 hover:text-gold-deep ${archived ? 'opacity-60' : ''}`}>
        <Car className="h-4 w-4 text-gold" />
        <span className="tabular w-[92px] font-medium">{plate(v.placa)}</span>
        <span className="flex-1 truncate">
          {v.marca ? `${v.marca} ` : ''}
          {v.modelo}
          {v.cor ? ` · ${v.cor}` : ''}
          {v.ano ? ` · ${v.ano}` : ''}
        </span>
        {archived && <Badge tone="neutral">Arquivado</Badge>}
      </Link>
    </li>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="label-dim">{label}</div>
      <div className="tabular mt-1 font-display text-[24px] font-semibold leading-none">{value}</div>
    </div>
  )
}
