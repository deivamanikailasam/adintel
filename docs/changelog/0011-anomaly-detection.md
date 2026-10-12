# 0011 — Anomaly Detection agent (no AI model, on purpose)

**In one sentence:** AdIntel now spots unusual changes in cost, return, clicks and conversions using
classic statistics that give the same answer every time and can show exactly why something was flagged.

## What changed

- `agents/anomaly.py` — for every campaign and metric over 180 days:
  - learns the normal weekly rhythm (Mondays differ from Sundays) with **STL** decomposition, using
    only the history *before* the last week so a problem can't hide itself in its own baseline;
  - draws a "normal range" band (3 robust standard deviations, at least ±5%);
  - flags a metric only if it stays outside the band for **3+ days in the harmful direction** (2 days
    if the jump is 50%+). Ratios like CPA use 3-day sums so a day with four sales isn't mistaken for a
    crisis, and low-volume campaigns skip CPA/ROAS entirely;
  - asks an **Isolation Forest** (fixed random seed) for a second opinion;
  - scores **severity** from how big the change is *and* how much money is at stake;
  - applies human-approved suppression rules ("Q4 always spikes, don't flag it").
- Tests prove: the Urban Roast Meta CPA spike is HIGH; the clean brands show nothing above low;
  a weekly Monday bump does **not** fire; results are identical across runs.

## Why it matters (layman's terms)

"The AI thought it looked weird" is not something you can say to a client. "Your cost per sale has
been above its normal range of $16.50–$23.70 for four days; it is $29.22" is. Statistical detection is
also roughly a thousand times cheaper than asking a language model and never varies between runs.
