import { useEffect, useState } from 'react'
import { Input } from './ui'
import { centsToInput, inputToCents } from '../lib/money'

/** Campo de dinheiro: mostra "129,90", devolve 12990. */
export function MoneyInput({
  value,
  onChange,
  placeholder = '0,00',
  disabled,
  className,
  autoFocus,
  ariaLabel,
}: {
  value: number | null
  onChange: (centavos: number | null) => void
  placeholder?: string
  disabled?: boolean
  className?: string
  autoFocus?: boolean
  /** nome para leitor de tela quando o rótulo visível não é um <label> */
  ariaLabel?: string
}) {
  const [texto, setTexto] = useState(() => centsToInput(value))

  // reflete mudanças vindas de fora (ex.: preço preenchido ao escolher o serviço)
  useEffect(() => {
    setTexto((atual) => (inputToCents(atual) === value ? atual : centsToInput(value)))
  }, [value])

  return (
    <div className="relative">
      <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[13px] text-muted">R$</span>
      <Input
        aria-label={ariaLabel}
        inputMode="decimal"
        value={texto}
        disabled={disabled}
        placeholder={placeholder}
        data-autofocus={autoFocus ? '' : undefined}
        className={`tabular pl-9 text-right ${className ?? ''}`}
        onChange={(e) => {
          setTexto(e.target.value)
          onChange(inputToCents(e.target.value))
        }}
        onBlur={() => setTexto(centsToInput(inputToCents(texto)))}
      />
    </div>
  )
}
