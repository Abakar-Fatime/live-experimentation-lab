# Ratio metrics and the delta method

## Why ratio metrics need care
Metrics such as gifts per watch hour divide two sums: total gifts and total hours. The analysis unit (hours) is not the randomisation unit (users), so treating each hour as independent understates the variance.

## The delta method
The lab computes each arm's ratio as mean(numerator) / mean(denominator) per user and approximates its variance with a first-order Taylor expansion: var(R) is about [var(N) - 2R cov(N, D) + R^2 var(D)] / (n * mean(D)^2). The same delta-method idea is used to turn a difference in means into a confidence interval for the relative lift.
