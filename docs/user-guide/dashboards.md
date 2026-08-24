# Custom dashboards

Create a dashboard, add a widget, select a vehicle and canonical metric, then drag or
resize it. Save persists the layout in PostgreSQL. Initial widgets include position map,
metric card, battery gauge, status, time series, multi-series comparison, device health
and hook activity. Chart widgets persist their selected one-day, seven-day or thirty-day
range with the layout.

The registry maps widget type to component, default size and configuration fields, so
new types remain localized. Dashboards use canonical names such as `battery.soc`, never
CAN identifiers.

The SPA supports English and French through locale catalogs designed for more languages.
Light, Dark and Auto themes are saved per browser; Auto follows operating-system changes.
