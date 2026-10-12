# Egress control, offline (air-gapped) mode and model-weight pinning

## Who may AdIntel talk to?

| Mode | Setting | Reachable |
|------|---------|-----------|
| Development (default) | — | anything |
| Allowlist | `ADINTEL_EGRESS_ALLOWLIST=["bedrock-runtime.us-east-1.amazonaws.com","*.slack.com"]` | internal destinations + the list (`host`, `host:port`, `*.suffix`) |
| **Offline / air-gapped** | `ADINTEL_OFFLINE=true` | loopback, private networks (LAN model server), single-label service names (`mongo`, `keycloak`, `host.docker.internal`), `.local/.internal/.svc` names, + the allowlist |

Checked at start-up for every configured endpoint — every model tier's URL, OTEL, Langfuse, alert
webhook, identity provider issuer/JWKS, S3/MinIO — and again when the model client or alert webhook
connects. A violation refuses to start (`EgressDenied`), naming the endpoint. `adintel egress-check`
prints each endpoint and its verdict.

Offline mode also sets `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `DO_NOT_TRACK=1`: embedding/reranker
models (fastembed) and tokenizers must already be on disk, so nothing is downloaded silently. Before
going offline: `make install`, run one `ADINTEL_EMBEDDER=fastembed adintel seed` (downloads the BGE models
once), pull container images, and lock the model weights (below).

Production equivalent: VPC with no internet route except the NAT for ad-platform APIs, VPC endpoints for
AWS services, and the allowlist naming exactly those hosts. The code-level check is defence in depth on top
of the network control.

## Are these the weights we evaluated?

```bash
adintel weights lock                         # SHA-256 of every file in each local tier's HF snapshot
adintel weights lock --path qwen3.6:35b-a3b-q4_K_M=~/models/Qwen3.6-35B-A3B-Q4_K_M.gguf   # Ollama/llama.cpp
adintel weights verify                       # exit 1 on a mismatch, missing or extra file
```

The lock file (`config/model-weights.lock.json`) is committed with the evaluation results that justified
the model; a re-download, corruption or swapped file is caught by `verify` (run it after downloads and in
the release checklist). Adapters keep their own pin in `config/models.yaml`.
