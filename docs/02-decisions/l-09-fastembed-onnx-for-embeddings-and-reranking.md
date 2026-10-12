# L-09: fastembed (ONNX) for embeddings and reranking

- **Status:** accepted
- **Owner:** Tech lead
- **Date:** 2026-10-12

## Context

Embeddings and the cross-encoder must run on a laptop without PyTorch, deterministically, with pinned model IDs.

## Decision

fastembed BAAI/bge-small-en-v1.5 embeddings and BAAI/bge-reranker-base cross-encoder, behind Embedder/Reranker interfaces; a deterministic hashing embedder and lexical reranker for tests and offline mode.

## Consequences

Different dimensionality from production (384 vs 1,024); the vector index definition is generated from the embedder's dimension.

## Alternatives rejected

sentence-transformers (PyTorch dependency); calling a hosted embedding API (data leaves the machine).

## Revisit when

Retrieval evals regress against production embeddings.
