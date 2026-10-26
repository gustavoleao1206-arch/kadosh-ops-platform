/**
 * Formatação que o dono lê. Dinheiro, telefone, placa, datas e a variação do dashboard.
 *
 * As datas são testadas contra o fuso da LOJA, não o do computador: o painel fixa America/Maceio
 * (`format.ts`) exatamente porque pode ser aberto de qualquer lugar, e a agenda é a da loja. Um
 * pagamento das 22h em Maceió é do dia seguinte em UTC — se a formatação usasse o relógio do
 * navegador, o caixa mostraria o lançamento no dia errado.
 */

import { describe, expect, it } from 'vitest'
import { date, dateTime, duracao, initials, money, phone, plate, variacaoPct, whatsappUrl } from './format'

describe('money', () => {
  it('escreve em real brasileiro', () => {
    expect(money(12990)).toMatch(/R\$\s?129,90/)
    expect(money(0)).toMatch(/R\$\s?0,00/)
    expect(money(100000000)).toMatch(/R\$\s?1\.000\.000,00/)
  })

  it('nulo é zero na tela, não "NaN"', () => {
    // acontece de verdade: campo que o backend ainda não devolveu numa resposta parcial
    expect(money(null)).toMatch(/R\$\s?0,00/)
    expect(money(undefined)).toMatch(/R\$\s?0,00/)
  })
})

describe('phone', () => {
  it('formata celular e fixo nacionais', () => {
    expect(phone('5582999110001')).toBe('(82) 99911-0001')
    expect(phone('558233110001')).toBe('(82) 3311-0001')
  })

  it('número de fora fica como veio, com o "+"', () => {
    expect(phone('351912345678')).toBe('+351912345678')
  })

  it('sem telefone mostra travessão, não vazio', () => {
    expect(phone(null)).toBe('—')
    expect(phone('')).toBe('—')
  })
})

describe('plate', () => {
  it('quebra a placa de 7 como o balcão lê', () => {
    expect(plate('BRA2E19')).toBe('BRA-2E19')
    expect(plate('ABC1D23')).toBe('ABC-1D23')
  })

  it('o que não tem 7 caracteres fica em paz', () => {
    expect(plate('ABC123')).toBe('ABC123')
    expect(plate(null)).toBe('sem placa')
  })
})

describe('datas no fuso da loja', () => {
  it('formata no fuso de Maceió, não no do computador', () => {
    // 2026-09-08T01:30Z é ainda dia 7 às 22:30 em Maceió
    expect(date('2026-09-08T01:30:00Z')).toBe('07/09/2026')
    expect(dateTime('2026-09-08T01:30:00Z')).toContain('07/09/2026')
    expect(dateTime('2026-09-08T01:30:00Z')).toContain('22:30')
  })

  it('o mesmo instante escrito com outro deslocamento dá o mesmo texto', () => {
    const a = date('2026-09-07T22:30:00-03:00')
    const b = date('2026-09-08T01:30:00Z')
    const c = date('2026-09-08T10:30:00+09:00')
    expect(a).toBe(b)
    expect(b).toBe(c)
  })

  it('sem data mostra travessão', () => {
    expect(date(null)).toBe('—')
    expect(dateTime(undefined)).toBe('—')
  })
})

describe('duracao', () => {
  it('escreve o tempo do jeito que se fala', () => {
    expect(duracao(30)).toBe('30min')
    expect(duracao(90)).toBe('1h 30min')
    expect(duracao(480)).toBe('8h')
    expect(duracao(1500)).toBe('1d 1h')
  })

  it('zero e nulo viram travessão', () => {
    expect(duracao(0)).toBe('—')
    expect(duracao(null)).toBe('—')
  })
})

describe('initials', () => {
  it('usa primeiro e último nome', () => {
    expect(initials('Ruan Oliveira')).toBe('RO')
    expect(initials('Maria de Souza Lima')).toBe('ML')
  })

  it('nome único não quebra', () => {
    expect(initials('Ruan')).toBe('R')
  })
})

describe('whatsappUrl', () => {
  it('monta o link com o texto codificado', () => {
    expect(whatsappUrl('5582999110001')).toBe('https://wa.me/5582999110001')
    const comTexto = whatsappUrl('5582999110001', 'Olá, tudo bem?')
    expect(comTexto).toContain('?text=')
    expect(comTexto).toContain(encodeURIComponent('Olá, tudo bem?'))
  })
})

describe('variacaoPct', () => {
  it('calcula a variação contra o período anterior', () => {
    expect(variacaoPct(150, 100)).toBe(50)
    expect(variacaoPct(50, 100)).toBe(-50)
    expect(variacaoPct(100, 100)).toBe(0)
  })

  it('sem base de comparação devolve null em vez de infinito', () => {
    // dividir por zero viraria "∞%" na tela do dono
    expect(variacaoPct(1000, 0)).toBeNull()
    expect(variacaoPct(0, 0)).toBeNull()
    expect(variacaoPct(1000, -5)).toBeNull()
  })
})
