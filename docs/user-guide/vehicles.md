# Vehicles

Vehicles belong to a user independently of the login provider. Generic fields describe
identity, propulsion, nominal battery capacity, timezone and display metadata. Raw
C-Zero fields never enter the generic table; choose a vehicle profile for decoding.

Live state shows the latest position, canonical metrics and device health. Online state
uses reporting freshness rather than assuming every parked vehicle reports rapidly.
