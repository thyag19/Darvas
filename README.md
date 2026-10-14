# Darvas Box System (TradingView, Pine v6)

| File | Purpose |
|---|---|
| `original/darvas_box_system_original.pine` | v1.0, the frozen-spec script, saved verbatim. Do not edit. |
| `darvas_box_system_v2.pine` | v2.0, improved version. |

## What v2 changes

**Bug fixes**
- **Equal-high inconsistency.** v1 counted a bar whose high equalled the candidate top as "not exceeded" while forming, but treated the same bar as a breakout once the box was confirmed (`h >= boxTop`). v2 uses strict `>` in both places.
- **Draw switch.** v1's "Keep historical boxes visible" switched off all box drawing, including the active box. v2 has a separate "Draw boxes" setting.
- **Unbounded array.** The `historicalBoxes` array in v1 was written but never read, and it was never trimmed. v2 reads it for the statistics table and caps it at 500 entries.

**Additions** (neutral or off by default, so v1 behaviour is recoverable)
- **New-high lookback** for intraday, daily and weekly charts, taken from the TradingView description you pasted. A box search starts only when a bar's high exceeds the previous N bars' highs. Set it to 0 for v1 behaviour. The defaults (50, 60 and 26 bars) are starting points to experiment with.
- **Trend filter** (optional): only start a box while the close is above an SMA.
- **Breakout trigger:** intrabar high (the on-stop buy order Darvas used, and the default) or close. Also an optional percentage buffer above the top.
- **Volume classification.** A breakout on at least N times the average volume is drawn as a strong breakout, otherwise as a weak one. It classifies only and never blocks a breakout, which keeps the spec's "no volume requirement in the core" intact.
- **Stop trigger:** close below the stop level (default) or an intrabar low through it.
- **Separate top and bottom confirmation bars.**
- **Gap-aware buy-stop fill.** The entry price is `max(open, trigger)`.
- **Provisional dashed box** while a box is forming, plus a breakout (buy-stop) price line and label.
- **Statistics table.** It shows box count, breakout rate, average height and width, and a simple long-only trade log (win rate, average win and loss, profit factor). The log is indicative only: there are no commissions or slippage, and stacked boxes don't add size.
- **Extra alerts:** box confirmed and strong breakout.

## Open design questions (not changed)
1. A bar that breaks out *and* closes below the stop is treated as a breakout, and the stop is first checked on the next bar. This was already a known simplification in v1.
2. After an invalidation, the next box search is only unlocked by a fresh new high. This is deliberate when the lookback is above 0.
3. The trailing stop only rises on bottom confirmation after a breakout. A volatility (ATR) based trail is a possible later addition.

## Caveat
These scripts were not compiled in TradingView from this environment. Paste `darvas_box_system_v2.pine` into the Pine Editor and fix anything it flags.
