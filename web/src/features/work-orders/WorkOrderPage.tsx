import { Link, useNavigate, useParams } from 'react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Trash2 } from 'lucide-react'
import { api, errorMessage, isNotFound } from '../../api/client'
import type { WorkOrderDetail } from '../../api/types'
import { useAuth } from '../../app/auth'
import { Button, Card, EmptyState, ErrorState, Spinner, useToast } from '../../components/ui'
import { PageHeader } from '../../components/PageHeader'
import { dateTime } from '../../lib/format'
import { WorkOrderPanel, tituloOS } from './WorkOrderPanel'

export function WorkOrderPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const toast = useToast()
  const { user } = useAuth()

  const { data: wo, isLoading, error, refetch } = useQuery({
    queryKey: ['work-orders', Number(id)],
    queryFn: () => api<WorkOrderDetail>(`/work-orders/${id}`),
  })

  const remove = useMutation({
    mutationFn: () => api(`/work-orders/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['work-orders'] })
      void qc.invalidateQueries({ queryKey: ['agenda'] })
      toast.push('Excluída.')
      navigate('/os', { replace: true })
    },
    onError: (e) => toast.push(errorMessage(e), 'danger'),
  })

  if (isLoading) return <Spinner />
  if (error && isNotFound(error)) {
    return <EmptyState title="Ordem de serviço não encontrada" action={<Link to="/os" className="text-gold-deep underline">Voltar</Link>} />
  }
  if (error || !wo) return <ErrorState message={errorMessage(error)} onRetry={() => void refetch()} />

  return (
    <>
      <PageHeader
        eyebrow={
          <span>
            <Link to="/os" className="hover:underline">
              Ordens de serviço
            </Link>{' '}
            / {wo.numero ? 'OS' : wo.status === 'orcamento' ? 'Orçamento' : 'Agendamento'}
          </span>
        }
        title={tituloOS(wo)}
        subtitle={wo.entrada ? `Entrada em ${dateTime(wo.entrada)}.` : undefined}
        actions={
          user?.role === 'admin' &&
          wo.numero === null && (
            <Button
              variant="danger"
              onClick={() => {
                if (confirm('Excluir? Só é possível porque o veículo ainda não foi recebido.')) remove.mutate()
              }}
              loading={remove.isPending}
            >
              <Trash2 className="h-4 w-4" /> Excluir
            </Button>
          )
        }
      />
      <Card>
        <WorkOrderPanel id={wo.id} />
      </Card>
    </>
  )
}
