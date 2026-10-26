import { useEffect, useState } from 'react'

export function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = window.setTimeout(() => setV(value), ms)
    return () => window.clearTimeout(t)
  }, [value, ms])
  return v
}

/**
 * Responde a uma media query em JavaScript — para o que o CSS não resolve.
 *
 * Quase tudo do responsivo é classe do Tailwind (`lg:flex`), e deve continuar sendo: CSS não
 * re-renderiza. Isto existe só para o punhado de casos em que muda o CONTEÚDO, não a aparência —
 * um texto de ajuda que não cabe, uma tabela que vira lista.
 */
export function useMediaQuery(query: string): boolean {
  const [combina, setCombina] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const mql = window.matchMedia(query)
    const aoMudar = () => setCombina(mql.matches)
    aoMudar() // o valor pode ter mudado entre o primeiro render e este efeito
    mql.addEventListener('change', aoMudar)
    return () => mql.removeEventListener('change', aoMudar)
  }, [query])
  return combina
}

/** Telas estreitas: o mesmo corte do `lg:` do Tailwind, para não haver dois limiares no sistema. */
export function useTelaEstreita(): boolean {
  return useMediaQuery('(max-width: 1023px)')
}
