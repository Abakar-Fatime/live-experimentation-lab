# EXP-102 Autoplay LIVE previews in feed - experiment readout

## Summary
Experiment EXP-102 (Autoplay LIVE previews in feed, key autoplay_preview) was run by LIVE Growth on 120,000 users for 14 days. Decision: Don't ship. Primary metric improved +6.4%, but the trade-off is not acceptable. Guardrail breached: Report rate moved +25.7% (adjusted p = 2.42e-16). Guardrail breached: 7-day retention moved -1.3% (adjusted p = 0.00247).

## Hypothesis
Auto-playing a muted LIVE preview in the For You feed will pull more viewers into LIVE rooms and raise watch time.

## Sample ratio check
Treatment received 50.05% of users (chi-square p = 0.75). The split is healthy.

## Metric results
LIVE watch minutes per viewer (primary): +6.4% relative change, 95% CI +5.0% to +7.8%, adjusted p = 2.72e-20. CUPED removed 45% of the variance.
Gifts sent per viewer (secondary): +7.6% relative change, 95% CI +5.0% to +10.3%, adjusted p = 8.83e-09.
Gift value per viewer (secondary): +7.6% relative change, 95% CI +4.8% to +10.4%, adjusted p = 5.6e-08.
Report rate (guardrail): +25.7% relative change, 95% CI +18.9% to +32.5%, adjusted p = 2.42e-16, guardrail breached.
7-day retention (guardrail): -1.3% relative change, 95% CI -2.1% to -0.5%, adjusted p = 0.00247, guardrail breached.

## Segments
Significant segment effects on the primary metric: country ID +10.2%; country MY +8.3%; device android_high +7.7%; country NG +7.0%.

## Peeking
The cumulative p-value first dropped below 0.05 on day 1.
