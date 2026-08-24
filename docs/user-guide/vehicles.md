# Vehicles

Vehicles belong to a user independently of the login provider. Generic fields describe
identity, propulsion, nominal battery capacity, timezone and display metadata. Raw
C-Zero fields never enter the generic table; choose a vehicle profile for decoding.

Live state shows the latest position, canonical metrics and device health. Online state
uses reporting freshness rather than assuming every parked vehicle reports rapidly.

The vehicle catalog is arranged as a photographic garage: each card leads with the
vehicle image, followed by identity, live energy/speed/contact readings and direct
history/tracker actions. Electric vehicles show traction-battery state; petrol and
diesel vehicles show fuel level; hybrids use the available battery or fuel signal.
VehiNode never turns a missing reading into `0%`. The compact overview above it shows
fleet totals, connected vehicles and average reported energy. Search is local and
immediate; the All, Online and Parked filters only change the visible catalog and do
not alter reporting configuration.

## Vehicle photos

Use **Add photo** on a vehicle to upload a JPEG, PNG or WebP image up to 25 MiB. You can
replace or remove it from the same media frame. Until then, VehiNode shows a plain
missing-image icon directly in the empty photo area, without placeholder copy or a
substitute vehicle illustration.

Photos remain private to the vehicle owner. VehiNode stores the image as a file in its
media directory; PostgreSQL contains only its content type, size, fingerprint and
storage key. Docker installations persist these files in the `vehicle-media` volume,
which must be backed up together with PostgreSQL.
