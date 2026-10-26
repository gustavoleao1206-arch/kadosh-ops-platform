# Arquitetura — Kadosh Ops (v2, aprovada em 21/08/2026)

Versão em texto do documento de aprovação. Fonte de verdade para decisões de projeto.

## Premissa
**Um sistema, dois clientes.** Painel web (dono/admin) e app Android (sócio/staff) usam o mesmo backend,
a mesma API (`/api/v1`), o mesmo banco e a mesma autenticação. Toda regra de negócio vive no backend.

```
Painel web (React+Vite) ─┐
                         ├─ HTTPS /api/v1 ─► FastAPI (Python 3.11) ─► PostgreSQL 16
App Android (Flutter)   ─┘        (serve também o build do painel em /)
```

## Decisões aprovadas
1. **Flutter** para o APK (alternativa registrada: Expo/React Native).
2. **Agenda e OS numa entidade só** (`work_orders`) com um fluxo de status.
3. **Sessão opaca no servidor** (tabela `sessions`, hash SHA-256), sem JWT. Web = cookie HttpOnly + `Sec-Fetch-Site`; Android = Bearer. 30 dias deslizantes; revogação imediata.
4. **Staff vê e opera tudo**; admin controla catálogo, usuários, exclusões, estornos de terceiros e reabertura de OS.
5. **OS com itens** (vários serviços, preço ajustável) e **vários pagamentos** (sinal + restante); "a receber" calculado; estorno em vez de exclusão.
6. **Render** Starter + Postgres Basic (~US$ 13/mês), deploy via GitHub (privado) após CI verde.
7. Projeto em **`X:\dev\kadosh-ops`** (sem acento/espaço). PostgreSQL portátil em `X:\dev\pgsql`, dados em `X:\dev\pgdata`, porta 5433. **Sem Docker local.**
8. Visual: painel claro com lateral obsidiana; app com tema claro e escuro (ouro só em acentos).
9. Botão "Avisar cliente no WhatsApp" (`wa.me`) na v1.

## Banco (10 tabelas)
`users`, `sessions`, `auth_logs`, `clients`, `vehicles`, `services`, `work_orders`, `work_order_items`,
`work_order_events`, `payments`. Detalhes e regras em `backend/app/models/`.

- Dinheiro em **centavos inteiros**; datas `timestamptz` (UTC) com agregados no fuso `America/Maceio`.
- Status: texto + CHECK. Fluxo: `orcamento → agendado → confirmado → recebido → em_execucao → aguardando_retirada → concluido`, terminais `cancelado` / `nao_compareceu`. Saltos para frente e um passo atrás permitidos; cancelar exige motivo; tudo em `work_order_events`.
- `numero` da OS vem de `work_order_numero_seq` ao **receber o veículo**.
- Placa opcional, normalizada, única só entre veículos ativos (`uq_vehicles_placa_ativa`). Telefone só dígitos com DDI; duplicado avisa.
- `arquivado_em` em clientes e veículos; FKs RESTRICT para o que tem histórico; CASCADE só em itens e eventos.
- Total da OS recalculado por uma única função com lock; concluída congela itens/desconto.

## Vocabulário financeiro (fixado em testes)
- **Recebido** = soma de `payments` não estornados por `pago_em`.
- **Faturado** = `valor_total` das OS `concluido` por `conclusao`.
- **A receber** = saldo das OS no pátio ou concluídas.
- **Em serviço** = `recebido`, `em_execucao`, `aguardando_retirada`.

## Pagamentos (fase 5)
Dinheiro entra **a partir da recepção do veículo** (`STATUSES_ACEITAM_PAGAMENTO`): antes disso a OS
ainda não tem número e pode ser excluída — aceitar pagamento ali abriria caminho para apagar uma OS
com dinheiro. Sinal pago por Pix antes da chegada é lançado na recepção com `pago_em` retroativo.

- Vários pagamentos por OS, **uma forma por lançamento** (Pix + dinheiro no mesmo ato = dois).
- Pagamento acima do saldo é recusado: não existe troco no sistema, registra-se o que fica no caixa.
- `recalc_total` tem **piso**: o total nunca cai abaixo do que já foi recebido. Desconto ou remoção de
  serviço depois do pagamento exige estorno antes.
- Concluir com saldo em aberto e cancelar com pagamento **continuam permitidos** — o painel avisa e o
  dono decide. Travar faria inventarem pagamento falso, e aí o caixa mentiria.
- Não existe `PATCH` nem `DELETE` de pagamento: corrigir é **estornar e lançar de novo**.
- Estorno: o autor desfaz o próprio lançamento, o administrador desfaz o de qualquer um. Motivo
  obrigatório, sem prazo. `pode_estornar` vem calculado no payload — o cliente não reimplementa a regra.
- Estorno abate o mês do `pago_em` (mês já conferido pode mudar), não o do `estornado_em`.
- **`GET /caixa` é liberado para o sócio** (`CurrentUser`, sem filtro por papel), coerente com a
  decisão 4: staff vê e opera tudo. Confirmado pelo dono em 04/09/2026. Só estorno de terceiros,
  catálogo, usuários e exclusões continuam restritos ao administrador.

## Segurança (aplicada desde a fase 1)
Argon2id (19 MiB, 2 it.), limite de login por IP real (proxy headers), por origem (e-mail + IP) e por conta (só para
origem que a conta nunca usou — um terceiro não tranca o dono), cabeçalhos CSP/nosniff/frame,
corpo máximo 1 MB, schemas `extra="forbid"`, docs desligadas em produção, bootstrap do admin só com tabela vazia
e troca obrigatória de senha, seed demo recusa produção, IntegrityError → 409.

## Recepção do veículo (fase 4)
`POST /work-orders/intake` é uma transação só: cria (ou reaproveita) cliente e veículo, abre a OS
já em `recebido`, lança os serviços combinados e registra o estado do carro na chegada. Se qualquer
passo falhar, nada é criado — o balcão nunca fica com um cliente sem carro nem com carro sem OS.

- `idempotency_key` gerada no aparelho: repetir o toque com sinal ruim devolve a mesma OS.
- Carro que chegou sem marcar → corpo com `cliente` + `veiculo`.
  Agendamento chegando → corpo com `work_order_id` (cliente e carro já estão na OS; `veiculo` só se
  o cliente apareceu em outro carro).
- O número legível da OS só é tirado da sequence no fim, quando nada mais pode falhar.
- `observacoes_entrada` é a defesa da loja numa reclamação: depois que a execução começa, só o
  administrador altera — e a mudança vira evento no histórico, guardando o texto anterior.
- `GET /patio` devolve os carros que estão fisicamente na loja, agrupados por status.

## Relatórios (fase 6)
"Faturado" passou a existir em código nesta fase — até a 5 era só vocabulário nesta página.

- `GET /relatorios?periodo=mes|mes_passado|personalizado` (+ `de`/`ate` no personalizado, teto de um
  ano). O rótulo do período ("Setembro de 2026") vem pronto do backend.
- O Faturado vem decomposto em `faturado_recebido` + `faturado_a_receber`, que fecham com ele. As
  duas partes existem porque Faturado e Recebido divergem de propósito: serviço entregue num mês e
  pago em outro aparece nos dois lugares em datas diferentes.
- Ticket médio = faturado ÷ OS concluídas, já líquido de desconto (o desconto vive na OS).
- Ranking por serviço mostra **receita bruta** e uma linha "Descontos concedidos" fecha a conta.
  O desconto não é rateado entre itens: seria inventar número que não existe no banco.
- Cancelamentos e não comparecimentos saem de `work_order_events`, não do status atual.
- `GET /relatorios/clientes-sumidos?dias=90` — quem já concluiu alguma OS e não volta. Cadastro sem
  OS nenhuma não entra: é cliente novo, não cliente perdido.
- Relatórios são `CurrentUser`, mesma decisão do `/caixa` (04/09/2026): o sócio vê.
- **Fora de escopo, e de propósito:** lucro, custo e margem (não existe campo de custo no banco);
  R$/hora (o item da OS congela nome e valor, não a duração); comparação com período anterior e
  metas (com dezenas de OS/mês, ruído vira tendência); exportação; biblioteca de gráfico.

## Fases
1 Arquitetura/banco/auth · 2 Clientes/veículos · 3 Serviços/agenda · 4 OS/recepção/pátio ·
5 Financeiro · 6 Dashboard/relatórios · 7 Android · 8 Segurança · 9 Testes · 10 Deploy (+ backup testado).
