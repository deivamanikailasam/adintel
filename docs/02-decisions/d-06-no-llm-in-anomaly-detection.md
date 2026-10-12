# D-06: No LLM in anomaly detection

- **Status:** accepted
- **Owner:** Tech lead
- **Date:** 2026-10-12

## Context

LLMs are poor at precise time-series detection, vary run to run and give no confidence interval. 'The AI thought it looked weird' is not defensible to a client.

## Decision

Seasonal-trend decomposition (STL, weekly period) with a robust residual band, confirmed by an Isolation Forest with a fixed seed. Same input, same output.

## Consequences

Needs at least 28 days of history; shorter series skip detection with a disclosed degradation.

## Alternatives rejected

LLM-based detection; a plain z-score (ignores weekly seasonality and fires every Monday).

## Revisit when

Not expected to change.
