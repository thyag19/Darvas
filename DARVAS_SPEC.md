# Darvas Box System: approved working specification

**Status:** approved working specification for `darvas_box_system_v2.pine`. It is **not** a recovered historical document. The text of the earlier "frozen spec Sections 1-8" is unavailable. Where the comments in `original/darvas_box_system_original.pine` differ from the rules below, these rules win. Those comments are historical implementation notes only.

## Rules

1. **Box top.** A candidate high is confirmed after K=3 subsequent bars without a strictly higher high. A strictly higher high replaces the candidate and resets confirmation. An equal high does not.
2. **Box bottom.** The search begins on the bar after the candidate-top bar. Track the running low. A strictly lower low resets confirmation. Confirm after K=3 subsequent bars without a lower low. An equal low does not reset.
3. **Independence.** The top and bottom counters run independently. A new (higher) candidate top restarts bottom formation. A bottom reset does not affect the top.
4. **Confirmation.** The box is confirmed when both boundaries are confirmed.
5. **Breakout.** `high >= confirmed box top`. The test is intrabar and equality counts. There is no volume requirement.
6. **Invalidation.** `close < confirmed box bottom` returns to NO_BOX. Searching restarts with no cooldown. The first bar after the event starts a new candidate top.
7. **Failed breakout.** After an upward breakout, `close < the broken box's bottom`. A close back inside the old box above its bottom is not a failure.
8. **Stop.** The stop is the raw confirmed box bottom, raised only by confirmed bottoms: `stop = max(previous_stop, new_confirmed_bottom)`. It never decreases and is never reset, including across invalidations and failed breakouts. It is not used as a substitute for the event conditions in rules 6 and 7.
9. **Breakout terminates the box.** The old box ends on the breakout bar. That bar's high immediately becomes the next candidate top, with no gap. The new bottom search starts on the next bar.
10. **Completed boxes are preserved**, both in the `historicalBoxes` array and, unless "Keep completed boxes visible" is switched off, on the chart. TradingView limits drawings to 500 boxes, so on very long histories older boxes disappear from the chart. The array is never trimmed.

## Implementation interpretations (not stated in the rules; please confirm or amend)

- **Event precedence in a confirmed box.** Breakout is tested before invalidation. A wide bar that reaches the top and also closes below the bottom counts as a breakout (rule 9 ends the box on that bar). The failed-breakout test (rule 7) first applies on the following bar.
- **Failed-breakout window.** It stays open from the breakout until the next box confirms. After that, rule 6 applies to the new box.
- **Failed breakout beats confirmation** if both occur on the same bar while forming.
- **When the stop rises.** It is raised when a box confirms. After a breakout it is also raised as soon as a new bottom confirms, before the new box's top confirms. Before the first breakout it is raised only at box confirmation.
- **Search restart.** After an invalidation or failed breakout, the next bar always starts a new search (core, extensions off).

## Optional extensions (outside the core, off or neutral by default)

New-high lookback, trend filter, breakout-on-close, breakout buffer, intrabar-low invalidation/failed-breakout trigger. All sit in the "Optional extensions (not frozen spec)" input group. Enabling any of them changes core behaviour, which is their purpose. Volume classification, drawing options and the statistics table never change core behaviour.
