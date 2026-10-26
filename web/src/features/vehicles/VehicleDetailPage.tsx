import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Archive, ArchiveRestore, ArrowRightLeft, Pencil, Trash2 } from 'lucide-react'
import { api, errorMessage, isNotFound } from '../../api/client'
import type { Vehicle, VehicleDetail } from '../../api/types'
import { useAuth } from '../../app/auth'
import { Badge, Button, Card, EmptyState, ErrorState, PhoneLink, Spinner, Table, Td, Th, useToast } from '../../components/ui'
import { PageHeader } from '../../components/PageHeader'
import { date, dateTime, money, plate } from '../../lib/format'
import { TransferDialog, VehicleForm } from './VehicleForm'

export function VehicleDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const toast = useToast()
  const { user } = useAuth()
  const [editOpen, setEditOpen] = useState(false)
  const [transferOpen, setTransferOpen] = useState(false)

  const { data: v, isLoading, error, refetch } = useQuery({
    queryKey: ['vehicles', Number(id)],
    queryFn: () => api<VehicleDetail>(`/vehicles/${id}`),
  })

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['vehicles'] })
    void qc.invalidateQueries({ queryKey: ['clients'] })
    void qc.invalidateQueries({ queryKey: ['search'] })
  }

  const archive = useMutation({
    mutationFn: (restore: boolean) => api<Vehicle>(`/vehicles/${id}/${restore ? 'desarquivar' : 'arquivar'}`, { method: 'POST' }),
    onSuccess: (_, restore) => {
      invalidate()
      toast.push(restore ? 'Veículo reativado.' : 'Veículo arquivado.')
    },
    onError: (e) => toast.push(errorMessage(e), 'danger'),
  })

  const remove = useMutation({
    mutationFn: () => api(`/vehicles/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      invalidate()
      toast.push('Veículo excluído.')
      navigate('/veiculos', { replace: true })
    },
    onError: (e) => toast.push(errorMessage(e), 'danger'),
  })

  if (isLoading) return <Spinner />
  if (error && isNotFound(error)) {
    return <EmptyState title="Veículo não encontrado" action={<Link to="/veiculos" className="text-gold-deep underline">Voltar para veículos</Link>} />
  }
  if (error || !v) return <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} />

  const arquivado = !!v.arquivado_em

  return (
    <>
      <PageHeader
        eyebrow={
          <span>
            <Link to="/veiculos" className="hover:underline">
              Veículos
            </Link>{' '}
            / Ficha
          </span>
        }
        title={`${v.marca ? `${v.marca} ` : ''}${v.modelo}`}
        subtitle={arquivado ? `Arquivado em ${dateTime(v.arquivado_em)}.` : undefined}
        actions={
          <>
            <Button variant="secondary" onClick={() => setEditOpen(true)} disabled={arquivado}>
              <Pencil className="h-4 w-4" /> Editar
            </Button>
            <Button variant="secondary" onClick={() => setTransferOpen(true)} disabled={arquivado}>
              <ArrowRightLeft className="h-4 w-4" /> Transferir
            </Button>
            {arquivado ? (
              <Button variant="secondary" onClick={() => archive.mutate(true)} loading={archive.isPending}>
                <ArchiveRestore className="h-4 w-4" /> Reativar
              </Button>
            ) : (
              <Button
                variant="ghost"
                onClick={() => {
                  if (confirm('Arquivar este veículo? Ele some das listas e da busca; o histórico continua.')) archive.mutate(false)
                }}
                loading={archive.isPending}
              >
                <Archive className="h-4 w-4" /> Arquivar
              </Button>
            )}
            {user?.role === 'admin' && v.historico.length === 0 && (
              <Button
                variant="danger"
                onClick={() => {
                  if (confirm('Excluir este veículo? Só é possível porque não há histórico.')) remove.mutate()
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
        <Card title="Dados">
          <div className="mb-4 inline-flex items-center rounded-md border border-line bg-paper px-4 py-2 font-label text-[22px] tracking-[0.12em]">
            {plate(v.placa)}
          </div>
          <dl className="grid grid-cols-[110px_1fr] gap-y-2.5 text-[14px]">
            <dt className="label-dim self-center">Marca</dt>
            <dd>{v.marca || <span className="text-muted">—</span>}</dd>
            <dt className="label-dim self-center">Modelo</dt>
            <dd>{v.modelo}</dd>
            <dt className="label-dim self-center">Cor</dt>
            <dd>{v.cor || <span className="text-muted">—</span>}</dd>
            <dt className="label-dim self-center">Ano</dt>
            <dd className="tabular">{v.ano ?? <span className="text-muted">—</span>}</dd>
            <dt className="label-dim self-center">Dono</dt>
            <dd className="flex flex-wrap items-center gap-x-3">
              <Link to={`/clientes/${v.cliente.id}`} className="font-medium text-gold-deep hover:underline">
                {v.cliente.nome}
              </Link>
              <PhoneLink digits={v.cliente.telefone} className="text-muted" />
            </dd>
            <dt className="label-dim self-center">Cadastro</dt>
            <dd className="tabular">{date(v.created_at)}</dd>
            <dt className="label-dim self-start pt-0.5">Observações</dt>
            <dd className="whitespace-pre-wrap text-ink-2">{v.observacoes || <span className="text-muted">—</span>}</dd>
          </dl>
        </Card>

        <Card title="Histórico de serviços">
          {v.historico.length === 0 ? (
            <p className="text-[13.5px] text-muted">Nenhuma ordem de serviço para este veículo ainda.</p>
          ) : (
            <Table className="!shadow-none">
              <thead>
                <tr>
                  <Th>OS</Th>
                  <Th>Cliente</Th>
                  <Th>Status</Th>
                  <Th>Entrada</Th>
                  <Th className="text-right">Valor</Th>
                </tr>
              </thead>
              <tbody>
                {v.historico.map((h) => (
                  <tr key={h.id}>
                    <Td className="tabular">{h.numero ? `nº ${String(h.numero).padStart(3, '0')}` : `#${h.id}`}</Td>
                    <Td>
                      <Link to={`/clientes/${h.client_id}`} className="hover:text-gold-deep hover:underline">
                        {h.cliente}
                      </Link>
                    </Td>
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

      <VehicleForm open={editOpen} onClose={() => setEditOpen(false)} vehicle={v} />
      <TransferDialog open={transferOpen} onClose={() => setTransferOpen(false)} vehicle={v} />
    </>
  )
}
