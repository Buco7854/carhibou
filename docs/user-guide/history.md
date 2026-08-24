# History

Choose a vehicle, range and metric to view its route and telemetry chart. The API bounds
the result and downsamples to the requested maximum so a browser does not receive an
unbounded month of raw samples. Exact source count and latest selected value remain
visible in a separate vehicle summary. Data controls occupy their own panel instead of
being compressed into the summary row. The initial metric is selected directly from
available telemetry; the application does not need or display a vehicle classification.
Every reported canonical metric remains selectable through the custom dropdown.
