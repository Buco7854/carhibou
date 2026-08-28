import BatteryGaugeWidget from './BatteryGaugeWidget.vue'
import ChargingWidget from './ChargingWidget.vue'
import ActivityFeedWidget from './ActivityFeedWidget.vue'
import AgentHealthWidget from './AgentHealthWidget.vue'
import HookActivityWidget from './HookActivityWidget.vue'
import MetricCardWidget from './MetricCardWidget.vue'
import MultiSeriesWidget from './MultiSeriesWidget.vue'
import PeriodStatsWidget from './PeriodStatsWidget.vue'
import OnlineStatusWidget from './OnlineStatusWidget.vue'
import PositionMapWidget from './PositionMapWidget.vue'
import RouteMapWidget from './RouteMapWidget.vue'
import SegmentStatsWidget from './SegmentStatsWidget.vue'
import TimeSeriesWidget from './TimeSeriesWidget.vue'
import TelemetryListWidget from './TelemetryListWidget.vue'
import VehicleMediaWidget from './VehicleMediaWidget.vue'
import VehicleSelectorWidget from './VehicleSelectorWidget.vue'
import XyChartWidget from './XyChartWidget.vue'
import type { DashboardWidgetDefinition } from './types'
import type { DashboardWidget, Vehicle } from '../api/types'
import { chargingState, energySummary, metricReading, secondaryReadings } from '../vehicleDisplay'

const reports = (vehicle: Vehicle | null | undefined, key: string): boolean =>
  metricReading(vehicle, key).value !== null

const definitions: DashboardWidgetDefinition[] = [
  { type:'vehicle-selector', titleKey:'dashboards.vehicleSelector', component:VehicleSelectorWidget, defaultSize:{w:12,h:1}, needsMetric:false, configSchema:{fields:['title']} },
  { type:'vehicle-media', titleKey:'dashboards.vehicleMedia', component:VehicleMediaWidget, defaultSize:{w:4,h:2}, needsMetric:false, configSchema:{fields:['vehicle_id','title']}, isEmpty:(_widget, vehicle) => !vehicle?.photo_url },
  { type:'telemetry-list', titleKey:'dashboards.telemetryList', component:TelemetryListWidget, defaultSize:{w:4,h:3}, needsMetric:false, configSchema:{fields:['vehicle_id','title']}, isEmpty:(_widget, vehicle) => secondaryReadings(vehicle).length === 0 && !reports(vehicle, 'vehicle.speed') },
  { type:'metric-card', titleKey:'dashboards.metricCard', component:MetricCardWidget, defaultSize:{w:3,h:2}, needsMetric:true, configSchema:{fields:['vehicle_id','metric','title','unit']}, isEmpty:(widget, vehicle) => !reports(vehicle, widget.metric ?? '') },
  { type:'battery-gauge', titleKey:'dashboards.batteryGauge', component:BatteryGaugeWidget, defaultSize:{w:4,h:2}, needsMetric:false, configSchema:{fields:['vehicle_id','title']}, isEmpty:(_widget, vehicle) => energySummary(vehicle).value === null },
  { type:'charging', titleKey:'dashboards.charging', component:ChargingWidget, defaultSize:{w:4,h:2}, needsMetric:false, configSchema:{fields:['vehicle_id','title']}, isEmpty:(_widget, vehicle) => chargingState(vehicle).active === null },
  { type:'position-map', titleKey:'dashboards.positionMap', component:PositionMapWidget, defaultSize:{w:6,h:4}, needsMetric:false, configSchema:{fields:['vehicle_id','title','time_range_days']}, isEmpty:(_widget, vehicle) => !vehicle?.state?.position },
  { type:'time-series', titleKey:'dashboards.timeSeries', component:TimeSeriesWidget, defaultSize:{w:6,h:3}, needsMetric:true, configSchema:{fields:['vehicle_id','metric','title','unit','time_range_days']} },
  { type:'multi-series', titleKey:'dashboards.multiSeries', component:MultiSeriesWidget, defaultSize:{w:6,h:3}, needsMetric:false, needsMetrics:true, configSchema:{fields:['vehicle_id','metrics','title','time_range_days']} },
  { type:'online-status', titleKey:'dashboards.onlineStatus', component:OnlineStatusWidget, defaultSize:{w:3,h:2}, needsMetric:false, configSchema:{fields:['vehicle_id','title']}, isEmpty:(_widget, vehicle) => !vehicle?.state },
  { type:'agent-health', titleKey:'dashboards.agentHealth', component:AgentHealthWidget, defaultSize:{w:3,h:4}, needsMetric:false, configSchema:{fields:['vehicle_id','title']}, isEmpty:(_widget, vehicle) => Object.keys(vehicle?.state?.agent ?? {}).length === 0 },
  { type:'route-map', titleKey:'dashboards.routeMap', component:RouteMapWidget, defaultSize:{w:8,h:6}, needsMetric:false, configSchema:{fields:['vehicle_id','title','time_range_days']}, isEmpty:(_widget, vehicle) => !vehicle?.state },
  { type:'activity-feed', titleKey:'dashboards.activityFeed', component:ActivityFeedWidget, defaultSize:{w:4,h:5}, needsMetric:false, configSchema:{fields:['vehicle_id','title','time_range_days']} },
  { type:'segment-stats', titleKey:'dashboards.segmentStats', component:SegmentStatsWidget, defaultSize:{w:4,h:3}, needsMetric:false, configSchema:{fields:['vehicle_id','title','time_range_days']} },
  { type:'xy-chart', titleKey:'dashboards.xyChart', component:XyChartWidget, defaultSize:{w:6,h:3}, needsMetric:false, configSchema:{fields:['vehicle_id','title','time_range_days','x_metric','y_metric']}, isEmpty:(_widget, vehicle) => !vehicle?.state },
  { type:'period-stats', titleKey:'dashboards.periodStats', component:PeriodStatsWidget, defaultSize:{w:6,h:3}, needsMetric:false, configSchema:{fields:['vehicle_id','title','time_range_days']} },
  { type:'hook-activity', titleKey:'dashboards.hookActivity', component:HookActivityWidget, defaultSize:{w:4,h:3}, needsMetric:false, configSchema:{fields:['title']} },
]

export const widgetRegistry: Record<string, DashboardWidgetDefinition> =
  Object.fromEntries(definitions.map((item) => [item.type, item]))

export interface WidgetPreset {
  id: string
  titleKey: string
  type: string
  config: Partial<DashboardWidget>
}

/**
 * A preset is a starting configuration for a generic widget, not a type of its
 * own. `LEGACY_TYPES` maps types that were once first class onto the preset that
 * replaced them, so saved layouts keep rendering.
 */
export const widgetPresets: WidgetPreset[] = [
  { id: 'charge-curve', titleKey: 'dashboards.chargeCurve', type: 'xy-chart', config: { x_metric: 'battery.soc', y_metric: 'charging.power' } },
]

const LEGACY_TYPES: Record<string, WidgetPreset> = Object.fromEntries(
  widgetPresets.map((preset) => [preset.id, preset]),
)

/** The preset a widget's configuration matches, so its head can carry that name. */
export function presetFor(widget: DashboardWidget): WidgetPreset | undefined {
  return widgetPresets.find((preset) => preset.type === widget.type
    && Object.entries(preset.config).every(([key, value]) => widget[key as keyof DashboardWidget] === value))
}

export function normalizeWidget(widget: DashboardWidget): DashboardWidget {
  const preset = LEGACY_TYPES[widget.type]
  if (!preset || widgetRegistry[widget.type]) return widget
  return { ...preset.config, ...widget, type: preset.type }
}
