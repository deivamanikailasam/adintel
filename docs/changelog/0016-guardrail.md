# 0016 — Guardrail agent

**In one sentence:** nothing leaves AdIntel until a final safety check passes — and if that check is
slow or broken, the answer is "hold it", never "let it through".

## What changed

- `agents/guardrail.py`
  - **Code checks first** (cannot be bypassed): personal data; the name of any *other* brand or agency;
    unsafe claims ("guaranteed", "risk-free"); echoed injection phrases; claims that a change was made
    without approval; and a second numeric-grounding check on the report.
  - **Then a safety classifier** (the small model with a six-category taxonomy modelled on Llama Guard)
    for the semantic tail — e.g. text that implicitly reveals another client's strategy.
  - **Zero retries, no fallback model, fail closed.** A timeout, outage or malformed answer blocks
    the output.
  - Recommendations must still be pending approval, with citations and constraint checks, or the
    output is blocked.
- `llm/gateway.py` — callers can now turn off repairs and transient retries (the guardrail does).

## Why it matters (layman's terms)

A safety check that is retried until it passes isn't a safety check. A safety check that lets things
through when it's down is worse than none, because everyone assumes it ran. This one does neither.
