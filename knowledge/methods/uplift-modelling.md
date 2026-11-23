# Uplift modelling (heterogeneous treatment effects)

## Question
An average lift can hide very different effects across users. Uplift models estimate the conditional average treatment effect (CATE) for each user from experiment data, to find who benefits and to target a feature.

## Models used
The T-learner trains one LightGBM model on treatment users and one on control users and subtracts their predictions. The X-learner adds a second stage that imputes individual effects and blends them with propensity weights. Models predict log watch time, so the output is close to a relative lift.

## Evaluation
Models are trained on half the experiment and evaluated on the other half with a Qini (cumulative uplift) curve, compared with random targeting and with an oracle that knows the true effects. Because the lab knows each user's true effect, it also reports the correlation between predicted and true effects.

## Low-latency mode result
In EXP-105, the true gain is about 12% for low-end Android users in emerging markets and zero elsewhere. The best model ranks Egypt, Indonesia, Brazil and Vietnam low-end Android as the top segments. Targeting only segments with a predicted lift above 4% treats about half the users while capturing all the true gain.
