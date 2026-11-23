# CUPED variance reduction

## Idea
CUPED (Controlled-experiment Using Pre-Experiment Data) reduces noise by using each user's behaviour before the experiment. Heavy viewers stay heavy viewers, so a large part of the variation in watch time can be predicted from the pre-period and removed.

## How it works
For outcome Y and pre-period covariate X, compute theta = cov(Y, X) / var(X) on the pooled data. The adjusted outcome is Y - theta * (X - mean(X)). Because X was measured before randomisation, it is independent of treatment and the estimate stays unbiased; only the variance shrinks.

## Effect in this lab
The lab uses pre-period LIVE watch minutes as the covariate for watch-time metrics. CUPED removes about 45% of the variance in the experiments, so confidence intervals are roughly 25 to 30% narrower. That is like running the test with almost twice as many users for free.

## When CUPED helps less
CUPED only helps if the covariate predicts the outcome. New users have no pre-period history, and metrics unrelated to past behaviour gain little.
