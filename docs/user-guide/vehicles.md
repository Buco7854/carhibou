# Vehicles and history

Vehicles belong to the instance, while [grants](./access.md) decide who can see or
operate each one. An administrator creates a vehicle with a name; Carhibou never asks
for an inferred powertrain classification.

![The vehicle list](/screens/vehicles.png)

The garage is a searchable catalog of vehicle photos and current readings. All, Online
and Parked filters change only the visible cards, not reporting behavior. A card shows
only readings that the vehicle has actually reported, so missing data never becomes
`0%`.

## History

![A vehicle's history: charts and the snapshot table](/screens/history.png)

Choose a vehicle and time range to review its route, chart a metric, or inspect the
state of the car at each moment. The **Snapshot table** is the default table view. Each
row contains everything Carhibou knew by the end of that time bucket, even when the
source reported only one changed value in that bucket.

Carried values keep their real observation time. The table dims and age-labels an older
value instead of pretending it was measured again, and collapses unchanged quiet spans
so long ranges remain usable. Columns come from what that vehicle reported; hidden
columns and their order are remembered in the browser per vehicle.

Open **Observations** when you want the raw evidence. It lists individual incoming
metric and position observations with their exact time and provenance. This view is
useful for diagnosing a profile or data source, but a raw observation is intentionally
not presented as the vehicle's complete state.

The chart and route follow the selected range and metric. Dense ranges are bounded and
downsampled for display without changing the recorded observations.

## Photos and deletion

Upload JPEG, PNG or WebP files up to 25 MiB from the vehicle card. Photos are visible to
everyone who can see the vehicle and live in the `vehicle-media` volume, which must be
backed up with PostgreSQL. Replacing or removing one keeps the card geometry stable.

Deleting a vehicle permanently removes its history, current state, photo, agents and
credentials, enrollment tokens, pending jobs and vehicle hooks. Pinned dashboard widgets
remain, but return to following the dashboard selector.

## How live readings and profiles work

Live state contains the resolved position, canonical readings and agent health that the
dashboard uses. Online state follows reporting freshness, including a parked agent's
slower cadence. Persistent readings may remain visible as stale; time-sensitive readings
become unknown when their evidence expires.

A telemetry profile belongs to a data source and translates its raw input into canonical
names such as `battery.soc`. CAN profiles are assigned to agents; mapping profiles are
assigned to connectors. Built-in and custom profiles are shared across the instance, and
an account with profile-creation access can add one from **Telemetry profiles**.

Changing an assigned profile increments that source's configuration version. Agents
receive the validated definition on their next configuration sync; connectors restart
their mapping session. Only use formulas backed by evidence for that vehicle and capture
hardware. Structural validation cannot prove that a reverse-engineered signal is
physically correct.
