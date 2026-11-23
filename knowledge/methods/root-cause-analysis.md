# Metric monitoring and root-cause analysis

## Anomaly detection
The anomaly detector decides whether a day is unusual. Each day, the platform metric (LIVE watch minutes per DAU) is compared with a baseline: the median of the same weekday over the previous four weeks. The residual is scaled with a robust z-score based on the median absolute deviation of past residuals, and days with |z| > 4 raise an alert.

## Decomposition
For a ratio metric such as minutes per DAU, a week-over-week change can come from segments changing their rate (each segment watches less) or from mix (traffic shifting to segments that always watch less). The lab splits each segment's contribution into a rate effect and a mix effect using symmetric averages, then ranks segments by contribution. Checking country, device and their combination shows where the change is concentrated.

## The November incident
On 16 November 2026, minutes per DAU dropped about 4% below baseline (robust z around -22) and the alert fired the same day. Decomposition shows that Indonesia on low-end Android explains essentially all of the drop: that segment's watch minutes per DAU fell 38% while other segments were stable. This pointed to the Android app v8.3 video player bug, which only affected low-end devices.
