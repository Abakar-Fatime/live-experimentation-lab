# Peeking and early stopping

## The problem
A fixed-horizon test is valid only if you look at the p-value once, at the planned end. If you check every day and stop the first time p < 0.05, you give chance many opportunities to cross the threshold, so the false positive rate rises well above 5%.

## Measured in this lab
In 1,000 simulated A/A tests (no real effect) with 14 daily looks, a single check at the end gave false positives 5.0% of the time, but stopping at the first daily p < 0.05 produced a false positive in 11.9% of tests, more than double the promised rate.

## How to avoid it
Decide the sample size and duration in advance with a power analysis and only make the decision at the end. Run for whole weeks so weekday and weekend behaviour are both covered. If teams need to monitor continuously, use sequential testing methods with adjusted boundaries, such as alpha spending or always-valid p-values.
