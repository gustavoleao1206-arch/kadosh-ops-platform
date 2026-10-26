/**
 * A conversão entre o que o dono digita e o inteiro em centavos que a API recebe.
 *
 * É o ponto do painel onde um erro vira dinheiro errado direto: um "1.299" lido como 1,299 lança
 * uma OS de R$ 1,30 no lugar de R$ 1.299,00, e ninguém confere o total de novo depois de digitar.
 * Até esta fase, o painel inteiro não tinha um teste sequer.
 */

import { describe, expect, it } from 'vitest'
import { centsToInput, inputToCents } from './money'

describe('centsToInput', () => {
  it('escreve com vírgula e duas casas, como o balcão lê', () => {
    expect(centsToInput(12990)).toBe('129,90')
    expect(centsToInput(100)).toBe('1,00')
    expect(centsToInput(5)).toBe('0,05')
    expect(centsToInput(0)).toBe('0,00')
  })

  it('campo vazio é diferente de zero', () => {
    // "não digitei nada" e "digitei zero" são coisas diferentes: o primeiro não manda o campo
    expect(centsToInput(null)).toBe('')
    expect(centsToInput(undefined)).toBe('')
    expect(centsToInput(0)).toBe('0,00')
  })

  it('valores altos mantêm as duas casas', () => {
    expect(centsToInput(199990)).toBe('1999,90')
    expect(centsToInput(100000000)).toBe('1000000,00')
  })
})

describe('inputToCents', () => {
  it('lê o que o dono digita', () => {
    expect(inputToCents('129,90')).toBe(12990)
    expect(inputToCents('129.90')).toBe(12990)
    expect(inputToCents('1299')).toBe(129900)
    expect(inputToCents('0,05')).toBe(5)
  })

  it('aceita o que vem colado de uma tabela ou de outro sistema', () => {
    expect(inputToCents('R$ 1.299,90')).toBe(129990)
    expect(inputToCents('  R$ 129,90  ')).toBe(12990)
  })

  it('"1.299" é mil duzentos e noventa e nove, não um vírgula duzentos e noventa e nove', () => {
    // o erro que valeria mil reais: ponto como milhar é o padrão brasileiro
    expect(inputToCents('1.299')).toBe(129900)
    expect(inputToCents('1.299.900')).toBe(129990000)
  })

  it('com vírgula presente, o ponto é sempre milhar', () => {
    expect(inputToCents('1.299,90')).toBe(129990)
    expect(inputToCents('10.000,00')).toBe(1000000)
  })

  it('sem vírgula e sem grupo de três, o ponto é decimal', () => {
    // "129.9" veio de um teclado numérico ou de um sistema em inglês
    expect(inputToCents('129.9')).toBe(12990)
    expect(inputToCents('0.5')).toBe(50)
  })

  it('campo vazio devolve null, não zero', () => {
    expect(inputToCents('')).toBeNull()
    expect(inputToCents('   ')).toBeNull()
    expect(inputToCents('R$ ')).toBeNull()
    expect(inputToCents('abc')).toBeNull()
  })

  it('recusa valor negativo em vez de mandá-lo para a API', () => {
    // desconto negativo viraria acréscimo silencioso
    expect(inputToCents('-10')).toBeNull()
    expect(inputToCents('-1,50')).toBeNull()
  })

  it('arredonda o centavo em vez de truncar', () => {
    // 0.1 + 0.2 em ponto flutuante: sem o round, "0,30" viraria 29 centavos
    expect(inputToCents('0,30')).toBe(30)
    expect(inputToCents('1,10')).toBe(110)
    expect(inputToCents('8,15')).toBe(815)
    expect(inputToCents('129,29')).toBe(12929)
  })

  it('ida e volta preserva o valor', () => {
    for (const centavos of [0, 5, 99, 100, 12990, 129990, 1999900, 100000000]) {
      expect(inputToCents(centsToInput(centavos))).toBe(centavos)
    }
  })
})
