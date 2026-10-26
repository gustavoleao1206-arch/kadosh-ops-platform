/** Conversão entre o que o usuário digita ("129,90") e o inteiro em centavos que a API usa. */

export function centsToInput(centavos: number | null | undefined): string {
  if (centavos === null || centavos === undefined) return ''
  return (centavos / 100).toFixed(2).replace('.', ',')
}

/** Aceita "129,90", "129.90", "R$ 1.299,90", "1.299" (milhar) e "1299". */
export function inputToCents(texto: string): number | null {
  const limpo = texto.replace(/[^\d,.-]/g, '').trim()
  if (!limpo) return null

  let normalizado: string
  if (limpo.includes(',')) {
    // vírgula manda: pontos são separador de milhar
    normalizado = limpo.replace(/\./g, '').replace(',', '.')
  } else if (/^\d{1,3}(\.\d{3})+$/.test(limpo)) {
    // "1.299" colado de uma tabela = mil duzentos e noventa e nove reais, não 1,299
    normalizado = limpo.replace(/\./g, '')
  } else {
    normalizado = limpo
  }

  const valor = Number(normalizado)
  if (!Number.isFinite(valor) || valor < 0) return null
  return Math.round(valor * 100)
}
