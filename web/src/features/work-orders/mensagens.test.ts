/**
 * Os textos que vão para o cliente pelo WhatsApp.
 *
 * É o único lugar do painel que MONTA conteúdo em vez de só exibir o que a API mandou — e o
 * único que sai da loja e chega a um terceiro. Um erro aqui não aparece numa tela interna: aparece
 * na conversa do cliente, com o nome da Kadosh em cima.
 *
 * O app tem um `mensagens.dart` que espelha `textoPronto`. Se um dos dois mudar sozinho, o cliente
 * recebe textos diferentes conforme quem avisou — por isso a expectativa aqui é literal.
 */

import { describe, expect, it } from 'vitest'
import type { WorkOrder } from '../../api/types'
import { textoLembrete, textoOrcamento, textoPronto } from './mensagens'

function os(patch: Partial<WorkOrder> = {}): WorkOrder {
  return {
    id: 9,
    numero: 5,
    previsao_manual: false,
    status: 'aguardando_retirada',
    status_label: 'Aguardando retirada',
    status_tone: 'ok',
    client_id: 1,
    vehicle_id: 1,
    scheduled_at: '2026-09-10T13:00:00Z',
    entrada: null,
    previsao_conclusao: null,
    conclusao: null,
    vencimento: null,
    desconto_centavos: 0,
    valor_total_centavos: 12990,
    pago_centavos: 0,
    saldo_centavos: 12990,
    situacao_cobranca: 'pendente',
    situacao_cobranca_label: 'A receber',
    situacao_cobranca_tone: 'warn',
    observacoes: null,
    observacoes_entrada: null,
    created_at: '2026-09-07T12:00:00Z',
    updated_at: '2026-09-07T12:00:00Z',
    itens: [{ id: 1, service_id: 1, descricao: 'Lavagem Simples', valor_centavos: 12990, created_at: '2026-09-07T12:00:00Z' }],
    cliente: { id: 1, nome: 'Ruan Oliveira da Silva', telefone: '5582999110001' } as WorkOrder['cliente'],
    veiculo: { id: 1, marca: 'Honda', modelo: 'Civic EX', placa: 'BRA2E19' } as WorkOrder['veiculo'],
    ...patch,
  } as WorkOrder
}

describe('textoPronto', () => {
  it('chama o cliente pelo primeiro nome', () => {
    // "Olá, Ruan Oliveira da Silva!" soa a cobrança de banco, não a estética que ele conhece
    const texto = textoPronto(os())
    expect(texto).toContain('Olá, Ruan!')
    expect(texto).not.toContain('Oliveira')
  })

  it('nomeia o carro com marca, modelo e placa', () => {
    expect(textoPronto(os())).toContain('Honda Civic EX (BRA-2E19)')
  })

  it('sem veículo, não escreve um espaço vazio no lugar do carro', () => {
    const texto = textoPronto(os({ veiculo: null }))
    expect(texto).toContain('Seu veículo está pronto')
    expect(texto).not.toMatch(/\s{2,}/)
  })

  it('veículo sem placa não vira parêntese vazio', () => {
    const texto = textoPronto(os({ veiculo: { id: 1, marca: 'Honda', modelo: 'Civic EX', placa: null } as WorkOrder['veiculo'] }))
    expect(texto).toContain('Honda Civic EX')
    expect(texto).not.toContain('()')
  })

  it('veículo sem marca não começa com espaço', () => {
    const texto = textoPronto(os({ veiculo: { id: 1, marca: null, modelo: 'Gol', placa: 'ABC1D23' } as WorkOrder['veiculo'] }))
    expect(texto).toContain('Gol (ABC-1D23)')
    expect(texto).not.toContain('  Gol')
  })
})

describe('textoLembrete', () => {
  it('confirma o horário no fuso da loja', () => {
    // 13:00Z = 10:00 em Maceió; mandar "13:00" faria o cliente chegar três horas atrasado
    const texto = textoLembrete(os())
    expect(texto).toContain('10/09/2026')
    expect(texto).toContain('10:00')
    expect(texto).toContain('Olá, Ruan!')
  })

  it('termina perguntando, porque o objetivo é a resposta', () => {
    expect(textoLembrete(os()).trim()).toMatch(/\?$/)
  })
})

describe('textoOrcamento', () => {
  it('lista cada serviço com o preço e fecha com o total', () => {
    const texto = textoOrcamento(
      os({
        itens: [
          { id: 1, service_id: 1, descricao: 'Lavagem Simples', valor_centavos: 12990, created_at: '' },
          { id: 2, service_id: 2, descricao: 'Polimento Técnico', valor_centavos: 99990, created_at: '' },
        ],
        valor_total_centavos: 112980,
      }),
    )
    expect(texto).toContain('• Lavagem Simples: ')
    expect(texto).toContain('• Polimento Técnico: ')
    expect(texto).toMatch(/Total: R\$\s?1\.129,80/)
  })

  it('mostra o desconto como linha própria, não escondido no total', () => {
    // o cliente precisa VER o abatimento; escondê-lo no total joga fora o efeito comercial
    const texto = textoOrcamento(os({ desconto_centavos: 5000, valor_total_centavos: 7990 }))
    expect(texto).toContain('Desconto: -')
    expect(texto).toMatch(/Total: R\$\s?79,90/)
  })

  it('sem desconto, não escreve "Desconto: -R$ 0,00"', () => {
    expect(textoOrcamento(os())).not.toContain('Desconto')
  })

  it('orçamento sem veículo ainda faz sentido', () => {
    // orçamento nasce sem carro definido — é o caso normal, não a exceção
    const texto = textoOrcamento(os({ veiculo: null }))
    expect(texto).toContain('Segue o orçamento da Kadosh Detail:')
  })
})

describe('a marca no texto', () => {
  it('usa o nome comercial e nunca o vocabulário interno', () => {
    const textos = [textoPronto(os()), textoLembrete(os()), textoOrcamento(os())]
    for (const texto of textos) {
      expect(texto).toContain('Kadosh Detail')
      // decisão de marca: nada de "ritual", "sagrado" ou o K isolado em material de cliente
      expect(texto.toLowerCase()).not.toMatch(/ritual|sagrad/)
    }
  })
})
