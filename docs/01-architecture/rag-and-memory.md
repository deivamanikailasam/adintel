# RAG, vector search and memory

> **RAG in plain words:** instead of asking a model to remember facts, you look up the relevant
> documents first and make it answer from them. It is the difference between asking someone to
> recall a contract and handing them the contract.

**The golden rule: RAG retrieves context and narrative; the database supplies numbers.** Every figure
in a client report comes from `metrics_daily`, never from a retrieved chunk.

## What gets indexed (`kb_chunks`)

Past reports, brand guidelines, agency playbooks, incident write-ups (what went wrong and what fixed
it), nightly campaign narratives and ad-platform docs. Chunking differs by type
(`src/adintel/rag/chunking.py`):

- **Prose (playbooks, guidelines):** semantic chunks of 400–800 tokens with 15% overlap, split on
  headings and paragraph boundaries. Fixed-size chunking can split "increase budget by 30%" from its
  condition "if impression share is below 60%", producing confidently wrong advice.
- **Reports:** one chunk per section, since sections stand alone.
- **Number tables: never embedded.** A nightly job turns each campaign period into a short sentence
  (`narratives.py`) and that sentence is embedded instead.

## The retrieval pipeline (`src/adintel/rag/retriever.py`)

1. Agent intent becomes a search query.
2. Embed it (cached by content hash).
3. **Hybrid search:** vector similarity + BM25 keyword search, merged with reciprocal rank fusion,
   weighted **0.65 semantic / 0.35 keyword**. A **mandatory pre-filter** on tenant, brand, doc type,
   date and `is_active` runs *inside* the query, never after it.
4. Over-fetch the top 25.
5. Rerank with a cross-encoder.
6. Keep the top 6.
7. Put them in the prompt with their source info, **fenced as untrusted content**.
8. **Grounding check** after generation: every number must match the database (blocking), and every
   claim should trace to a chunk (a warning to the reviewer).

Why hybrid? Vector search misses exact names ("AS-B Retargeting Cold"); keyword search misses
meaning ("why did our costs go up" vs "Diagnosing CPA inflation"). Why rerank? Bi-encoders are fast
but approximate; a cross-encoder reads query and document together — accurate but slow — so fetch 25
cheaply and rerank to 6. Why filter inside the query? Post-filtering silently loses recall and, more
importantly, pre-filtering makes tenant isolation **structural**.

### Local vs production

| | Local | Production |
|-|-------|-----------|
| Vector search | Atlas Local `$vectorSearch` with `filter`, or brute-force cosine over the tenant-filtered set (memory backend) | Atlas Vector Search, 1,024-dim, int8 quantization, `numCandidates ≈ 12 × limit` |
| Keyword search | In-process BM25 over the tenant-filtered candidate set | Atlas Search + `$rankFusion` |
| Fusion | RRF in Python, 0.65/0.35 | `$rankFusion` with the same weights |

The retriever interface is identical, and **ties are broken by doc ID**, so retrieval is deterministic.

### Cross-brand learning, safely

Incidents from other brands in the same vertical *within the same agency* are useful pattern
knowledge. They are allowed within a tenant, blocked across tenants, and anonymised at index time
("a client in this vertical").

### Soft deletes

Chunks are soft-deleted (`is_active=false`), never hard-deleted, so evidence cited in March is still
auditable in September.

## Five kinds of memory

| Memory | What it holds | Where | How long |
|--------|---------------|-------|----------|
| Working | The current `RunState` | `run_checkpoints` | Run + 30 days for replay |
| Episodic | Past runs: anomalies, actions, outcomes | `run_history` | 24 months |
| Semantic | Playbooks, guidelines, reports, incidents | `kb_chunks` (vector + text) | Indefinite, versioned |
| Procedural | Learned brand rules, e.g. "Q4 always spikes, don't flag it" | `brand_rules`, **human-approved** | Indefinite |
| Conversational | Chat history | `chat_sessions`, last 20 turns + summary | 90 days |

Procedural memory is what makes AdIntel feel like it learns. After an account manager dismisses
three similar anomalies as "planned promo", the system **proposes** a suppression rule and a human
approves it. It never silently learns to ignore things.

## Caching layers

| Layer | Local implementation | Key includes |
|-------|----------------------|--------------|
| Per-tenant API cache (60 s) | in-process TTL cache | tenant, route, params |
| **Semantic cache** for near-duplicate chat questions | cosine ≥ 0.97, 15-min TTL (`llm/semantic_cache.py`) | **tenant and brand** |
| Provider prompt caching | mlx-lm prompt cache (stable prefix first) | — |
| Embedding cache | content-hash → vector | model ID |
| RAG result cache | query hash → chunk IDs | tenant, brand, filters |
| Pre-computed daily rollups | `metrics_rollups` | tenant, brand, date |

Prompts are ordered **stable-prefix-first** so the cacheable part is as long as possible. A unit test
checks the order, because getting it wrong produces no error — only a bigger bill and slower chat.
