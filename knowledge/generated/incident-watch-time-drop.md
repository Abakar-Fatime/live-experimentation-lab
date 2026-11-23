# Incident report - LIVE watch time drop (2026-11-16)

## What happened
LIVE watch minutes per DAU fell 3.7% week over week (from 33.7 to 32.4 minutes). The anomaly detector raised the first alert on 2026-11-16, the same day the drop started.

## Root cause
The drop is concentrated in Indonesia on low-end Android phones (ID / android_low): that segment's minutes per DAU fell 38% and it explains 113% of the total change (other segments slightly offset it). The cause was the Android app v8.3 video player bug on low-end devices.

## Top contributing segments
ID / android_low: 113% of the change; SA / android_high: 1% of the change; EG / android_low: 1% of the change.

## Follow-up
Roll back or hotfix the v8.3 player on low-end Android, add app version as a monitoring dimension, and exclude the incident week from experiment baselines.
