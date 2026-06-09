# Engram — Documentação Completa do Projeto

> Sistema de memória persistente para desenvolvimento de software com Claude Code.
> Versão 3.0 · 118 testes · Repositório: github.com/ianbenicio/engram_v03

---

## Índice

1. [O que é e por que existe](#1-o-que-é-e-por-que-existe)
2. [Filosofia central: curadoria vs verbatim](#2-filosofia-central-curadoria-vs-verbatim)
3. [Visão geral da arquitetura](#3-visão-geral-da-arquitetura)
4. [Os atores do sistema](#4-os-atores-do-sistema)
5. [Modelo de dados](#5-modelo-de-dados)
6. [Write path — escrita 100% Python](#6-write-path--escrita-100-python)
7. [Read path — leitura dual-path](#7-read-path--leitura-dual-path)
8. [Gestão de contexto e handoff de sessão](#8-gestão-de-contexto-e-handoff-de-sessão)
9. [As 6 features inspiradas no Graphify](#9-as-6-features-inspiradas-no-graphify)
10. [Melhorias do backlog (BL-01 a BL-04)](#10-melhorias-do-backlog-bl-01-a-bl-04)
11. [As 6 ferramentas MCP](#11-as-6-ferramentas-mcp)
12. [A CLI](#12-a-cli)
13. [Configuração](#13-configuração)
14. [Segurança](#14-segurança)
15. [Estratégia de testes](#15-estratégia-de-testes)
16. [Estrutura de arquivos](#16-estrutura-de-arquivos)
17. [Instalação e uso](#17-instalação-e-uso)
18. [Decisões de design e trade-offs](#18-decisões-de-design-e-trade-offs)
19. [Histórico de construção](#19-histórico-de-construção)

---

## 1. O que é e por que existe

**Engram** é um servidor **MCP** (Model Context Protocol) que dá a Claude Code uma **memória persistente e contínua** entre sessões de desenvolvimento.

### O problema

A cada nova conversa com o Claude Code, todo o conhecimento acumulado precisa ser reconstruído do zero: decisões de arquitetura tomadas, bugs já resolvidos, padrões identificados, o "porquê" de cada escolha. Isso é:

- **Caro em tokens** — re-explicar contexto a cada sessão consome janela de contexto.
- **Lento** — o desenvolvedor repete informação que o agente "deveria saber".
- **Propenso a inconsistência** — sem memória, o agente pode contradizer decisões passadas.

### A solução

Um **vault estruturado no Obsidian** que funciona como segundo cérebro do desenvolvedor e do agente:

- Conhecimento é **capturado** durante o desenvolvimento (decisões, bugs, patterns).
- **Organizado** semanticamente com tags hierárquicas, wikilinks e TL;DRs.
- **Recuperado** de forma eficiente quando necessário, via busca dupla (texto + semântica).

### O nome

"Engram" = o **traço físico que uma memória deixa no cérebro**. É a metáfora exata: cada nota é um traço persistente de memória do processo de desenvolvimento.

---

## 2. Filosofia central: curadoria vs verbatim

Esta é a decisão mais importante do projeto e o que diferencia o Engram de sistemas concorrentes (como MemPalace).

| Abordagem | Como funciona | Trade-off |
|-----------|---------------|-----------|
| **Verbatim** (MemPalace) | Guarda TUDO que foi dito, sem resumir; busca semântica acha depois | Recall máximo, mas ruído + custo de armazenamento + polui contexto |
| **Curadoria** (Engram) | Guarda só conhecimento **destilado** (decisões, bugs, patterns), com TL;DR de ~15 palavras | Precisão máxima, ~200 tokens por consulta, legível por humano |

**Engram é precision-first.** Claude decide o que vale a pena lembrar e destila na escrita. O resultado é uma memória de "engenheiro sênior" — lembra só o que importa, já processado — em vez de uma "memória fotográfica" que lembra tudo cru.

Consequências dessa filosofia em todo o sistema:
- O **write path** exige curadoria na origem (Claude sintetiza, valida tags, gera TL;DR).
- O **mining** (importação retroativa) produz **drafts** para revisão, nunca despeja verbatim.
- As notas são **markdown legível** no Obsidian (não blobs opacos de banco vetorial).

---

## 3. Visão geral da arquitetura

### Padrão: Monólito Modular

Um único pacote Python. Um processo serve tanto o servidor MCP quanto a CLI. Estado compartilhado (conexão SQLite, config) via módulos `core/`.

**Por que monólito e não microkernel/plugins/clean-architecture?**
- Projeto de 1-2 desenvolvedores — não precisa de plugin system.
- **Eficiência é prioridade** — menos abstrações = menos overhead.
- YAGNI — se crescer, refatora depois. Abstração prematura é desperdício.

### Princípio de módulos

Cada módulo em `core/` tem **uma responsabilidade**, é testável isoladamente, e tem menos de ~300 linhas. Todos compartilham `db.py` (conexão) e `config.py` (settings).

```
Claude Code  ──MCP──▶  Engram Server (Python)  ──▶  Obsidian Vault (.md)
                              │                  ──▶  SQLite (FTS5 + sqlite-vec)
                              └──Path B──▶  Ollama (bge-m3 + qwen3) [opcional]
```

### Os três pilares

1. **Escrita de memória** — Claude identifica conhecimento novo, sintetiza nota, MCP valida e salva. **Zero LLM** no write path.
2. **Leitura e consulta (dual-path)** — router decide entre busca leve (FTS5, zero LLM) e busca pesada (embeddings + síntese Qwen).
3. **Gestão de sessão** — monitora tamanho do contexto, dispara handoff automático em 50%, retoma na sessão seguinte.

---

## 4. Os atores do sistema

| Ator | Papel |
|------|-------|
| **Claude Code** | Orquestrador. Raciocina, decide quando salvar e buscar. Sintetiza notas com contexto completo da conversa. |
| **Engram MCP Server** (Python) | Interface entre Claude Code e o vault. Expõe 6 ferramentas. Write 100% Python; read roteia Path A/B. Rate-limited. |
| **Ollama** (local, opcional) | `bge-m3` (embeddings) + `qwen3` (síntese). Sistema degrada para Path A se offline. |
| **Obsidian Vault** | Banco de memória persistente. Markdown navegável por humano (Graph View). Notas nunca deletadas (`status: archived` filtra). |
| **SQLite + FTS5 + sqlite-vec** | Índice de busca. Metadados + full-text + busca vetorial. Invisível ao usuário. |

---

## 5. Modelo de dados

### 5.1 Tipos de nota (7 ativos, 11 preparados)

```python
class NoteType(str, Enum):
    # v3.0 ativos
    DECISION = "decision"      # decisão de arquitetura/técnica (ADR)
    BUG = "bug"                # bug resolvido + causa raiz
    PATTERN = "pattern"        # padrão de código identificado
    CONTEXT = "context"        # contexto de projeto/módulo
    RUNBOOK = "runbook"        # procedimento operacional
    SESSION = "session"        # handoff de sessão
    CONCEPT = "concept"        # conceito/glossário
    # v3.1 preparados (folder + template existem; desabilitados no config)
    POST_MORTEM = "post-mortem"
    EXPERIMENT = "experiment"
    REFACTORING = "refactoring"
    METRIC = "metric"
```

**Por que 7 ativos mas 11 preparados?** Decisão deliberada: começar enxuto (evita over-engineering de tipos nunca usados), mas deixar o enum + folder mapping + templates prontos. Ativar os 4 restantes = adicionar à lista `enabled_types` no config. Custo zero para preparar, ativação trivial.

Os tipos ativos são **config-driven** (`engram.toml` → `[types] enabled`), não hardcoded.

### 5.2 Confidence enum (inspirado no Graphify)

```python
class Confidence(str, Enum):
    FACT = "fact"             # verificado: teste passou, decisão tomada
    INFERENCE = "inference"   # derivado de análise
    HYPOTHESIS = "hypothesis" # não confirmado
```

Campo **obrigatório** no frontmatter. Mapeado do Graphify (EXTRACTED/INFERRED/AMBIGUOUS). Permite que a recuperação distinga **fatos verificados** de **suposições**. O Path B mostra o confidence de cada fonte na síntese.

### 5.3 Schema do frontmatter

**Obrigatórios:** `id, title, tldr, type, confidence, status, created, updated, author, scope, tags`.

**Prefixos de tag obrigatórios:** `tipo/`, `maturidade/`, `dominio/` (toda nota deve ter um de cada).

**Opcionais:** `subtype, parent, project, module, related[], implements, supersedes, code_refs, session_id, confidentiality`.

### 5.4 Schema SQLite

```sql
CREATE TABLE notes (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    tldr TEXT,
    type TEXT NOT NULL,
    subtype TEXT,
    confidence TEXT NOT NULL,        -- NOVO (Graphify)
    scope TEXT DEFAULT 'project',
    project TEXT,
    module TEXT,
    status TEXT DEFAULT 'active',    -- suporta 'archived' (cold storage futuro), 'draft' (mining)
    created TEXT NOT NULL,
    updated TEXT NOT NULL,
    author TEXT DEFAULT 'claude',
    tags_json TEXT,
    content_hash TEXT,               -- SHA-256[:32] para dedup
    file_path TEXT,                  -- qualquer path (cold storage futuro = troca de path)
    confidentiality TEXT DEFAULT 'internal',
    schema_version INTEGER DEFAULT 1
);

-- Full-text search (busca por palavra-chave)
CREATE VIRTUAL TABLE notes_fts USING fts5(
    note_id UNINDEXED, title, tldr, tags_text, body_snippet
);

-- Busca vetorial (semântica), criada em runtime após load_extension('vec0')
-- notes_vec: vec0(note_id TEXT PRIMARY KEY, embedding float[1024])  -- bge-m3
```

**Detalhe importante — FTS5 sem triggers:** a tabela FTS é populada **via Python** (delete + insert no `upsert_note`), não por triggers SQL. Isso garante que `tags_text` e `body_snippet` sejam sempre populados corretamente e dá controle explícito sobre a sincronização.

**Future-proofing do cold storage:** `status` já suporta `archived` e `file_path` aceita qualquer caminho. Mover uma nota para armazenamento frio no futuro = trocar o path + filtro, sem mudança de schema. Cold storage foi **adiado** (YAGNI até o vault passar de ~500 notas), mas o schema já está pronto.

---

## 6. Write path — escrita 100% Python

### 6.1 Princípio: zero LLM na escrita

Claude faz o trabalho **semântico** (escolhe type, tags, escreve o conteúdo, gera o TL;DR). O Python faz o trabalho **mecânico** (valida, formata, deduplica, salva, indexa). Nenhum LLM intermediário no write path → custo zero de inferência ao salvar.

### 6.2 Por que cortamos o "sweeper" (decisão-chave)

A versão anterior (v2.2) usava um `_pending/` + uma thread daemon ("sweeper") que verificava a cada 5s se o Obsidian estava ocioso antes de mover arquivos para a pasta final.

**Cortamos.** Resolvia um problema raro (Obsidian editando exatamente a nota que Claude está salvando) com custo alto: thread extra, race conditions, bookkeeping de `.meta.json`, latência de 5s, consistência adiada do SQLite.

**Substituição — escrita atômica + lock:**

1. **portalocker** — lock exclusivo cross-platform durante a escrita.
2. **Escrita atômica** — escreve em `.tmp`, depois `os.replace()` (atômico no Windows + POSIX). O Obsidian nunca vê arquivo parcial. Um crash no meio deixa o `.tmp`, nunca um alvo corrompido.

```python
tmp = target.with_suffix(target.suffix + ".tmp")
tmp.write_text(markdown, encoding="utf-8")
os.replace(tmp, target)   # atômico
```

**Os 4 cenários de conflito com Obsidian, tratados:**

| Cenário | Tratamento |
|---------|-----------|
| Obsidian com nota X aberta, Engram atualiza X | `os.replace` escreve arquivo completo; Obsidian detecta mudança externa e recarrega (comportamento nativo). Sem corrupção. |
| Humano edita X no Obsidian enquanto Engram escreve X | portalocker serializa. `vault.update` lê o arquivo atual antes de escrever, preservando edições humanas em outros campos. |
| Crash no meio da escrita | `.tmp` órfão; alvo intacto. Startup limpa `.tmp` com mais de 60s. |
| Escritas concorrentes do Engram (multi-agente futuro) | portalocker serializa. |

### 6.3 Pipeline do `vault_save`

```
Claude → vault.save(note_data, body)
  1. rate_limit check (30/60s)
  2. gera ULID se sem id
  3. set timestamps + defaults (confidence obrigatório, sem default silencioso)
  4. valida type habilitado no config
  5. valida campos obrigatórios (incl. confidence)
  6. valida prefixos de tag (tipo/, maturidade/, dominio/)
  7. valida tags contra vocabulário (meta/tags.md)
  8. valida módulo contra _index.md do projeto (warning, não-bloqueante)  [CR-03]
  9. valida tamanho do TL;DR (≤ 20 palavras, warning)
  10. computa hash SHA-256[:32] + checa duplicata
  11. valida wikilinks em related[] (SQLite-first, fallback filesystem)
  12. determina path final (type → folder mapping)
  13. formata markdown (YAML frontmatter + body)
  14. acquire lock → escrita atômica (.tmp → os.replace) → release lock
  15. insert SQLite + FTS5 (Python) + EMBEDDING (se Ollama on)  [fix crítico]
  16. log activity.jsonl
  17. retorna {note_id, path, warnings}
```

**O fix crítico (passo 15):** na implementação original, os embeddings **nunca eram gravados** em `notes_vec` — o que tornava Path B e clustering mortos em produção (os testes passavam porque populavam vetores manualmente). Corrigido: `embed_and_store` é chamado em todos os caminhos de escrita (save, update, handoff, import, reindex). Se o Ollama está offline, ele **pula graciosamente** (a nota é salva sem vetor; FTS5 ainda funciona).

### 6.4 `vault_update` — edição parcial

Campos **imutáveis**: `id, created, type, subtype, parent`. Lê a nota existente, aplica updates de campo, preserva campos não tocados (incl. edições humanas no corpo), recomputa hash só se o corpo mudou, re-valida tags/wikilinks alterados, escrita atômica, atualiza SQLite.

---

## 7. Read path — leitura dual-path

O coração da eficiência. Um **router** decide automaticamente entre dois caminhos.

### 7.1 O router

```
depth == "deep"                → Path B (pesado)
multi-projeto ou "*"           → Path B
intenção semântica (18 regex)  → Path B   (bilíngue PT + EN)
FTS5 match_count > 5           → Path B
caso contrário                 → Path A (leve)
```

Os 18 padrões semânticos detectam queries que precisam de síntese (não só lookup): `impacto`, `relação entre`, `migrar`, `por que`, `comparar`, `histórico de`, `alternativas` — e equivalentes em inglês (`impact`, `why did`, `compare`, etc.).

### 7.2 Path A — leve (~70% das queries)

Busca FTS5 por tags + projeto + keywords. Retorna **TL;DRs concatenados** das notas relevantes. **Zero LLM.** ~200 tokens.

Filtros: status (exclui `archived` e `draft` por padrão), type, project, tags, cold storage.

**[BL-01] Recency boost:** quando `recency_weight > 0`, o Path A faz over-fetch (limit×3 candidatos), re-ordena por uma mistura de score FTS normalizado + fator de recência (decaimento exponencial, half-life 90 dias), e corta para top-k. Notas recentes sobem no ranking. Backward-compatible: `weight=0` ou `config=None` → ordem FTS pura.

### 7.3 Path B — pesado (~30% das queries)

```
1. get embedding da query (Ollama bge-m3)
   └─ Ollama offline → fallback total para Path A
2. busca vetorial KNN: WHERE embedding MATCH ? AND k = ?  (sqlite-vec)
3. filtra confidentiality: restricted (NUNCA enviado ao LLM externo)
4. [BL-02] rerank opcional: re-score por vec_sim + keyword overlap + recência
5. lê corpo das top-7 notas
6. síntese Qwen (~400 palavras, prompt bilíngue, mostra confidence por fonte)
   └─ Qwen offline → fallback: Path A + top-3 notas inteiras (~800-1500 tokens)
```

### 7.4 Cadeia de fallback — nunca bloqueia

| Falha | Comportamento |
|-------|--------------|
| Ollama embeddings offline | Path A puro |
| Qwen síntese offline | Path A + top-3 notas inteiras |
| Lock timeout (5s) | Erro explícito, Claude tenta de novo |
| Validação falha | Erro estruturado + amostra do vocabulário |
| Embedding falha ao salvar | Nota salva sem vetor; FTS5 ainda funciona |

O sistema **degrada graciosamente** — nunca trava por causa de um serviço externo indisponível.

---

## 8. Gestão de contexto e handoff de sessão

```
PreToolUse hook (a cada tool call):
  lê flag do tempdir → estima tokens incrementais → acumula → escreve flag
  < 35%   normal
  35-50%  warning: "seja conciso, prepare handoff"
  ≥ 50%   crítico: "inicie handoff AGORA" → Claude chama vault.handoff()

vault.handoff(): gera nota type:session (decisões abertas, arquivos ativos,
  próximos passos, branch git) → salva em sessoes/handoff-{id}.md

Nova sessão:
  SessionStart hook → acha handoff mais recente (por projeto, por mtime)
    → injeta via additionalContext → Claude começa com ~8% de contexto vs ~50% no fim
```

**Por que thresholds 35%/50% (e não 50%/65%)?** Claude degrada a qualidade do raciocínio a partir de ~40% do contexto. Sair cedo com contexto limpo é melhor que espremer até perder coerência. A nova sessão retoma exatamente de onde parou.

---

## 9. As 6 features inspiradas no Graphify

O Graphify transforma codebases em knowledge graphs. Analisamos e incorporamos 6 ideias, sem comprometer a essência curation-first.

| # | Feature | Como integra | Interface |
|---|---------|--------------|-----------|
| 1 | **Confidence tags** | enum `fact/inference/hypothesis` no frontmatter + SQLite. Validator exige. Path B mostra. | MCP (save/update) |
| 2 | **SHA256 incremental** | `reindex` compara hash do arquivo vs SQLite; pula se igual. Zero reprocessamento. | CLI |
| 3 | **Watch mode** | watchdog monitora o vault; edição manual no Obsidian dispara reindex de um arquivo (hash-checked). | CLI (`engram watch`) |
| 4 | **Hub notes** | `hubs.py` = centralidade por wikilinks de entrada + frequência de query. | MCP (`vault.status`) |
| 5 | **Graphify import** | `import-graph graph.json` → notas context; edges → related[]; tags Graphify → confidence. | CLI |
| 6 | **Community clustering** | agrupa notas por similaridade de embedding (cosine-threshold) → `_clusters.md` por projeto. | CLI (`engram cluster`) |

**Features 2,3,5,6 são CLI-first** — não precisam do Claude, então custam **zero tokens** (prioridade: economia).

**Sobre clustering:** o spec pedia algoritmo Leiden. Optamos por **connected-components com threshold de cosseno** (union-find) — determinístico, testável, zero dependência C-extension. Para vaults pequenos a qualidade é equivalente. `python-igraph`/`leidenalg` ficam como extra opcional `[clustering]` para quando o vault crescer o suficiente para precisar de otimização de modularidade.

---

## 10. Melhorias do backlog (BL-01 a BL-04)

Inspiradas na análise do **MemPalace** (sistema concorrente de memória local-first), filtradas por eficiência + estrutura, sem adotar verbatim.

### BL-01 — Recency boost no Path A (✅)

Path A ordenava só por rank FTS5. Adiciona boost de recência: notas recentes sobem. Melhor ranking → menos escalações para o Path B (pesado) → economia de tokens. Pure Python, zero LLM, sem mudança de schema (usa coluna `updated`). Config: `[retrieval] recency_weight=0.2, recency_halflife_days=90`.

### BL-02 — Cheap rerank no Path B (✅)

Path B ordenava só por distância vetorial. O rerank re-pontua os candidatos com `0.5·vec_sim + 0.3·keyword_overlap + 0.2·recência` antes da síntese — mais precisão, menos contexto irrelevante enviado ao Qwen. **Zero LLM** (rerank é Python determinístico). Default off (`[retrieval] rerank=false`). O LLM-rerank do MemPalace foi **rejeitado** — chamada LLM extra contradiz a prioridade de economia.

### BL-03 — Mining mode (✅)

Importação retroativa de arquivos/transcripts como notas **DRAFT** em staging `_mined/`. Curation-first: produz candidatos para revisão (`status: draft`, `confidence: hypothesis`), nunca despeja verbatim. Drafts são excluídos das queries padrão; promoção via `vault.update status→active`. CLI: `engram mine <source> <project> [--mode files|convos]`. Zero LLM, totalmente local.

### BL-04 — Benchmark harness (✅)

Mede objetivamente a qualidade da recuperação: **Path A Recall@5**, **router accuracy**, **Path B Recall@5** (skip gracioso se Ollama offline). Dataset seedado de 6 queries sobre 4 notas conhecidas. CLI `engram bench` (vault temp efêmero, dev-only). Resultado: Path A R@5=1.0, router accuracy=1.0.

**Finding documentado:** o Path A Recall é escopado a queries keyword (lightweight). Queries semânticas falham o implicit-AND do FTS5 **propositalmente** — é trabalho do Path B. Incluí-las conflataria "Path A é fraco em semântica" (esperado) com "retrieval quebrado".

### Ideias rejeitadas do MemPalace
- **Verbatim storage** — viola a essência curation-first.
- **Temporal validity windows** — redundante com `supersedes`/`superseded_by`.
- **Palace metaphor (Wings/Rooms/Drawers)** — overhead conceitual; projetos/tags são mais diretos.
- **29 ferramentas** — contradiz economia; 6 ferramentas focadas batem 29.
- **ChromaDB** — sqlite-vec basta, menos deps, e Obsidian markdown é legível.

---

## 11. As 6 ferramentas MCP

| Ferramenta | Propósito | Path |
|-----------|-----------|------|
| `vault.save` | Cria nota nova | Write |
| `vault.update` | Edição parcial | Write |
| `vault.query` | Query padrão (router decide A/B) | Read |
| `vault.deep_query` | Força Path B (semântico) | Read |
| `vault.status` | Estatísticas do vault + hub notes | Read |
| `vault.handoff` | Salva estado da sessão | Write |

Todas passam por **rate limiting** (30 chamadas / 60s por ferramenta, in-memory sliding window). Expostas via `FastMCP` (SDK oficial MCP), entry-point `engram-server`.

---

## 12. A CLI

Operações que **não precisam do Claude** → CLI → custo zero de tokens.

```bash
engram status                            # estatísticas + hub notes
engram reindex                           # rebuild incremental do índice SQLite (hash-skip)
engram watch                             # auto-reindex em edições externas (watchdog)
engram import-graph graph.json proj      # importa um graph.json do Graphify
engram cluster proj --threshold 0.75     # clusteriza notas → _clusters.md
engram mine ./src proj                   # minera *.md/*.txt → notas DRAFT (_mined/)
engram mine ./convos proj --mode convos  # minera *.jsonl transcripts → drafts
engram bench                             # benchmark de recuperação (R@5 + router accuracy)
```

Implementada com `typer`. Entry-point `engram`.

---

## 13. Configuração

```toml
# engram.toml
[vault]
root = "C:/Users/ianfl/dev-vault"   # default ~/.engram/vault ; backward-compatible

[types]
enabled = ["decision","bug","pattern","context","runbook","session","concept"]

[embeddings]
provider = "ollama"
model = "bge-m3"
endpoint = "http://localhost:11434"

[synthesis]
model = "qwen3:7b"

[limits]
rate_calls = 30
rate_window_seconds = 60
lock_timeout_seconds = 5
context_warning_pct = 35
context_critical_pct = 50

[retrieval]
recency_weight = 0.2          # BL-01: boost de recência no Path A (0 desativa)
recency_halflife_days = 90
rerank = false                # BL-02: rerank no Path B (default off)
```

Override via env: `ENGRAM_VAULT_ROOT`, `ENGRAM_OLLAMA_ENDPOINT`. **Vault configurável** = pode apontar para um vault existente (backward-compatible, zero migração) ou criar um novo. Default `~/.engram/vault`.

---

## 14. Segurança

Auditada no review final. Veredicto: **PASS**.

- **Notas `confidentiality: restricted` NUNCA chegam ao LLM externo.** O Path B filtra os candidatos restricted **antes** de ler corpos ou montar o contexto de síntese. Só notas seguras vão ao Qwen. Coberto por teste (`test_path_b_excludes_restricted`).
- **Sem SQL injection no FTS.** Todos os valores de `MATCH` são parâmetros vinculados com `"` duplicado; todos os filtros são parametrizados. Nenhuma interpolação de input de usuário em SQL.
- **Sem vazamento de segredos/paths.** Resultados retornam ids/paths dentro do vault; nenhuma credencial. O endpoint do Ollama vem do config, não é ecoado.
- **Lock crash-safe.** `portalocker` com try/finally (unlock + close), deadline loop. Escrita atômica (`.tmp` → `os.replace`) é crash-safe; limpeza de `.tmp` órfão existe.
- **Threading.** Conexão SQLite com `check_same_thread=False` para o FastMCP poder despachar de threads de worker.

---

## 15. Estratégia de testes

- **TDD rigoroso** — todo módulo: teste escrito **antes** da implementação (falha → implementa → passa → commit).
- `pytest` + `pytest-asyncio`. Vault temporário via fixture `tmp_path`. **Mock do Ollama** (sem dependência externa no CI).
- Cobertura: ≥ 80% em `core/`, 100% em validator + router (lógica crítica).
- Cada ferramenta MCP tem teste de contrato (schema input/output).
- Matriz de features: confidence enum, hash incremental, ranking de hubs, determinismo de cluster, roundtrip de import, crash safety de escrita atômica, cenários de conflito Obsidian, recency boost, rerank, mining drafts, benchmark offline.
- **118 testes**, todos verde.

---

## 16. Estrutura de arquivos

```
H:\Engram\
├── engram/
│   ├── __init__.py
│   ├── config.py          # load config (toml + env), paths, constantes
│   ├── models.py          # Pydantic: NoteData, QueryRequest, NoteType, Confidence
│   ├── server.py          # servidor FastMCP — entry point, 6 ferramentas
│   ├── cli.py             # CLI typer: status, reindex, watch, import-graph, cluster, mine, bench
│   ├── bench.py           # BL-04 benchmark harness
│   ├── core/
│   │   ├── db.py          # conexão SQLite, schema, sqlite-vec loading
│   │   ├── validator.py   # validação de campos/tags/wikilinks/confidence/module
│   │   ├── indexer.py     # hash + upsert SQLite/FTS5 + dedup
│   │   ├── fsio.py        # escrita atômica + format markdown + cleanup .tmp
│   │   ├── locking.py     # lock portalocker (context manager)
│   │   ├── paths.py       # resolução type→folder + activity log
│   │   ├── writer.py      # vault_save + vault_update
│   │   ├── embeddings.py  # Ollama bge-m3 + qwen3 (falha graciosa) + embed_and_store
│   │   ├── router.py      # decisão Path A vs B
│   │   ├── reader.py      # Path A (FTS5) + Path B (vetor + síntese) + recency + rerank
│   │   ├── rate_limit.py  # rate limiter sliding-window in-memory
│   │   ├── hubs.py        # vault_status + ranking de hub notes
│   │   ├── handoff.py     # nota de handoff de sessão + find latest
│   │   ├── clustering.py  # community detection → _clusters.md
│   │   ├── watcher.py     # watchdog reindex incremental
│   │   ├── reindex.py     # rebuild full/incremental do SQLite
│   │   └── mining.py      # BL-03 mining de files/transcripts → drafts
│   ├── importers/
│   │   └── graphify.py    # graph.json → notas context
│   └── hooks/
│       ├── pre_tool_use.py    # monitor de contexto (35%/50%)
│       └── session_start.py   # injeção de handoff
├── scripts/
│   └── migrate_v2_to_v3.py    # backfill de confidence (migração v2.2→v3.0)
├── tests/                     # 1 arquivo por módulo + E2E + recency + rerank + mining + bench
├── docs/
│   ├── specs/2026-06-01-engram-v3-design.md   # spec de design
│   ├── plans/2026-06-01-engram-v3-implementation.md  # plano de implementação (30 tasks TDD)
│   ├── engram-v3.md           # doc de sistema
│   ├── backlog.md             # backlog (BL-01..04 done, CR-01..04 done)
│   └── PROJETO-ENGRAM.md      # este documento
├── pyproject.toml
├── engram.toml.example
├── claude-config-snippet.json
└── README.md
```

---

## 17. Instalação e uso

### Instalar

```bash
cd H:\Engram
pip install -e ".[dev]"
# opcional, clustering Leiden real:
# pip install -e ".[clustering]"
```

### Configurar

Copie `engram.toml.example` para `engram.toml` e ajuste `vault.root`. Ou use `ENGRAM_VAULT_ROOT`.

### Rodar o servidor MCP

```bash
engram-server
```

Registre no Claude Code `.claude/settings.json` (ver `claude-config-snippet.json`):

```json
{
  "mcpServers": { "engram": { "command": "engram-server" } },
  "hooks": {
    "PreToolUse": [{ "matcher": "*", "command": "python -m engram.hooks.pre_tool_use" }],
    "SessionStart": [{ "command": "python -m engram.hooks.session_start" }]
  }
}
```

### Migrar um vault v2.2 existente

```bash
python scripts/migrate_v2_to_v3.py C:/Users/ianfl/dev-vault          # dry run
python scripts/migrate_v2_to_v3.py C:/Users/ianfl/dev-vault --apply  # escreve
engram reindex
```

A migração faz backfill do campo `confidence`: `decision`/`bug` verificados → `fact`; `pattern`/`concept` → `inference`; itens abertos → `hypothesis`.

### Testar

```bash
pytest                 # todos
pytest --cov=engram    # com cobertura
```

---

## 18. Decisões de design e trade-offs

| Decisão | Escolha | Por quê |
|---------|---------|---------|
| Arquitetura | Monólito modular | 1-2 devs, eficiência > abstração, YAGNI |
| Write path | 100% Python, sem sweeper | Custo zero LLM; atomic write + lock cobrem o risco real com simplicidade |
| Sweeper | Cortado | Resolvia problema raro com custo alto; `os.replace` + portalocker bastam |
| Tipos de nota | 7 ativos, 11 preparados | Enxuto agora, ativação trivial depois |
| Cold storage | Adiado, schema pronto | Premature optimization até ~500 notas |
| Embeddings | Ollama local only | Zero custo, offline, máxima economia |
| Interface | MCP + CLI mínima | CLI economiza tokens em ops que não precisam do Claude |
| Clustering | Cosine-threshold (não Leiden) | Determinístico, testável, sem dep C-extension |
| Rerank | Keyword+recência, sem LLM | LLM-rerank contradiz economia |
| Mining | Drafts em staging | Curation-first; nunca verbatim automático |
| Filosofia | Precision-first (curadoria) | ~200 tokens/query, legível, sem ruído |

---

## 19. Histórico de construção

O projeto foi construído com **metodologia spec-driven + TDD** usando o framework superpowers (brainstorming → spec → plano → execução subagent-driven).

**Fases (F0–F5), 30 tasks TDD:**
- **F0 Scaffold** — pacote, config, models, schema DB, fixtures
- **F1 Write path** — validator, indexer, atomic write, lock, paths, save, update
- **F2 Read path** — embeddings, router, Path A, Path B, rate limiter
- **F3 Server** — handoff, status+hubs, FastMCP (6 tools), hooks
- **F4 Graphify features** — reindex, watcher, import, clustering
- **F5 Final** — CLI, migração, docs

**Qualidade — defeitos pegos por subagentes (sem invenção):**
- Task 2.3: teste com `MATCH 'proj'` em coluna não-indexada → corrigido.
- **Review final: bug CRÍTICO** — embeddings nunca gravados em `notes_vec`, tornando Path B + clustering mortos em produção. Corrigido com `embed_and_store` em todos os write paths + 2 testes E2E + fix de threading.

**Follow-ups de review (CR-01..04):**
- CR-01: `upsert_note` lança `ValueError` em chaves faltantes; reindex pula malformadas.
- CR-02: hub_notes resolve `[[Title]]` → id (não só `[[id]]`).
- CR-03: validação de módulo contra `_index.md` (warning não-bloqueante).
- CR-04: remoção de import morto.

**Melhorias (BL-01..04):** recency boost, cheap rerank, mining mode, benchmark harness.

**Estado final:** 118 testes verde, backlog esgotado, publicado em github.com/ianbenicio/engram_v03.

---

*Engram v3.0 — memória persistente para desenvolvimento. Construído com curadoria, não acumulação.*
