import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router'
import { ExternalLink } from 'lucide-react'
import { api } from '../../api/client'
import type { WorkOrderDetail } from '../../api/types'
import { Dialog } from '../../components/ui'
import { WorkOrderPanel, tituloOS } from './WorkOrderPanel'

/** A OS aberta a partir da agenda. O mesmo conteúdo da tela cheia (/os/:id). */
export function WorkOrderDialog({ id, onClose }: { id: number | null; onClose: () => void }) {
  const { data: wo } = useQuery({
    queryKey: ['work-orders', id],
    queryFn: () => api<WorkOrderDetail>(`/work-orders/${id}`),
    enabled: !!id,
  })

  return (
    <Dialog
      open={!!id}
      onClose={onClose}
      width="lg"
      title={tituloOS(wo)}
      footer={
        id && (
          <Link to={`/os/${id}`} onClick={onClose} className="flex items-center gap-1.5 text-[13px] text-gold-deep hover:underline">
            Abrir em tela cheia <ExternalLink className="h-3.5 w-3.5" />
          </Link>
        )
      }
    >
      {id && <WorkOrderPanel id={id} />}
    </Dialog>
  )
}
