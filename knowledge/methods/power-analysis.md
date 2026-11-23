# Power analysis and sample size

## Formula
To detect a relative lift (minimum detectable effect, MDE) with significance level alpha and power 1 - beta, each arm needs n = 2 (z_(1-alpha/2) + z_(1-beta))^2 * sigma^2 / delta^2 users, where sigma is the metric's standard deviation and delta = baseline mean * MDE.

## Sample size for LIVE watch time
In the control groups of past LIVE experiments, watch time averages about 74 minutes per user over 14 days with a standard deviation of about 115 minutes, because a few heavy viewers watch for hours. Detecting a 3% relative lift with 80% power at the 5% level therefore needs about 41,900 users per arm without CUPED, and about 22,400 per arm with CUPED.

## Checked by simulation
The formula was tested by simulation: for a 3% lift it asked for 30,511 users per arm on the simulated metric, and in 500 simulated tests of exactly that size the test was significant 79.4% of the time, matching the promised 80% power.

## Practical tips
Smaller effects need many more users: halving the MDE requires four times the sample. CUPED reduces sigma^2 by about 45% for watch time, which cuts the required sample nearly in half. The planner page in the dashboard computes these numbers interactively.
