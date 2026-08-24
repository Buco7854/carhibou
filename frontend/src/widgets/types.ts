import type { Component } from 'vue'
import type { DashboardWidget } from '../api/types'

export interface WidgetSize { w:number; h:number }
export interface DashboardWidgetDefinition {
  type: string
  titleKey: string
  component: Component
  defaultSize: WidgetSize
  needsMetric: boolean
  needsMetrics?: boolean
  configSchema: { fields: string[] }
}

export interface WidgetProps { widget:DashboardWidget }
