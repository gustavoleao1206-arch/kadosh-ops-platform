/**
 * Oito peças de interface, e só. Tudo deriva dos tokens do index.css.
 * Button · Input/Field · Badge · Card · Dialog · Table · EmptyState · Spinner (+ useToast, PhoneLink)
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react'
import { Loader2, X } from 'lucide-react'
import { phone, whatsappUrl } from '../lib/format'

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ')
}

/* ---------- Button ---------- */

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md'

const variants: Record<Variant, string> = {
  primary: 'bg-obsidian text-ivory hover:bg-carbon focus-visible:ring-gold/40 border border-obsidian',
  secondary: 'bg-surface text-ink border border-line hover:border-gold hover:text-gold-deep focus-visible:ring-gold/30',
  ghost: 'bg-transparent text-ink-2 hover:bg-surface-2 hover:text-ink focus-visible:ring-gold/30 border border-transparent',
  danger: 'bg-surface text-danger border border-danger/40 hover:bg-danger-wash focus-visible:ring-danger/30',
}
const sizes: Record<Size, string> = {
  sm: 'h-8 px-3 text-[13px] gap-1.5',
  md: 'h-10 px-4 text-[14px] gap-2',
}

/** Classes do botão para usar em links (<a>) sem aninhar botão dentro de link. */
export function buttonClasses(variant: Variant = 'primary', size: Size = 'md', className?: string): string {
  return cx(
    'inline-flex items-center justify-center rounded-md font-medium transition focus:outline-none focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-60',
    variants[variant],
    sizes[size],
    className,
  )
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  className,
  children,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: Size; loading?: boolean }) {
  return (
    <button className={buttonClasses(variant, size, className)} disabled={disabled || loading} {...rest}>
      {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
      {children}
    </button>
  )
}

/* ---------- Field / Input ---------- */

export function Field({
  label,
  hint,
  error,
  children,
  className,
}: {
  label: string
  hint?: string
  error?: string
  children: ReactNode
  className?: string
}) {
  return (
    <label className={cx('block', className)}>
      <span className="label-dim mb-1.5 block">{label}</span>
      {children}
      {error ? (
        <span className="mt-1 block text-[12.5px] text-danger">{error}</span>
      ) : hint ? (
        <span className="mt-1 block text-[12.5px] text-muted">{hint}</span>
      ) : null}
    </label>
  )
}

export function Input({ className, ref, ...rest }: InputHTMLAttributes<HTMLInputElement> & { ref?: React.Ref<HTMLInputElement> }) {
  return <input ref={ref} className={cx('input', className)} {...rest} />
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const { className, ...rest } = props
  return <textarea className={cx('input min-h-[88px] resize-y', className)} {...rest} />
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  const { className, ...rest } = props
  return <select className={cx('input', className)} {...rest} />
}

/* ---------- Badge ---------- */

type Tone = 'neutral' | 'gold' | 'ok' | 'warn' | 'danger'
const tones: Record<Tone, string> = {
  neutral: 'bg-surface-2 text-ink-2 border-line',
  gold: 'bg-gold-wash text-gold-deep border-gold/30',
  ok: 'bg-ok-wash text-ok border-ok/30',
  warn: 'bg-warn-wash text-warn border-warn/30',
  danger: 'bg-danger-wash text-danger border-danger/30',
}

export function Badge({ tone = 'neutral', children, className }: { tone?: Tone; children: ReactNode; className?: string }) {
  return (
    <span
      className={cx(
        'inline-flex items-center rounded border px-2 py-0.5 font-label text-[10.5px] uppercase tracking-[0.16em]',
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}

/* ---------- Card ---------- */

export function Card({ children, className, title, actions }: { children: ReactNode; className?: string; title?: string; actions?: ReactNode }) {
  return (
    <section className={cx('rounded-lg border border-line bg-surface shadow-card', className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-5 py-3">
          {title && <h2 className="font-display text-[20px] font-semibold leading-none text-ink">{title}</h2>}
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  )
}

/* ---------- Dialog ---------- */

export function Dialog({
  open,
  onClose,
  title,
  children,
  footer,
  width = 'md',
}: {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
  footer?: ReactNode
  width?: 'md' | 'lg'
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const downOnBackdrop = useRef(false)
  const titleId = useId()

  useEffect(() => {
    const el = ref.current
    if (!el) return
    if (open && !el.open) {
      el.showModal()
      // o navegador focaria o botão "Fechar"; queremos o primeiro campo
      el.querySelector<HTMLElement>('[data-autofocus], input:not([type=hidden]), select, textarea')?.focus()
    }
    if (!open && el.open) el.close()
  }, [open])

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      // fecha só quando o gesto começou E terminou no fundo (selecionar texto e soltar fora não fecha)
      onPointerDown={(e) => {
        downOnBackdrop.current = e.target === ref.current
      }}
      onClick={(e) => {
        if (downOnBackdrop.current && e.target === ref.current) onClose()
        downOnBackdrop.current = false
      }}
      className={cx(
        'm-auto w-[calc(100%-2rem)] rounded-lg border border-line bg-surface p-0 text-ink shadow-card backdrop:bg-obsidian/50',
        width === 'lg' ? 'max-w-2xl' : 'max-w-lg',
      )}
    >
      <div className="flex items-center justify-between border-b border-line px-5 py-3">
        <h2 id={titleId} className="font-display text-[22px] font-semibold leading-none">
          {title}
        </h2>
        <button type="button" onClick={onClose} className="rounded p-1 text-muted hover:bg-surface-2 hover:text-ink" aria-label="Fechar">
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="px-5 py-4">{children}</div>
      {footer && <div className="flex justify-end gap-2 border-t border-line bg-paper px-5 py-3">{footer}</div>}
    </dialog>
  )
}

/* ---------- Table ---------- */

export function Table({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cx('overflow-x-auto rounded-lg border border-line bg-surface shadow-card', className)}>
      <table className="w-full text-left text-[14px]">{children}</table>
    </div>
  )
}
export function Th({ children, className }: { children?: ReactNode; className?: string }) {
  return <th className={cx('label-dim whitespace-nowrap bg-surface-2 px-4 py-2.5 font-normal', className)}>{children}</th>
}
export function Td({ children, className }: { children?: ReactNode; className?: string }) {
  return <td className={cx('border-t border-line px-4 py-3 align-middle', className)}>{children}</td>
}

/** Linha clicável que respeita seleção de texto e links/botões internos. */
export function rowClick(go: () => void) {
  return (e: React.MouseEvent<HTMLTableRowElement>) => {
    if (window.getSelection()?.toString()) return
    if ((e.target as HTMLElement).closest('a,button,select,input')) return
    go()
  }
}

/* ---------- EmptyState / Spinner / ErrorState ---------- */

export function EmptyState({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-14 text-center">
      <p className="font-display text-[22px] text-ink">{title}</p>
      {hint && <p className="max-w-sm text-[13.5px] text-muted">{hint}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="rounded-lg border border-danger/30 bg-surface">
      <EmptyState
        title="Não foi possível carregar"
        hint={message}
        action={
          onRetry && (
            <Button variant="secondary" onClick={onRetry}>
              Tentar de novo
            </Button>
          )
        }
      />
    </div>
  )
}

export function Spinner({ label = 'Carregando…' }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 px-2 py-8 text-muted" role="status">
      <Loader2 className="h-4 w-4 animate-spin" /> <span className="text-[13px]">{label}</span>
    </div>
  )
}

/* ---------- PhoneLink ---------- */

/** Telefone sempre clicável: abre o WhatsApp do cliente. */
export function PhoneLink({ digits, className }: { digits: string | null | undefined; className?: string }) {
  if (!digits) return <span className="text-muted">—</span>
  return (
    <a
      href={whatsappUrl(digits)}
      target="_blank"
      rel="noreferrer"
      title="Abrir no WhatsApp"
      className={cx('tabular whitespace-nowrap hover:text-gold-deep hover:underline', className)}
    >
      {phone(digits)}
    </a>
  )
}

/* ---------- Toast ---------- */

interface Toast {
  id: number
  text: string
  tone: 'ok' | 'danger' | 'neutral'
}
const ToastContext = createContext<{ push: (text: string, tone?: Toast['tone']) => void } | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const push = useCallback((text: string, tone: Toast['tone'] = 'ok') => {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t, { id, text, tone }])
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3800)
  }, [])
  const value = useMemo(() => ({ push }), [push])
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cx(
              'pointer-events-auto rounded-md border px-4 py-2.5 text-[13.5px] shadow-card',
              t.tone === 'ok' && 'border-ok/30 bg-ok-wash text-ok',
              t.tone === 'danger' && 'border-danger/30 bg-danger-wash text-danger',
              t.tone === 'neutral' && 'border-line bg-surface text-ink',
            )}
          >
            {t.text}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast fora do ToastProvider')
  return ctx
}
