# Multiple testing

## The problem
Every metric and every segment tested adds another chance of a false positive. With 20 independent comparisons at the 5% level, you expect about one significant result by luck alone.

## What the lab does
Within each experiment, the lab adjusts p-values with the Benjamini-Hochberg procedure, which controls the false discovery rate. Segment breakdowns (device, country, new versus returning users) are adjusted separately. Decisions use adjusted p-values. Segment results should be treated as hypotheses for a follow-up test unless they were planned in advance.
