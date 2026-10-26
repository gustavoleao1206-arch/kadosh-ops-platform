import { useRouteError } from 'react-router'
import { buttonClasses } from '../components/ui'

/** Qualquer erro de renderização cai aqui, em português e com saída. */
export function ErrorPage() {
  const err = useRouteError()
  const message = err instanceof Error ? err.message : 'Erro inesperado.'
  return (
    <div className="flex min-h-full items-center justify-center bg-paper p-8">
      <div className="w-full max-w-md rounded-lg border border-line bg-surface p-8 text-center shadow-card">
        <div className="font-display text-[22px] tracking-[0.14em]">
          KAD<span className="text-gold">O</span>SH
        </div>
        <h1 className="mt-6 font-display text-[28px] font-semibold leading-none">Algo deu errado nesta tela</h1>
        <p className="mt-3 text-[13.5px] text-muted">{message}</p>
        <div className="mt-6 flex justify-center gap-2">
          <button type="button" onClick={() => window.location.reload()} className={buttonClasses('secondary')}>
            Recarregar
          </button>
          <a href="/" className={buttonClasses('primary')}>
            Ir para o início
          </a>
        </div>
      </div>
    </div>
  )
}
