# Dashboards

Every account starts with an **Overview** made from ordinary widgets: selector, map,
energy, charging, current telemetry, history and agent health. Widgets with no relevant
data can hide themselves, so the same dashboard works for an EV, a fuel vehicle or an
agent that reports only position.

![The default overview dashboard](/screens/dashboard.png)

Create more dashboards for a vehicle or purpose and choose which opens by default.
Dashboards are personal and stored in PostgreSQL.

## Edit the canvas

The dashboard is both the viewing and editing surface. **Edit dashboard** enables adding,
dragging and resizing widgets on the same canvas; saving removes those controls. On a
narrow screen, the layout becomes a stable single-column stack and disables movement so
content remains readable.

Available widgets include the vehicle selector, media, telemetry, map, metric card,
energy gauge, status, time series, comparison chart, agent health and hook activity.
Charts retain their one-, seven- or thirty-day range.

Widgets set to **Selected vehicle** follow the searchable selector immediately. A widget
pinned to one vehicle ignores it. If access to that vehicle is later removed, the widget
shows an empty state and does not reveal the vehicle.

Data widgets consistently show **No data yet** until the required position, metric,
history or health exists. The optional **Hide this widget when the vehicle reports no
data for it** closes the gap without changing the saved layout; edit mode always reveals
hidden widgets.

## Metrics

Dashboards consume canonical names, never raw CAN identifiers. Suggested metrics come
from the selected vehicle. Energy displays `battery.soc` or `fuel.level` when reported.
Charging widgets use the resolved charging state and rate; Carhibou may derive these from
fresh power evidence when no explicit state is available. Widgets display the result and
do not repeat that inference themselves. Explicitly configured cards keep the metric
selected by the owner.

A pattern can be exact (`battery.soc`) or a prefix (`tyre.*`). Prefixes automatically
include later matching signals; pattern order controls display order. A gauge or reading
uses the first match because it represents one value, while tables and charts accept all
matches.

English and French follow the browser language until explicitly changed. Light, Dark and
Auto interface themes are saved in the browser; Auto follows the operating system. Map
appearance is separate: it can follow the interface using your selected OpenFreeMap
light and dark styles, or keep one provider style at all times. Liberty and Dark are the
defaults.
