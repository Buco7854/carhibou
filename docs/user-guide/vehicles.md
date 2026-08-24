# Vehicles

Vehicles belong to a user independently of the login provider. Generic fields describe
identity, propulsion, nominal battery capacity, timezone and display metadata. Raw
C-Zero fields never enter the generic table; choose a vehicle profile for decoding.

Live state shows the latest position, canonical metrics and device health. Online state
uses reporting freshness rather than assuming every parked vehicle reports rapidly.

The vehicle catalog shows fleet totals, connected vehicles and average battery state.
Search is local and immediate; the All, Online and Parked filters only change the visible
catalog and do not alter reporting configuration. Each vehicle card links to its real
history and tracker workflows.
