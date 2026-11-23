# Propensity score methods

## The selection problem
When users or creators choose to join a programme, those who join are usually different, for example more active or with more followers. Comparing joiners with non-joiners mixes the programme effect with these differences.

## Methods in the lab
Inverse propensity weighting (IPW) re-weights each creator by the inverse of their probability of joining, estimated with logistic regression, so the groups look alike on observed covariates. Propensity matching pairs each joiner with the non-joiner whose propensity is closest. Doubly robust estimation (AIPW) combines an outcome model with the weights and stays consistent if either model is correct.

## Creator Academy result
Creators who joined the Creator Academy streamed 7.0 more hours per week than those who did not, but this naive gap is mostly selection. After adjustment, IPW estimates +1.57 hours and doubly robust estimation +1.49 hours (95% CI 1.41 to 1.57), close to the true effect of 1.5 hours. Covariate balance improves from standardised mean differences above 1.1 to below 0.03.

## Limitation
These methods only adjust for observed covariates. Unmeasured confounders, such as motivation, can still bias the estimate.
