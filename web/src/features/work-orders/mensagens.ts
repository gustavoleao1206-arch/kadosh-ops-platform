/** Textos prontos de WhatsApp — o momento de maior valor do dia é avisar o cliente. */

import type { WorkOrder } from '../../api/types'
import { dateTime, money, plate } from '../../lib/format'

function primeiroNome(nome: string): string {
  return nome.trim().split(/\s+/)[0]
}

function veiculoTexto(wo: WorkOrder): string {
  if (!wo.veiculo) return ''
  const modelo = `${wo.veiculo.marca ? `${wo.veiculo.marca} ` : ''}${wo.veiculo.modelo}`
  return wo.veiculo.placa ? `${modelo} (${plate(wo.veiculo.placa)})` : modelo
}

export function textoLembrete(wo: WorkOrder): string {
  const carro = veiculoTexto(wo)
  return (
    `Olá, ${primeiroNome(wo.cliente.nome)}! Aqui é da Kadosh Detail. ` +
    `Confirmando seu horário: ${dateTime(wo.scheduled_at)}${carro ? ` — ${carro}` : ''}. ` +
    `Podemos confirmar?`
  )
}

export function textoOrcamento(wo: WorkOrder): string {
  const linhas = wo.itens.map((i) => `• ${i.descricao}: ${money(i.valor_centavos)}`).join('\n')
  const desconto = wo.desconto_centavos ? `\nDesconto: -${money(wo.desconto_centavos)}` : ''
  const carro = veiculoTexto(wo)
  return (
    `Olá, ${primeiroNome(wo.cliente.nome)}! Segue o orçamento da Kadosh Detail` +
    `${carro ? ` para o ${carro}` : ''}:\n\n${linhas}${desconto}\n\nTotal: ${money(wo.valor_total_centavos)}`
  )
}

export function textoPronto(wo: WorkOrder): string {
  const carro = veiculoTexto(wo)
  return `Olá, ${primeiroNome(wo.cliente.nome)}! ${carro ? `Seu ${carro} está pronto` : 'Seu veículo está pronto'} para retirada na Kadosh Detail. 🚗✨`
}
