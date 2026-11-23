# EXP-105 Low-latency streaming mode - experiment readout

## Summary
Experiment EXP-105 (Low-latency streaming mode, key low_latency_mode) was run by LIVE Infrastructure on 150,000 users for 14 days. Decision: Ship. LIVE watch minutes per viewer up +3.9% (95% CI +2.7% to +5.1%); all guardrails healthy.

## Hypothesis
A lighter video codec will cut buffering and raise watch time, especially on low-end phones with slow networks.

## Sample ratio check
Treatment received 50.27% of users (chi-square p = 0.035). The split is healthy.

## Metric results
LIVE watch minutes per viewer (primary): +3.9% relative change, 95% CI +2.7% to +5.1%, adjusted p = 3.77e-10. CUPED removed 44% of the variance.
Gifts sent per viewer (secondary): +4.4% relative change, 95% CI +2.1% to +6.7%, adjusted p = 0.000237.
Gift value per viewer (secondary): +5.7% relative change, 95% CI +3.2% to +8.1%, adjusted p = 1.08e-05.
Report rate (guardrail): -4.9% relative change, 95% CI -9.8% to +0.1%, adjusted p = 0.0735.
7-day retention (guardrail): -0.0% relative change, 95% CI -0.8% to +0.7%, adjusted p = 0.978.

## Segments
Significant segment effects on the primary metric: device android_low +10.2%; country EG +6.5%; country MX +5.9%; country NG +5.8%.

## Peeking
The cumulative p-value first dropped below 0.05 on day 1.
