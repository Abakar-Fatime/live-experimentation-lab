# A/B testing basics

## What an A/B test answers
An A/B test randomly splits users into control and treatment so the only systematic difference between the groups is the feature. Any difference in metrics beyond chance can then be attributed to the feature. Random assignment is what makes the comparison causal.

## Unit of randomisation
In this lab the unit is the user. Every metric is first aggregated per user, then compared across arms. Analysing per session or per event while randomising per user underestimates variance, because events from the same user are correlated.

## Reading a result
Each metric is reported as a relative lift (treatment mean divided by control mean, minus one) with a 95% confidence interval. If the interval excludes zero, the change is statistically significant at the 5% level. The interval width shows how precisely the effect is measured; a significant but tiny lift may not be worth the cost of shipping.

## Primary, secondary and guardrail metrics
The primary metric is the one the hypothesis is about and drives the ship decision. Secondary metrics help explain the result. Guardrail metrics, such as report rate and 7-day retention, protect user experience: a feature that wins on the primary metric but significantly harms a guardrail should not ship.

## Decision rules used by the lab
1. If the sample ratio mismatch check fails, the result is invalid and the test must be rerun.
2. If any guardrail is significantly worse after multiple-testing correction, do not ship.
3. If the primary metric is significantly positive, ship.
4. Otherwise report no clear effect and keep control or iterate on the design.
