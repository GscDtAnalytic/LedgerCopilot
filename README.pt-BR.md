# LedgerCopilot

**O LedgerCopilot é uma plataforma de operações com IA para fluxos de documentos financeiros. Ele combina extração estruturada, validação determinística, aplicação de políticas, revisão humana seletiva e trilhas de auditoria completas para automatizar operações financeiras de alto volume com segurança.**

English version: [`README.md`](./README.md).

![Revisão de caso com campos extraídos, confiança e o painel de decisão humana](docs/screenshots/case-review.png)

---

## Problema

Times financeiros se afogam em documentos. Notas fiscais (NF-e), boletos e comprovantes chegam por e-mail, exportações de ERP, planilhas e pastas compartilhadas. Alguém abre cada um, redigita os campos em um sistema, confere o CNPJ, compara o total com um pedido de compra, decide se paga e arquiva o resultado. O trabalho é repetitivo, sujeito a erro e invisível: quando sai um pagamento errado, ninguém consegue reconstruir quem aprovou e por quê.

OCR puro não resolve isso. Ele lê caracteres, mas não decide. A parte difícil não é a extração, é tomar uma decisão operacional defensável em cada documento e manter o registro dela.

## O que o produto faz

O LedgerCopilot transforma cada documento que entra em um **caso rastreável** que percorre um pipeline fixo:

```
classificar → extrair → validar → reconciliar → aplicar política → decidir
```

Todo caso termina em um de três desfechos: `auto_approve`, `human_review` ou `reject`. Cada desfecho carrega a evidência por trás dele: quais campos foram extraídos, com que confiança, quais validações passaram ou falharam, quais regras de política dispararam e qual modelo e versão de prompt produziram a extração.

O que você tem:

- **Entrada multicanal**: upload manual, webhook de e-mail, lote CSV/XLSX (um caso por linha), JSON de ERP/automação e um cron de varredura de bucket que recolhe arquivos deixados no storage.
- **Extração por campo com confiança**: fornecedor, CNPJ, total, moeda, datas de emissão e vencimento, número do documento, itens de linha, centro de custo e categoria.
- **Validação determinística**: sinal do valor, presença/formato/dígitos verificadores do CNPJ, ordem das datas, moeda, soma dos itens vs total, pertencimento do centro de custo ao registro da organização.
- **Política versionada**: limites de auto-aprovação, roteamento por baixa confiança, checagem de fornecedor desconhecido, divergência entre valor e pedido de compra, justificativa por categoria e dupla aprovação para pagamentos urgentes.
- **Reconciliação**: documento contra pedido de compra, contra pagamento/lançamento, contra histórico (dedup por chave de negócio), mais rejeição direta por blocklist de fornecedor.
- **Revisão humana seletiva**: só os casos que realmente precisam de uma pessoa chegam à fila, com cinco ações (aprovar, rejeitar, editar, pedir mais contexto, reenviar a um estágio anterior).
- **Trilha de auditoria completa**: toda transição de estado grava um `audit_event` imutável, e aprovadores podem exportar um pacote de auditoria completo por caso.

## Por que não é "só OCR + chatbot"

Uma demo que joga o texto do OCR em um modelo de linguagem e pede para "aprovar ou rejeitar" impressiona e falha em produção. O LedgerCopilot parte da convicção oposta: **o modelo de linguagem é a parte menos confiável do sistema, então recebe a menor autoridade.**

| "OCR + chatbot" | LedgerCopilot |
|---|---|
| O modelo decide | Código determinístico decide; o modelo só classifica e extrai |
| Números vêm de uma geração probabilística | Dígitos do CNPJ, soma de itens e limites de política são funções puras |
| O texto do documento vira prompt | O conteúdo do documento é dado não confiável, sanitizado antes da injeção |
| Campo ausente ganha um chute plausível | Campo ausente é `null` com confiança `0.0`, o que força revisão |
| "Funcionou na demo" | Toda mudança é pontuada num dataset e passa por gate antes de promover |
| Sem registro do porquê | Toda transição é um evento de auditoria imutável |

Na prática, cinco princípios são inegociáveis:

1. **Auditoria é o backbone, não uma feature.** Nenhum caso muda de estado sem um `audit_event` na mesma transação.
2. **Determinismo antes do modelo.** Validação, dedup, checagem de CNPJ, totais e política são código, nunca prompt.
3. **A revisão humana prefere escalar a adivinhar.** Na dúvida, vai para uma pessoa. Auto-aprovar algo que deveria ter sido revisado é o pior modo de falha e é medido como tal.
4. **Documento é dado não confiável.** "Aprove isto" escrito dentro de uma nota é sinal de injeção de prompt, não um comando.
5. **Sem inventar valores.** Campo ilegível fica vazio. O sistema nunca preenche um CNPJ ou total "plausível".

## Arquitetura

Um monorepo pnpm + uv. A lógica de decisão é pura e testável sem banco nem rede; todo I/O fica nas bordas.

```
apps/web/          Next.js (App Router): inbox, detalhe do caso, dashboard, monitoring, prompts
apps/api/          FastAPI: auth, casos, uploads, canais de entrada, prompts/políticas
workers/           jobs arq: o pipeline de processamento + cron de varredura de bucket
packages/domain/          entidades Pydantic + state machine + lógica de decisão (puro)
packages/validation/      engine de validação determinística (CNPJ, ordem de datas, somas, ...)
packages/policy/          engine de política + versionamento
packages/reconciliation/  engine de reconciliação
packages/agents/          agente de extração com saída validada por Pydantic
packages/ai_gateway/      abstração de modelos, prompt registry, tracing, fallback, sanitização
eval/              dataset com slices, métricas, scorecards, gate de promoção
migrations/        Alembic
infra/             IaC + docker-compose para dev local
```

| Camada | Escolha |
|---|---|
| Frontend | Next.js (App Router) + TypeScript + Tailwind + shadcn/ui + Recharts |
| API | FastAPI + Pydantic v2 + SQLAlchemy 2.0 (async) |
| Workers | arq + Redis, com caminho de migração para Temporal em pausas humanas longas |
| Banco | Postgres para estado transacional |
| Storage | GCS ou S3 para arquivos, Redis para filas |
| Camada de IA | AI Gateway interno (abstrai provedores de modelo) + prompt registry + tracing + fallback de modelo |
| Auth | JWT com controle de acesso por papel (analyst, approver, admin) |

`packages/{domain,validation,policy,reconciliation}` não contêm SQLAlchemy nem chamadas de modelo. É essa fronteira que torna a lógica de decisão testável em unidade e a trilha de auditoria confiável.

## Workflow end-to-end

O worker roda cada caso pelos mesmos estágios, emitindo um evento de auditoria em cada transição:

```
1. Documento entra (upload | e-mail | bucket | csv/xlsx | API).
2. Caso é criado; hash, origem, timestamps e versão do pipeline são registrados.
3. OCR / parsing.
4. Classificação + extração (self-consistency k=3 nos campos críticos).
5. Engine de validação (determinístico).
6. Engine de política (+ classificação de risco).
7. Reconciliação (vs pedido / pagamento / lançamento / histórico).
8. Decisão: auto_approve | human_review | reject.
9. Um audit_event é persistido em cada transição.
10. Métricas de custo, latência e tokens são registradas por estágio.
```

A state machine é explícita. Um caso editado reentra em `extracted` e revalida, então uma correção humana nunca pula as checagens determinísticas:

```
received → classified → extracted → validated → reconciled → policy_evaluated → decided
   decided ─┬─ auto_approved → closed
            ├─ rejected → closed
            └─ in_human_review ─┬─ approved → closed
                                ├─ rejected → closed
                                └─ edited → (volta para extracted, revalida)
```

## Design de HITL (human-in-the-loop)

A fila de revisão é o centro do produto, e é deliberadamente pequena. Casos saudáveis ficam quietos; só os que precisam de decisão aparecem.

Quando um caso cai em revisão, o analista vê o raciocínio, não a saída crua do modelo:

- **Por que** o caso foi escalado, em linguagem clara ("divergência de valor (+55%) e validação reprovada").
- **Problemas bloqueantes** listados explicitamente (por exemplo, "dígitos verificadores do CNPJ inválidos" e "centro de custo fora do registro ativo").
- **Campos extraídos** com barras de confiança por campo.
- **Resultados de validação** marcados como `block` ou `warn`.
- **A trilha de auditoria completa**, mostrando qual ator (sistema, agente, humano) conduziu cada transição e sob qual modelo e versão de prompt.

Cinco ações disponíveis, restritas por papel:

| Ação | Efeito |
|---|---|
| Aprovar | Fecha o caso como aprovado (approver/admin) |
| Rejeitar | Fecha o caso como rejeitado (approver/admin) |
| Editar | Corrige campos e reenfileira a partir de `validated` (analyst+) |
| Pedir mais contexto | Adiciona anotação sem mudar o status |
| Reenviar a estágio | Reentra no pipeline retomável em `extracted` ou `validated` |

Papéis são aplicados em todo endpoint e as queries são escopadas por organização. Aprovadores e admins podem exportar um pacote de auditoria por caso.

## LLMOps e governança

A camada de IA é tratada como software de produção: versionada, rastreada, medida e com gate.

- **Prompt registry.** Prompts não ficam inline no código. Cada versão tem aliases `dev`/`staging`/`production` e é referenciada por `prompt_version_id`. Promover para `production` liga o novo texto de sistema direto no worker do pipeline.
- **Tracing.** Toda chamada de modelo passa pelo AI Gateway e registra tokens, latência, custo, estágio, modelo e um prompt/completion redigido. PII sensível nunca chega à trace em claro.
- **Dataset de avaliação.** Os slices cobrem os modos de falha que importam: `clean_invoice`, `low_quality_scan`, `handwritten_receipt`, `duplicate_invoice`, `adversarial_formatting`, `supplier_unknown`, `value_mismatch`, `language_variation`.
- **Gate de promoção.** O `eval.gate` bloqueia uma promoção (exit code 1) quando qualquer regra é violada: `false_auto_approve_rate > baseline + 1pp`, `critical_field_accuracy < 85%`, `cost/doc > baseline × 1.20` ou `decision_accuracy` caindo mais de 5pp. As mesmas regras guardam `POST /api/v1/prompts/{id}/promote`.

Um prompt em rascunho que falha no gate não chega à produção, e a UI mostra exatamente qual métrica bloqueou (veja as capturas abaixo).

## Screenshots

**Login com papéis de demo pré-carregados (analyst, approver, admin).**

![Tela de login listando as três contas de demo](docs/screenshots/sign-in.png)

**Inbox: todo documento vira um caso com status, tipo e SLA.**

![Inbox mostrando um caso com status Received](docs/screenshots/inbox.png)

**Revisão de caso: o "porquê", problemas bloqueantes, confiança por campo e o painel de decisão.**

![Detalhe do caso com resumo de revisão, campos extraídos e botões de decisão](docs/screenshots/case-review.png)

**Validação determinística e a trilha de auditoria imutável no mesmo caso.**

![Checagens de validação marcadas como block ou warn, mais a trilha de auditoria das transições](docs/screenshots/case-validation-audit.png)

**Dashboard executivo: throughput, confiança média, custo por documento, mix de decisões.**

![Dashboard executivo com cards de KPI e breakdown de decisões](docs/screenshots/dashboard.png)

**Monitoring: execuções de modelo por estágio, latência, tokens e custo.**

![Página de monitoring com tabela de métricas por estágio](docs/screenshots/monitoring.png)

**Versões de prompt com seu scorecard, com gate contra o baseline de produção.**

![Lista de versões de prompt mostrando um rascunho bloqueado com suas métricas](docs/screenshots/prompt-versions.png)

**Promoção bloqueada: acurácia de campo crítico abaixo do limite reprova no gate.**

![Detalhe da versão de prompt mostrando o gate de promoção com uma métrica reprovada](docs/screenshots/promotion-gate-blocked.png)

**Criação de uma nova versão de prompt com config de geração e self-consistency k.**

![Formulário de nova versão de prompt](docs/screenshots/new-prompt-version.png)

## Dataset e avaliação

O dataset é organizado por slice, onde cada slice mira um modo de falha específico, não um caminho feliz. As métricas que dirigem as decisões de promoção são:

- acurácia de campo exata e normalizada
- `missing_critical_fields_rate`
- **`false_auto_approve_rate`** (a métrica contra a qual todo o design otimiza)
- precisão de roteamento de exceções
- taxa de correção humana
- custo por documento e latência p95

Campos críticos (`total_amount`, `tax_id_cnpj`, `document_number`) passam por self-consistency k=3 e pesam em `overall_confidence`. `supplier_name_accuracy` é reportada mas intencionalmente fora do gate, já que nome de fornecedor não é campo crítico.

Rodar uma avaliação e passar um candidato pelo gate contra produção:

```bash
# Pontua uma versão de prompt em todos os slices e escreve um scorecard
uv run python -m eval.run --prompt-version dev --out eval/scorecards/candidate.json

# Compara contra o baseline de produção (exit 1 = bloqueado)
uv run python -m eval.gate \
    --candidate eval/scorecards/candidate.json \
    --baseline  eval/scorecards/production.json
```

Uma promoção bloqueada se parece com isto:

```
=== eval.gate: extraction-v2-experimental vs extraction-v1 ===

  PROMOTION BLOCKED for extraction-v2-experimental:

  ✗ false_auto_approve_rate: 0.025 > 0.000+0.01
  ✗ critical_field_accuracy: 0.000 < 0.85
  ✗ decision_accuracy: 0.625 < 0.700 (baseline-0.05)

Exit code: 1
```

O dataset hoje traz um fixture por slice, suficiente para demonstrar o gate de ponta a ponta. Expandi-lo é o próximo passo óbvio para significância estatística.

## Trade-offs

Toda escolha de design aqui tem um custo, e nomeá-lo é parte do ponto.

- **Determinismo acima de flexibilidade.** Colocar checagem de CNPJ, somas e política em código deixa o sistema previsível e auditável, mas significa que uma regra nova exige mudança de código e migration, não edição de prompt. Isso é intencional: regras que movem dinheiro não vivem num prompt.
- **Escalar acima de taxa de automação.** Preferir `human_review` na dúvida mantém o `false_auto_approve_rate` baixo ao custo de uma taxa de auto-aprovação menor. Em operações financeiras, uma revisão perdida é muito mais cara que uma a mais.
- **arq + Redis em vez de Temporal, por ora.** O arq cobre o pipeline atual com clareza. Workflows longos com pausas humanas de dias vão precisar de Temporal; a arquitetura deixa espaço para essa migração sem reescrever a lógica de domínio.
- **Pipeline com sensação síncrona em vez de event sourcing em tudo.** O log de auditoria dá linhagem sem o peso operacional de um sistema event-sourced. Se a reconciliação ficar mais complexa, essa fronteira pode precisar se mover.
- **Um fixture por slice em vez de um benchmark grande.** Isso prova que o loop de LLMOps funciona, não que o modelo é acurado para produção. O dataset é a primeira coisa a crescer antes de um deploy real.

## Roadmap

O produto foi construído em quatro fases, cada uma com um critério de sucesso concreto como gate.

| Fase | Escopo | Status |
|---|---|---|
| 1. Core MVP | Upload, classificação, extração, validação, detalhe do caso, fila de revisão, audit events | Concluída |
| 2. Workflow intelligence | Engine de política, confiança por campo, aprovar/rejeitar/editar, reconciliação | Concluída |
| 3. Camada de LLMOps | Framework de eval, CLI de gate, scorecards, prompt registry ligado ao runtime, tracing | Concluída |
| 4. Enterprise polish | JWT + RBAC, queries por organização, dashboards, export de auditoria, os cinco canais de entrada | Concluída |

A seguir, em ordem de prioridade:

- Expandir o dataset de avaliação além de um fixture por slice.
- Migrar workflows longos com pausa humana para Temporal.
- Aprofundar a reconciliação contra dados reais de referência de ERP.
- Adicionar o assistente de revisão conversacional (perguntar "por que isto foi escalado?" e receber resposta rastreável).

---

## Como rodar

Requisitos: Python 3.12+, Node 20+, `uv`, `pnpm`, Docker.

```bash
corepack enable pnpm        # se ainda não estiver habilitado

uv sync                     # deps Python
pnpm install                # deps frontend

docker compose -f infra/docker-compose.dev.yml up -d   # postgres + redis + storage
uv run alembic upgrade head                            # migrations
```

Rodar os três processos:

```bash
uv run uvicorn apps.api.main:app --reload     # API em :8000
uv run arq workers.pipeline.WorkerSettings    # worker do pipeline
pnpm --filter web dev                         # frontend em :3000
```

Quality gates (rode antes de considerar uma tarefa concluída):

```bash
make check      # ruff + mypy + pytest + lint/typecheck do front
```

### Contas de demo

Três usuários são criados na inicialização da API (senha `demo123`):

| E-mail | Papel | Permissões |
|---|---|---|
| `analyst@demo.com` | analyst | Ler casos, submeter revisões de edição |
| `approver@demo.com` | approver | Acesso de analyst + aprovar/rejeitar + export de auditoria |
| `admin@demo.com` | admin | Acesso total + criar/promover prompts + dashboard |

```bash
# Login e captura do JWT
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@demo.com","password":"demo123"}' | jq -r .access_token)

# Upload de um documento
curl -s -X POST http://localhost:8000/api/v1/documents \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@/caminho/para/nota.pdf"

# Listar casos (escopado por organização)
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/cases
```
