# Dashboards

VehiNode always provides one premade **Overview** composed from normal dashboard widgets:
a vehicle selector, large position/route map, vehicle media, energy state, current
telemetry, tracker health, connection status and a recent metric chart. Existing accounts
that predate the preset receive it without losing their other dashboards. Create
additional dashboards for another vehicle or purpose and choose which one opens by
default.

The selected dashboard is the page itself. Tabs sit above the content and a single actions
menu contains **Edit dashboard** and **New dashboard**. Editing enables dragging, resizing
and a compact toolbar on that same canvas. Saving simply removes the editing controls;
there is no separate dashboard-editor destination. Each Overview section is an ordinary
saved widget, so removing or repositioning one in edit mode changes the normal dashboard
page after saving.

Add a widget, select a vehicle and canonical metric, then drag or resize it on a larger
screen. On narrow screens the canvas becomes a single-column stack and moving/resizing
is disabled so widget contents remain readable. Save persists the layout in PostgreSQL.
Available widgets include the vehicle selector, vehicle media, telemetry list, position
map, metric card, energy gauge, status, time series, multi-series comparison, device
health and hook activity. Chart widgets persist their selected one-day, seven-day or
thirty-day range with the layout.

Widgets added with **Selected vehicle** follow the dashboard's selector immediately.
The selector is a fixed-size searchable dropdown, so it does not expand the canvas as the
fleet grows. Widgets pinned to a named vehicle ignore the selector. This allows one
reusable dashboard to switch all of its live cards together while still supporting a
fixed comparison card.

Data widgets use one consistent **No data yet** state until the selected vehicle reports
the required metric, position, history or tracker health. Empty maps and charts are not
mounted, and telemetry lists omit unavailable readings instead of filling the card with
dashes.

The registry maps widget type to component, default size and configuration fields, so
new types remain localized. Dashboards use canonical names such as `battery.soc`, never
CAN identifiers. Suggested metrics come directly from the selected vehicle's reported
keys. The energy gauge shows `battery.soc` when available, otherwise `fuel.level`, without
classifying the vehicle. An explicitly configured metric card or chart always keeps the
metric you selected.

The SPA supports English and French through locale catalogs designed for more languages.
The browser language is used initially; an explicit choice is then saved. Light, Dark
and Auto themes are saved per browser; Auto follows operating-system changes.
