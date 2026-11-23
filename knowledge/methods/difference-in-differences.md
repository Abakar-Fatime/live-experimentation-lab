# Difference-in-differences (DiD)

## When to use it
When a feature launches to some markets but not others, without randomisation, compare the change over time in launched markets with the change over the same period in markets without the launch. The control markets capture common trends such as seasonality.

## Key assumption
Parallel trends: without the launch, treated and control markets would have moved in parallel. The lab checks this with an event study, estimating week-by-week effects before the launch; pre-launch effects close to zero support the assumption.

## Gifting v3 rollout result
Gifting v3 launched only in Brazil and Mexico on day 30. A naive before/after comparison in those countries suggests a 14.0% rise in gift revenue per DAU, but much of that is the platform-wide trend. Difference-in-differences with country and day fixed effects estimates +7.5% (95% CI 5.9% to 9.2%), and the simulated true effect was 7%.
