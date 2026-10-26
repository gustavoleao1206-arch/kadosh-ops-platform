import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Banknote, Car, MessageCircle, Plus, Trash2, Undo2, User } from 'lucide-react'
import { api, errorMessage } from '../../api/client'
import type { FormaPagamento, Page, Payment, Service, Transition, WorkOrderDetail } from '../../api/types'
import { Badge, Button, Field, Input, Select, Spinner, Textarea, buttonClasses, cx, useToast } from '../../components/ui'
import { MoneyInput } from '../../components/MoneyInput'
import { EtiquetaCobranca } from '../../components/stats'
import { dateTime, money, plate, whatsappUrl } from '../../lib/format'
import { hour, sameBusinessDay } from '../../lib/datetime'
import { isoToLocalInput, toIsoFromLocalInput } from '../../lib/datetime'
import { textoLembrete, textoOrcamento, textoPronto } from './mensagens'
import { IntakeDialog } from './IntakeDialog'

/**
 * Corpo da OS: serviços, valores, datas, observações e histórico — com a barra de ações no topo.
 * Usado tanto no diálogo (a partir da agenda) quanto na tela cheia (/os/:id).
 */
export function WorkOrderPanel({ id }: { id: number }) {
  const qc = useQueryClient()
  const toast = useToast()
  const [servicoId, setServicoId] = useState('')
  const [valorNegociado, setValorNegociado] = useState<number | null>(null)
  const [desconto, setDesconto] = useState<number | null>(null)
  const [descontoMotivo, setDescontoMotivo] = useState('')
  const [vencimento, setVencimento] = useState('')
  const [quando, setQuando] = useState('')
  const [previsao, setPrevisao] = useState('')
  const [entradaObs, setEntradaObs] = useState('')
  const [motivoFor, setMotivoFor] = useState<Transition | null>(null)
  const [motivo, setMotivo] = useState('')
  const [recepcaoAberta, setRecepcaoAberta] = useState(false)
  const [pagamentoAberto, setPagamentoAberto] = useState(false)
  const [valorPago, setValorPago] = useState<number | null>(null)
  const [forma, setForma] = useState('')
  const [estornando, setEstornando] = useState<Payment | null>(null)
  const [estornoMotivo, setEstornoMotivo] = useState('')
  // uma chave por abertura do bloco: tocar duas vezes não lança dois pagamentos
  const chavePagamento = useRef('')
  // O mesmo para o serviço: uma chave por LANÇAMENTO pretendido (cunhada ao escolher o serviço),
  // não por clique. Gerá-la dentro do clique deixava a idempotência do item inerte justamente no
  // caso que ela existe para cobrir: resposta perdida na rede, o dono clica de novo, chave nova,
  // serviço entra duas vezes e o total dobra.
  const chaveItem = useRef('')
  // Último valor que veio do servidor para cada campo editável. Serve para saber se uma mudança
  // veio de lá (e deve entrar na tela) ou se é texto que o usuário ainda está digitando.
  const doServidor = useRef<Campos | null>(null)
  const motivoRef = useRef<HTMLInputElement>(null)

  const { data: wo, isLoading } = useQuery({
    queryKey: ['work-orders', id],
    queryFn: () => api<WorkOrderDetail>(`/work-orders/${id}`),
  })

  const formas = useQuery({
    queryKey: ['payment-methods'],
    queryFn: () => api<FormaPagamento[]>('/payment-methods'),
    staleTime: Infinity, // lista fixa do domínio: não muda enquanto o painel estiver aberto
  })

  // O catálogo é pedido DO PONTO DE VISTA DESTE CLIENTE: cada serviço vem com o preço combinado
  // dele (quando houver) e com o que vale de fato. Sem `client_id` o seletor mostraria o preço de
  // tabela e o backend cobraria outro — a diferença apareceria só depois de lançar.
  const servicos = useQuery({
    queryKey: ['services', 'ativos', wo?.client_id],
    queryFn: () =>
      api<Page<Service>>('/services', {
        query: { apenas_ativos: true, page_size: 200, client_id: wo!.client_id },
      }),
    enabled: wo !== undefined,
    staleTime: 60_000,
  })

  // Cada campo se atualiza sozinho quando o SERVIDOR muda (lançar um serviço recalcula a
  // previsão, por exemplo) — mas nunca por cima do que o usuário está digitando e ainda não
  // salvou. Sem isso, clicar em "Iniciar execução" apagava o estado do carro na chegada.
  useEffect(() => {
    if (!wo) return
    const vindo = camposDe(wo)
    const antes = doServidor.current
    doServidor.current = vindo
    if (!antes || antes.id !== vindo.id) {
      setDesconto(vindo.desconto)
      setQuando(vindo.quando)
      setPrevisao(vindo.previsao)
      setEntradaObs(vindo.entradaObs)
      setVencimento(vindo.vencimento)
      return
    }
    if (antes.desconto !== vindo.desconto) setDesconto((atual) => (atual === antes.desconto ? vindo.desconto : atual))
    if (antes.quando !== vindo.quando) setQuando((atual) => (atual === antes.quando ? vindo.quando : atual))
    if (antes.previsao !== vindo.previsao) setPrevisao((atual) => (atual === antes.previsao ? vindo.previsao : atual))
    if (antes.entradaObs !== vindo.entradaObs) setEntradaObs((atual) => (atual === antes.entradaObs ? vindo.entradaObs : atual))
    if (antes.vencimento !== vindo.vencimento) setVencimento((atual) => (atual === antes.vencimento ? vindo.vencimento : atual))
  }, [wo])

  useEffect(() => {
    if (motivoFor) motivoRef.current?.focus()
  }, [motivoFor])

  // Toda mutação de dinheiro (pagamento, estorno, desconto, item, conclusão de OS) mexe nestas
  // quatro leituras. Uma função só para não depender de alguém lembrar de cada uma.
  const invalidarFinanceiro = () => {
    void qc.invalidateQueries({ queryKey: ['caixa'] })
    void qc.invalidateQueries({ queryKey: ['extrato'] })
    void qc.invalidateQueries({ queryKey: ['relatorios'] })
    void qc.invalidateQueries({ queryKey: ['dashboard'] })
  }

  const invalidate = () => {
    void qc.invalidateQueries({ queryKey: ['work-orders'] })
    void qc.invalidateQueries({ queryKey: ['patio'] })
    void qc.invalidateQueries({ queryKey: ['agenda'] })
    void qc.invalidateQueries({ queryKey: ['clients'] })
    void qc.invalidateQueries({ queryKey: ['vehicles'] })
    // Dinheiro mexido aqui muda o relatório, o extrato e o dashboard. Antes da fase 8 só o caixa
    // era invalidado, e as outras telas ficavam defasadas até o staleTime — com o financeiro
    // crescendo, isso vira o dono vendo dois números diferentes em duas abas abertas.
    invalidarFinanceiro()
  }

  const aoSalvar = (msg?: string) => ({
    onSuccess: (data: WorkOrderDetail) => {
      qc.setQueryData(['work-orders', id], data)
      invalidate()
      if (msg) toast.push(msg)
    },
    onError: (e: unknown) => toast.push(errorMessage(e), 'danger'),
  })

  const addItem = useMutation({
    mutationFn: (body: { service_id: number; valor_centavos?: number; idempotency_key: string }) =>
      api<WorkOrderDetail>(`/work-orders/${id}/items`, { method: 'POST', body: [body] }),
    onError: (e: unknown) => toast.push(errorMessage(e), 'danger'),
    onSuccess: (data: WorkOrderDetail) => {
      qc.setQueryData(['work-orders', id], data)
      invalidate()
      toast.push('Serviço adicionado.')
      // O formulário só é limpo aqui: limpar no clique apagava a seleção e obrigava a escolher o
      // serviço de novo depois de uma falha — o que cunhava outra chave e desfazia a proteção.
      setServicoId('')
      setValorNegociado(null)
      chaveItem.current = ''
    },
  })
  const delItem = useMutation({
    mutationFn: (itemId: number) => api<WorkOrderDetail>(`/work-orders/${id}/items/${itemId}`, { method: 'DELETE' }),
    ...aoSalvar('Serviço removido.'),
  })
  const patch = useMutation({
    mutationFn: (body: Record<string, unknown>) => api<WorkOrderDetail>(`/work-orders/${id}`, { method: 'PATCH', body }),
    onSuccess: (data: WorkOrderDetail, body) => {
      // O servidor normaliza o que recebe (limpar a previsão a devolve calculada, por exemplo).
      // O campo que acabou de ser salvo adota o valor de lá mesmo quando ele é igual ao anterior —
      // senão a tela ficaria mostrando para sempre algo que não foi gravado.
      const vindo = camposDe(data)
      doServidor.current = vindo
      if ('desconto_centavos' in body) {
        setDesconto(vindo.desconto)
        setDescontoMotivo('')
      }
      if ('scheduled_at' in body) setQuando(vindo.quando)
      if ('previsao_conclusao' in body) setPrevisao(vindo.previsao)
      if ('observacoes_entrada' in body) setEntradaObs(vindo.entradaObs)
      qc.setQueryData(['work-orders', id], data)
      invalidate()
    },
    onError: (e: unknown) => toast.push(errorMessage(e), 'danger'),
  })
  const pagar = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api<WorkOrderDetail>(`/work-orders/${id}/payments`, { method: 'POST', body }),
    onSuccess: (data: WorkOrderDetail) => {
      fecharPagamento()
      qc.setQueryData(['work-orders', id], data)
      invalidate()
      toast.push('Pagamento lançado.')
    },
    onError: (e: unknown) => toast.push(errorMessage(e), 'danger'),
  })

  const estornar = useMutation({
    mutationFn: ({ paymentId, motivo }: { paymentId: number; motivo: string }) =>
      api<WorkOrderDetail>(`/work-orders/${id}/payments/${paymentId}/estorno`, { method: 'POST', body: { motivo } }),
    onSuccess: (data: WorkOrderDetail) => {
      setEstornando(null)
      setEstornoMotivo('')
      qc.setQueryData(['work-orders', id], data)
      invalidate()
      toast.push('Pagamento estornado.')
    },
    onError: (e: unknown) => toast.push(errorMessage(e), 'danger'),
  })

  const transition = useMutation({
    mutationFn: (payload: { to_status: string; motivo?: string }) =>
      api<WorkOrderDetail>(`/work-orders/${id}/transition`, {
        method: 'POST',
        // expected_status: se o outro aparelho mudou antes, a API responde 409 em vez de sobrescrever
        body: { ...payload, expected_status: wo?.status },
      }),
    onSuccess: (data: WorkOrderDetail) => {
      setMotivoFor(null)
      setMotivo('')
      qc.setQueryData(['work-orders', id], data)
      invalidate()
      toast.push('Status atualizado.')
    },
    onError: (e: unknown) => toast.push(errorMessage(e), 'danger'),
  })

  const executar = (acao: Transition) => {
    // Cancelar exige motivo, então este aviso tem de vir antes do desvio para o campo de motivo.
    // Cancelar não devolve dinheiro sozinho: quem devolveu estorna, e o botão continua lá depois.
    if (acao.status === 'cancelado' && wo && wo.pago_centavos > 0) {
      if (!confirm(`Este cliente já pagou ${money(wo.pago_centavos)}. Cancelar mesmo assim? Estornar é um passo à parte.`)) return
    }
    if (acao.requer_motivo) return setMotivoFor(acao)
    // A PRIMEIRA recepção tem trabalho de balcão junto: qual carro chegou, o que foi combinado e
    // em que estado ele veio — vai pela tela de recepção. "Voltar para a fila" também tem destino
    // "recebido", mas o carro já entrou (wo.entrada preenchido): esse é um clique seco mesmo.
    if (acao.status === 'recebido' && wo && !wo.entrada) return setRecepcaoAberta(true)
    // entregar fiado é decisão do dono; o sistema informa e não impede
    if (acao.status === 'concluido' && wo && wo.saldo_centavos > 0) {
      if (!confirm(`Faltam ${money(wo.saldo_centavos)} a receber. Concluir e entregar mesmo assim?`)) return
    }
    transition.mutate({ to_status: acao.status })
  }

  const fecharPagamento = () => {
    setPagamentoAberto(false)
    setValorPago(null)
    setForma('')
  }

  const abrirPagamento = () => {
    // já vem preenchido com o que falta: o caso comum é quitar de uma vez
    setValorPago(wo?.saldo_centavos || null)
    setForma(formas.data?.[0]?.valor ?? 'dinheiro')
    chavePagamento.current = `pg-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    setPagamentoAberto(true)
  }

  /** O preço que o backend usaria se ninguém digitasse nada — combinado do cliente, ou tabela. */
  const precoEfetivo = (s: Service) => s.valor_efetivo_centavos ?? s.valor_base_centavos

  const escolherServico = (valor: string) => {
    setServicoId(valor)
    const s = servicos.data?.items.find((x) => x.id === Number(valor))
    setValorNegociado(s ? precoEfetivo(s) : null)
    // trocar de serviço é outro lançamento: chave nova
    chaveItem.current = `it-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
  }

  const lancarServico = () => {
    const s = servicos.data?.items.find((x) => x.id === Number(servicoId))
    if (!s || !chaveItem.current) return
    addItem.mutate({
      service_id: s.id,
      // só manda valor quando o dono REALMENTE mudou: mandar igual ao efetivo faria a OS carregar
      // um preço "manual" que na verdade era o combinado, e o histórico perderia essa distinção
      valor_centavos: valorNegociado !== null && valorNegociado !== precoEfetivo(s) ? valorNegociado : undefined,
      idempotency_key: chaveItem.current,
    })
  }

  if (isLoading || !wo) return <Spinner />

  const editavel = !['cancelado', 'concluido'].includes(wo.status)
  const podeMexerNosItens = !['cancelado', 'concluido', 'nao_compareceu'].includes(wo.status)
  const soma = wo.itens.reduce((s, i) => s + i.valor_centavos, 0)

  return (
    <div className="grid gap-5">
      {/* ações: o que dá para fazer com esta OS agora. Só o passo natural fica escuro — os avisos
          de WhatsApp ficam à direita, separados, para não disputar o olho com ele. */}
      <div className="flex flex-wrap items-center gap-2 rounded-md border border-line bg-paper px-3 py-2.5">
        <Badge tone={wo.status_tone}>{wo.status_label}</Badge>
        <div className="flex flex-wrap gap-2">
          {wo.acoes.map((a) => (
            <Button
              key={a.status}
              size="sm"
              variant={a.tone === 'danger' ? 'danger' : a.principal ? 'primary' : 'secondary'}
              onClick={() => executar(a)}
              loading={transition.isPending}
            >
              {a.acao_label}
            </Button>
          ))}
          {wo.acoes.length === 0 && <span className="text-[13px] text-muted">Sem ações disponíveis neste status.</span>}
        </div>
        <div className="ml-auto flex flex-wrap gap-2">
          {wo.cliente.telefone && wo.status === 'aguardando_retirada' && (
            <a href={whatsappUrl(wo.cliente.telefone, textoPronto(wo))} target="_blank" rel="noreferrer" className={buttonClasses('secondary', 'sm')}>
              <MessageCircle className="h-3.5 w-3.5" /> Avisar que está pronto
            </a>
          )}
          {wo.cliente.telefone && wo.itens.length > 0 && ['orcamento', 'agendado', 'confirmado'].includes(wo.status) && (
            <a href={whatsappUrl(wo.cliente.telefone, textoOrcamento(wo))} target="_blank" rel="noreferrer" className={buttonClasses('secondary', 'sm')}>
              <MessageCircle className="h-3.5 w-3.5" /> Enviar orçamento
            </a>
          )}
          {wo.cliente.telefone && wo.scheduled_at && !wo.entrada && (
            <a href={whatsappUrl(wo.cliente.telefone, textoLembrete(wo))} target="_blank" rel="noreferrer" className={buttonClasses('secondary', 'sm')}>
              <MessageCircle className="h-3.5 w-3.5" /> Lembrar do horário
            </a>
          )}
        </div>
      </div>

      {motivoFor && (
        <div className="rounded-md border border-warn/30 bg-warn-wash p-3">
          <Field label={`Motivo — ${motivoFor.label}`}>
            <Input ref={motivoRef} value={motivo} onChange={(e) => setMotivo(e.target.value)} placeholder="Ex.: cliente desistiu, chuva, remarcado por telefone" />
          </Field>
          <div className="mt-2 flex justify-end gap-2">
            {/* "Cancelar" aqui seria o mesmo texto do botão que confirma o cancelamento da OS */}
            <Button size="sm" variant="ghost" onClick={() => setMotivoFor(null)}>
              Voltar
            </Button>
            <Button
              size="sm"
              variant={motivoFor.tone === 'danger' ? 'danger' : 'primary'}
              disabled={!motivo.trim()}
              loading={transition.isPending}
              onClick={() => transition.mutate({ to_status: motivoFor.status, motivo: motivo.trim() })}
            >
              {motivoFor.acao_label}
            </Button>
          </div>
        </div>
      )}

      {/* quem e qual carro */}
      <div className="grid gap-1.5 text-[14px]">
        <Link to={`/clientes/${wo.client_id}`} className="flex items-center gap-2 font-medium hover:text-gold-deep">
          <User className="h-4 w-4 text-gold" /> {wo.cliente.nome}
        </Link>
        {wo.veiculo ? (
          <Link to={`/veiculos/${wo.veiculo.id}`} className="flex items-center gap-2 text-ink-2 hover:text-gold-deep">
            <Car className="h-4 w-4 text-gold" /> <span className="tabular">{plate(wo.veiculo.placa)}</span> ·{' '}
            {wo.veiculo.marca ? `${wo.veiculo.marca} ` : ''}
            {wo.veiculo.modelo}
            {wo.veiculo.cor ? ` · ${wo.veiculo.cor}` : ''}
          </Link>
        ) : (
          <span className="flex items-center gap-2 text-muted">
            <Car className="h-4 w-4" /> Sem veículo definido (orçamento)
          </span>
        )}
      </div>

      {/* serviços */}
      <div>
        <div className="label-dim mb-2">Serviços</div>
        {wo.itens.length === 0 ? (
          <p className="text-[13.5px] text-muted">Nenhum serviço lançado.</p>
        ) : (
          <ul className="divide-y divide-line rounded-md border border-line">
            {wo.itens.map((item) => (
              <li key={item.id} className="flex items-center gap-3 px-3 py-2">
                <span className="flex-1 truncate text-[14px]">{item.descricao}</span>
                <span className="tabular text-[14px]">{money(item.valor_centavos)}</span>
                {podeMexerNosItens && (
                  <button type="button" onClick={() => delItem.mutate(item.id)} className="rounded p-1 text-muted hover:bg-surface-2 hover:text-danger" aria-label={`Remover ${item.descricao}`}>
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}

        {podeMexerNosItens && (
          <>
            <div className="mt-2 flex flex-wrap gap-2">
              <Select value={servicoId} onChange={(e) => escolherServico(e.target.value)} className="min-w-[220px] flex-1 !py-1.5 text-[13px]" aria-label="Serviço a adicionar">
                <option value="">Adicionar serviço…</option>
                {servicos.data?.items.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.nome} — {money(precoEfetivo(s))}
                  </option>
                ))}
              </Select>
              <div className="w-32">
                <MoneyInput value={valorNegociado} onChange={setValorNegociado} disabled={!servicoId} ariaLabel="Preço combinado" />
              </div>
              <Button size="sm" variant="secondary" disabled={!servicoId} loading={addItem.isPending} onClick={lancarServico}>
                <Plus className="h-4 w-4" /> Lançar
              </Button>
            </div>
            {servicoId && <OrigemDoPreco servico={servicos.data?.items.find((x) => x.id === Number(servicoId))} digitado={valorNegociado} />}
          </>
        )}
      </div>

      {/* valores */}
      <div className="grid gap-2 rounded-md border border-line bg-paper p-4 text-[14px]">
        <div className="flex justify-between">
          <span className="text-muted">Serviços</span>
          <span className="tabular">{money(soma)}</span>
        </div>
        <div className="flex items-center justify-between gap-3">
          <span className="text-muted">Desconto</span>
          <div className="flex items-center gap-2">
            <div className="w-32">
              <MoneyInput value={desconto} onChange={setDesconto} disabled={!editavel || patch.isPending} ariaLabel="Desconto" />
            </div>
            {desconto !== (wo.desconto_centavos || null) && editavel && (
              <Button
                size="sm"
                variant="secondary"
                loading={patch.isPending}
                onClick={() =>
                  patch.mutate({
                    desconto_centavos: desconto ?? 0,
                    // o motivo vai junto e fica gravado no histórico; vazio não vira campo em branco
                    ...(descontoMotivo.trim() ? { desconto_motivo: descontoMotivo.trim() } : {}),
                  })
                }
              >
                Aplicar
              </Button>
            )}
          </div>
        </div>
        {/* "Por que este cliente levou R$ 50?" é a pergunta que aparece três meses depois. O campo
            só existe enquanto o valor está mudando: pedir motivo de um desconto que já foi aplicado
            não teria onde gravar (o evento nasce com a mudança). */}
        {desconto !== (wo.desconto_centavos || null) && editavel && (
          <div className="-mt-1 flex justify-end">
            <Input
              value={descontoMotivo}
              onChange={(e) => setDescontoMotivo(e.target.value)}
              placeholder="Motivo do desconto (opcional)"
              maxLength={500}
              className="w-[280px] !py-1.5 text-[13px]"
              aria-label="Motivo do desconto"
            />
          </div>
        )}
        <div className="flex justify-between border-t border-line pt-2 font-medium">
          <span>Total</span>
          <span className="tabular text-[16px] text-gold-deep">{money(wo.valor_total_centavos)}</span>
        </div>

        {/* dinheiro: o que já entrou e o que falta */}
        {(wo.pago_centavos > 0 || wo.aceita_pagamento) && (
          <div className="mt-1 grid gap-2 border-t border-line pt-2">
            <div className="flex justify-between">
              <span className="text-muted">Recebido</span>
              <span className="tabular">{money(wo.pago_centavos)}</span>
            </div>
            {/* O que dizer da segunda linha depende do estado da OS, não só do sinal do saldo:
                numa OS cancelada ninguém deve nada (quem está com dinheiro alheio é a loja), e numa
                OS sem serviço lançado saldo zero não é "quitado" — é que não há o que cobrar. */}
            {!wo.aceita_pagamento && wo.pago_centavos > 0 ? (
              <div className="flex items-center justify-between gap-3">
                <span className="font-medium text-ink">Recebido e não devolvido</span>
                <span className="text-[13px] text-muted">Estorne para registrar a devolução.</span>
              </div>
            ) : wo.valor_total_centavos === 0 ? (
              <div className="flex items-center justify-between gap-3">
                <span className="text-muted">Sem serviços lançados</span>
              </div>
            ) : (
              <div className="flex items-center justify-between gap-3">
                <span className={cx(wo.saldo_centavos > 0 ? 'font-medium text-ink' : 'text-muted')}>
                  {wo.saldo_centavos > 0 ? 'A receber' : 'Pago'}
                </span>
                <div className="flex items-center gap-2">
                  {/* rótulo e cor vêm do backend: a data de corte do atraso é do servidor, e um
                      computador com o relógio errado inventaria atraso que não existe */}
                  <EtiquetaCobranca label={wo.situacao_cobranca_label} tone={wo.situacao_cobranca_tone} />
                  {wo.saldo_centavos > 0 ? (
                    <span
                      className={cx(
                        'tabular font-medium',
                        wo.situacao_cobranca === 'atrasado' ? 'text-danger' : 'text-warn',
                      )}
                    >
                      {money(wo.saldo_centavos)}
                    </span>
                  ) : (
                    <Badge tone="ok">quitado</Badge>
                  )}
                  {wo.aceita_pagamento && wo.saldo_centavos > 0 && !pagamentoAberto && (
                    <Button size="sm" onClick={abrirPagamento}>
                      <Banknote className="h-4 w-4" /> Lançar pagamento
                    </Button>
                  )}
                </div>
              </div>
            )}

            {/* Prazo de pagamento. É a ÚNICA coisa editável numa OS já concluída, e por um motivo
                concreto: o carro entregue devendo é justamente o que precisa ganhar data — sem ela,
                a régua o marca como atrasado no dia seguinte, que é o comportamento certo para quem
                sumiu, e errado para quem combinou pagar na sexta. */}
            {wo.aceita_pagamento && wo.saldo_centavos > 0 && (
              <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line pt-2">
                <span className="text-muted">Vencimento</span>
                <div className="flex items-center gap-2">
                  <Input
                    type="date"
                    value={vencimento}
                    onChange={(e) => setVencimento(e.target.value)}
                    className="w-[150px] !py-1.5 text-[13px]"
                    aria-label="Data de vencimento"
                  />
                  {vencimento !== isoToLocalInput(wo.vencimento).slice(0, 10) && (
                    <Button
                      size="sm"
                      variant="secondary"
                      loading={patch.isPending}
                      onClick={() =>
                        patch.mutate({
                          // fim do dia NA LOJA: "vence dia 20" quer dizer até o fim do dia 20 em
                          // Maceió. A conversão passa pelo helper da casa, nunca por string crua.
                          vencimento: vencimento ? toIsoFromLocalInput(`${vencimento}T23:59`) : null,
                        })
                      }
                    >
                      {vencimento ? 'Definir' : 'Tirar prazo'}
                    </Button>
                  )}
                </div>
              </div>
            )}

            {pagamentoAberto && (
              <div className="grid gap-2 rounded-md border border-gold/40 bg-surface p-3">
                <div className="flex flex-wrap items-end gap-2">
                  <div className="w-32">
                    <Field label="Valor">
                      <MoneyInput value={valorPago} onChange={setValorPago} autoFocus ariaLabel="Valor do pagamento" />
                    </Field>
                  </div>
                  <div className="min-w-[150px] flex-1">
                    <Field label="Forma">
                      <Select value={forma} onChange={(e) => setForma(e.target.value)}>
                        {formas.data?.map((f) => (
                          <option key={f.valor} value={f.valor}>
                            {f.label}
                          </option>
                        ))}
                      </Select>
                    </Field>
                  </div>
                </div>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-[12px] text-muted">
                    Pix e dinheiro no mesmo ato são dois lançamentos — lance o segundo em seguida.
                  </span>
                  <div className="flex gap-2">
                    <Button size="sm" variant="ghost" onClick={fecharPagamento}>
                      Cancelar
                    </Button>
                    <Button
                      size="sm"
                      disabled={!valorPago || !forma}
                      loading={pagar.isPending}
                      onClick={() =>
                        pagar.mutate({ valor_centavos: valorPago, forma, idempotency_key: chavePagamento.current })
                      }
                    >
                      Receber
                    </Button>
                  </div>
                </div>
              </div>
            )}

            {wo.pagamentos.length > 0 && (
              <ul className="grid gap-1">
                {wo.pagamentos.map((p) => (
                  <li key={p.id} className="flex items-center gap-2 text-[13px]">
                    <span className={cx('tabular', p.estornado_em && 'text-muted line-through')}>
                      {money(p.valor_centavos)}
                    </span>
                    <span className={cx('text-muted', p.estornado_em && 'line-through')}>{p.forma_label}</span>
                    <span className="tabular text-[12px] text-muted">
                      {hour(p.pago_em)}
                      {/* Pix de ontem lançado hoje: as duas datas contam histórias diferentes */}
                      {!sameBusinessDay(p.pago_em, p.created_at) && ` · lançado ${dateTime(p.created_at)}`}
                    </span>
                    {p.estornado_em && (
                      <>
                        <Badge tone="danger">estornado</Badge>
                        {p.estorno_motivo && (
                          <span className="max-w-[240px] truncate text-[12px] text-muted" title={p.estorno_motivo}>
                            {p.estorno_motivo}
                          </span>
                        )}
                      </>
                    )}
                    {p.pode_estornar && (
                      <button
                        type="button"
                        onClick={() => {
                          setEstornando(p)
                          setEstornoMotivo('')
                        }}
                        className="ml-auto rounded p-1 text-muted hover:bg-surface-2 hover:text-danger"
                        aria-label={`Estornar ${money(p.valor_centavos)}`}
                      >
                        <Undo2 className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}

            {estornando && (
              <div className="rounded-md border border-danger/30 bg-danger-wash p-3">
                <Field label={`Motivo do estorno — ${money(estornando.valor_centavos)} em ${estornando.forma_label}`}>
                  <Input
                    value={estornoMotivo}
                    onChange={(e) => setEstornoMotivo(e.target.value)}
                    placeholder="Ex.: lancei o valor errado, cartão recusado, devolvido ao cliente"
                    data-autofocus
                  />
                </Field>
                <div className="mt-2 flex justify-end gap-2">
                  <Button size="sm" variant="ghost" onClick={() => setEstornando(null)}>
                    Voltar
                  </Button>
                  <Button
                    size="sm"
                    variant="danger"
                    disabled={!estornoMotivo.trim()}
                    loading={estornar.isPending}
                    onClick={() => estornar.mutate({ paymentId: estornando.id, motivo: estornoMotivo.trim() })}
                  >
                    Estornar
                  </Button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* datas */}
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={wo.entrada ? 'Entrada' : 'Data e hora marcada'}>
          {wo.entrada ? (
            <div className="tabular px-1 py-2 text-[14px]">{dateTime(wo.entrada)}</div>
          ) : (
            <div className="flex gap-2">
              <Input type="datetime-local" value={quando} onChange={(e) => setQuando(e.target.value)} disabled={!editavel} className="tabular" />
              {isoToLocalInput(wo.scheduled_at) !== quando && (
                <Button size="sm" variant="secondary" loading={patch.isPending} onClick={() => patch.mutate({ scheduled_at: toIsoFromLocalInput(quando) })}>
                  Salvar
                </Button>
              )}
            </div>
          )}
        </Field>
        <Field label={wo.conclusao ? 'Concluída em' : 'Previsão de conclusão'} hint={wo.conclusao ? undefined : wo.previsao_manual ? 'Definida à mão.' : 'Calculada pela duração dos serviços — pode ajustar.'}>
          {wo.conclusao ? (
            <div className="tabular px-1 py-2 text-[14px]">{dateTime(wo.conclusao)}</div>
          ) : (
            <div className="flex gap-2">
              <Input type="datetime-local" value={previsao} onChange={(e) => setPrevisao(e.target.value)} disabled={!editavel} className="tabular" />
              {isoToLocalInput(wo.previsao_conclusao) !== previsao && (
                <Button size="sm" variant="secondary" loading={patch.isPending} onClick={() => patch.mutate({ previsao_conclusao: toIsoFromLocalInput(previsao) })}>
                  Salvar
                </Button>
              )}
            </div>
          )}
        </Field>
      </div>

      {/* estado do carro na chegada */}
      {(wo.entrada || entradaObs) && (
        <Field label="Estado do carro na chegada" hint="Riscos, pertences, combustível — registrado na recepção.">
          <Textarea value={entradaObs} onChange={(e) => setEntradaObs(e.target.value)} disabled={!editavel} className={entradaObs ? 'bg-warn-wash/40' : undefined} />
          {entradaObs !== (wo.observacoes_entrada ?? '') && editavel && (
            <div className="mt-2 flex justify-end">
              <Button size="sm" variant="secondary" loading={patch.isPending} onClick={() => patch.mutate({ observacoes_entrada: entradaObs.trim() || null })}>
                Salvar observações de entrada
              </Button>
            </div>
          )}
        </Field>
      )}

      {wo.observacoes && (
        <Field label="Observações">
          <Textarea value={wo.observacoes} readOnly className="cursor-default bg-surface-2" />
        </Field>
      )}

      <IntakeDialog
        open={recepcaoAberta}
        workOrderId={id}
        onClose={() => setRecepcaoAberta(false)}
        onRecebido={(data) => qc.setQueryData(['work-orders', id], data)}
      />

      {/* histórico */}
      <div>
        <div className="label-dim mb-2">Histórico</div>
        <ul className="grid gap-1 text-[13px] text-ink-2">
          {wo.eventos.map((e) => (
            <li key={e.id} className="flex gap-2">
              <span className="tabular w-[118px] shrink-0 text-muted">{dateTime(e.created_at)}</span>
              <span>{e.descricao}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

/**
 * De onde saiu o preço que apareceu no campo.
 *
 * Sem esta linha, um preço combinado parece erro do sistema: o dono vê R$ 99 onde a tabela diz
 * R$ 129 e desconfia. E o contrário também acontece — "cadastrei o preço especial e não pegou",
 * quando na verdade alguém digitou um valor por cima naquela OS.
 */
function OrigemDoPreco({ servico, digitado }: { servico?: Service; digitado: number | null }) {
  if (!servico) return null
  const efetivo = servico.valor_efetivo_centavos ?? servico.valor_base_centavos
  const combinado = servico.valor_cliente_centavos != null
  const alterado = digitado !== null && digitado !== efetivo

  if (alterado) {
    return (
      <p className="mt-1 text-[12px] text-warn">
        Valor alterado — vale só para esta OS. O preço {combinado ? 'combinado com o cliente' : 'de tabela'} continua{' '}
        {money(efetivo)}.
      </p>
    )
  }
  return (
    <p className="mt-1 text-[12px] text-muted">
      {combinado ? (
        <>
          <span className="text-gold-deep">Preço combinado com este cliente.</span> Tabela: {money(servico.valor_base_centavos)}.
        </>
      ) : (
        <>Preço de tabela. Ajuste se combinou outro valor — vale só para esta OS.</>
      )}
    </p>
  )
}

interface Campos {
  id: number
  desconto: number | null
  quando: string
  previsao: string
  entradaObs: string
  vencimento: string
}

function camposDe(wo: WorkOrderDetail): Campos {
  return {
    id: wo.id,
    desconto: wo.desconto_centavos || null,
    quando: isoToLocalInput(wo.scheduled_at),
    previsao: isoToLocalInput(wo.previsao_conclusao),
    entradaObs: wo.observacoes_entrada ?? '',
    // Só a DATA, e no fuso da loja. Cortar o ISO cru mostraria o dia seguinte: "vence dia 20" é
    // guardado como 23:59 em Maceió, que em UTC já é 02:59 do dia 21.
    vencimento: isoToLocalInput(wo.vencimento).slice(0, 10),
  }
}

/** Título consistente entre o diálogo e a tela cheia. */
export function tituloOS(wo?: { numero: number | null; id: number; status: string } | null): string {
  if (!wo) return 'Ordem de serviço'
  if (wo.numero) return `OS nº ${String(wo.numero).padStart(3, '0')}`
  return wo.status === 'orcamento' ? `Orçamento #${wo.id}` : `Agendamento #${wo.id}`
}
