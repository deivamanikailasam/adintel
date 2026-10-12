# L-05: STL + robust band instead of Prophet

- **Status:** accepted
- **Owner:** Tech lead
- **Date:** 2026-10-12

## Context

Prophet needs a Stan toolchain that is painful on Apple Silicon and in slim containers. The requirement is a seasonal model with a prediction interval, deterministic and auditable.

## Decision

statsmodels STL (weekly period, robust) for the expected band plus scikit-learn IsolationForest (fixed random_state) as confirmation. The detector interface allows Prophet as a drop-in.

## Consequences

STL extrapolation is simpler than Prophet's changepoint model; evaluated with the 50-series anomaly golden set.

## Alternatives rejected

Prophet; plain z-score.

## Revisit when

Anomaly F1 on the golden set falls below 0.90 or false positives exceed 5%.
