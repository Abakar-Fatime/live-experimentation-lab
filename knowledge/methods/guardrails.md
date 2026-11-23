# Guardrail metrics

## Purpose
Guardrails stop teams from shipping changes that win on their own goal while damaging the product. In LIVE, the lab uses two guardrails: report rate (share of users reporting a stream as harmful or annoying; must not rise) and 7-day retention (share of users who come back; must not fall).

## Trade-offs
A feature that raises watch time by making content more intrusive can increase reports and push users away over time. The autoplay LIVE previews test (EXP-102) is an example: watch time rose about 6%, but reports rose about 26% and retention fell, so the recommendation is not to ship and to explore a less intrusive design, such as previews only for followed creators.
