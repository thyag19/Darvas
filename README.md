# Darvas Box System (TradingView, Pine v6)

| File | Purpose |
|---|---|
| `DARVAS_SPEC.md` | Approved working specification (core rules 1-10 and interpretations). |
| `darvas_box_system_v2.pine` | The indicator. |
| `original/darvas_box_system_original.pine` | v1 as supplied. Never edit. |

## Core rules (defaults)
K=3 top and bottom confirmation with independent counters. Strict `>` / `<` resets, so equality never resets. Breakout is intrabar `high >= box top`, with no volume requirement. Invalidation is `close < box bottom`. Failed breakout is `close < the broken box's bottom`. The stop is the max of confirmed bottoms and is never reduced. The breakout bar's high becomes the next candidate top. Completed boxes are kept. Full text: `DARVAS_SPEC.md`.

## Optional extensions
- **Change the core when enabled** (group "Optional extensions (not frozen spec)"): new-high lookback per timeframe, trend filter (SMA), breakout on close, breakout buffer %, intrabar-low trigger for invalidation and failed breakout.
- **Never change the core:** strong/weak breakout volume marking, drawing options, provisional dashed box, breakout price line, alerts.
- **Statistics table and trade log:** *indicative only, not a validated backtest*. They are long-only, enter on the first breakout and exit on invalidation or failed breakout, and ignore commissions, slippage and sizing.

## Known limitations
- Not compiled or run in TradingView by the author; see the validation steps below.
- A wide bar that breaks out and closes below the old bottom counts as a breakout; the failed-breakout check starts on the next bar (see `DARVAS_SPEC.md`).
- TradingView keeps at most 500 boxes on the chart. The internal history is not capped.
- The stop is informational; no event is triggered from it.
- Bar-magnifier and replay behaviour for intrabar events is untested.

## TradingView validation steps
1. Open the Pine Editor, paste `darvas_box_system_v2.pine`, click **Add to chart**, and fix any compile error it reports.
2. With default inputs, check on a liquid daily chart that the optional-extension values are 0 or off and that the "Optional extensions" group sits apart from the other groups.
3. Pick several confirmed boxes and check on the chart: top confirmed after 3 bars with no higher high, bottom after 3 bars with no lower low, and a candidate top reset restarting the bottom.
4. Check the breakout triangle is on the first bar with `high >= top`, including a bar that only equals the top.
5. Check the invalidation cross appears only on a close below the box bottom, not on a wick through it.
6. After a breakout, check that a close back inside the old box above its bottom gives no failed-breakout mark, and a close below the old bottom does.
7. Check the stop line only ever steps up, including across invalidations and failed breakouts.
8. Turn each optional extension on in turn and check only the intended behaviour changes.
9. Check the alerts fire on the matching bars and the table footer reads "INDICATIVE ONLY".
