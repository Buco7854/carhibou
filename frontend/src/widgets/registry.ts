import BatteryGaugeWidget from './BatteryGaugeWidget.vue'
import DeviceHealthWidget from './DeviceHealthWidget.vue'
import HookActivityWidget from './HookActivityWidget.vue'
import MetricCardWidget from './MetricCardWidget.vue'
import MultiSeriesWidget from './MultiSeriesWidget.vue'
import OnlineStatusWidget from './OnlineStatusWidget.vue'
import PositionMapWidget from './PositionMapWidget.vue'
import TimeSeriesWidget from './TimeSeriesWidget.vue'
import TelemetryListWidget from './TelemetryListWidget.vue'
import VehicleMediaWidget from './VehicleMediaWidget.vue'
import VehicleSelectorWidget from './VehicleSelectorWidget.vue'
import type { DashboardWidgetDefinition } from './types'

export const widgetRegistry: Record<string, DashboardWidgetDefinition> = Object.fromEntries([
  { type:'vehicle-selector', titleKey:'dashboards.vehicleSelector', component:VehicleSelectorWidget, defaultSize:{w:12,h:1}, needsMetric:false, configSchema:{fields:['title']} },
  { type:'vehicle-media', titleKey:'dashboards.vehicleMedia', component:VehicleMediaWidget, defaultSize:{w:4,h:2}, needsMetric:false, configSchema:{fields:['vehicle_id','title']} },
  { type:'telemetry-list', titleKey:'dashboards.telemetryList', component:TelemetryListWidget, defaultSize:{w:4,h:3}, needsMetric:false, configSchema:{fields:['vehicle_id','title']} },
  { type:'metric-card', titleKey:'dashboards.metricCard', component:MetricCardWidget, defaultSize:{w:3,h:2}, needsMetric:true, configSchema:{fields:['vehicle_id','metric','title','unit']} },
  { type:'battery-gauge', titleKey:'dashboards.batteryGauge', component:BatteryGaugeWidget, defaultSize:{w:4,h:2}, needsMetric:false, configSchema:{fields:['vehicle_id','title']} },
  { type:'position-map', titleKey:'dashboards.positionMap', component:PositionMapWidget, defaultSize:{w:6,h:4}, needsMetric:false, configSchema:{fields:['vehicle_id','title']} },
  { type:'time-series', titleKey:'dashboards.timeSeries', component:TimeSeriesWidget, defaultSize:{w:6,h:3}, needsMetric:true, configSchema:{fields:['vehicle_id','metric','title','unit','time_range_days']} },
  { type:'multi-series', titleKey:'dashboards.multiSeries', component:MultiSeriesWidget, defaultSize:{w:6,h:3}, needsMetric:false, needsMetrics:true, configSchema:{fields:['vehicle_id','metrics','title','time_range_days']} },
  { type:'online-status', titleKey:'dashboards.onlineStatus', component:OnlineStatusWidget, defaultSize:{w:3,h:2}, needsMetric:false, configSchema:{fields:['vehicle_id','title']} },
  { type:'device-health', titleKey:'dashboards.deviceHealth', component:DeviceHealthWidget, defaultSize:{w:3,h:3}, needsMetric:false, configSchema:{fields:['vehicle_id','title']} },
  { type:'hook-activity', titleKey:'dashboards.hookActivity', component:HookActivityWidget, defaultSize:{w:4,h:3}, needsMetric:false, configSchema:{fields:['title']} },
].map((item)=>[item.type,item]))
