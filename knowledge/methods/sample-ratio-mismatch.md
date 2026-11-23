# Sample ratio mismatch (SRM)

## What it is
If a test is designed as a 50/50 split, the observed numbers of users in each arm should be close to 50/50. A sample ratio mismatch is a statistically significant deviation from the designed split. It is checked with a chi-square goodness-of-fit test, and the usual alarm threshold is p < 0.001.

## Why it invalidates results
SRM almost always means users were lost or added in a way that depends on the treatment, for example a logging bug, a crash in one variant, or a redirect that drops some users. The users who remain are no longer comparable, so every metric can be biased in an unknown direction. A positive lift in a test with SRM is not evidence that the feature works.

## What to do
Do not ship. Find the cause by checking which segments (device, country, app version) have the imbalance, fix the assignment or logging, and rerun the experiment. In the beauty filter promotion test (EXP-104), low-engagement users on low-end Android phones were dropped from treatment, which made watch time look higher than it really was.
