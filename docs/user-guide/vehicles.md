# Vehicles and history

Vehicles belong to the instance, while [grants](./access.md) decide who can see or
operate each one. An administrator creates a vehicle with a name and, optionally, a
telemetry profile; Carhibou never asks for an inferred powertrain classification.

![The vehicle list](/screens/vehicles.png)

The garage is a searchable catalog of vehicle photos and current readings. All, Online
and Parked filters change only the visible cards, not reporting behavior.

## Live state and profiles

Live state shows the latest position, canonical metrics and agent health. Online state
uses reporting freshness, with due allowance for a parked agent's slower cadence. A card
prefers `battery.soc`, then `fuel.level`, then a conventional metric the vehicle actually
reported. Missing data stays missing instead of becoming `0%`.

A telemetry profile is a declarative map from raw CAN frames to names such as
`battery.soc`. Built-in and custom profiles are shared across the instance; an account
with profile-creation access can add one from **Telemetry profiles**. Assigning a profile
requires *operate* on the vehicle. Saving, changing or deleting an assigned custom
profile increments agent configuration so the validated definition reaches the agent.

Only use formulas backed by evidence for that vehicle and capture hardware. Structural
validation cannot prove that a reverse-engineered signal is physically correct.

## Photos and deletion

Upload JPEG, PNG or WebP files up to 25 MiB from the vehicle card. Photos are visible to
everyone who can see the vehicle and live in the `vehicle-media` volume, which must be
backed up with PostgreSQL. Replacing or removing one keeps the card geometry stable.

Deleting a vehicle permanently removes its history, current state, photo, agents and
credentials, enrollment tokens, pending jobs and vehicle hooks. Pinned dashboard widgets
remain, but return to following the dashboard selector.

## History

![A vehicle’s history: charts and the entries table](/screens/history.png)

History covers one visible vehicle over a selected range. The chart, route and raw table
follow the same range and metric. The chart endpoint bounds and downsamples dense data;
the metric choices come from what that vehicle actually reported.

**All entries** is different: it returns raw rows, newest first, with pagination rather
than downsampling. Header sorting treats metric values numerically and places text or
booleans last. Multiple numeric minimum and maximum filters combine, while *Only rows
reporting it* removes rows where an intermittent signal is absent.

Columns are derived from the data: position and agent fields plus every metric reported
in the range. Hidden columns and their order are remembered in the browser per vehicle;
new signals are appended without replacing that choice.
