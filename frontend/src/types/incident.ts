export type Severity = 'P1' | 'P2' | 'P3' | 'P4'
export type IncidentStatus = 'investigating' | 'identified' | 'remediating' | 'resolved'

export interface TriggerEvent {
  alert_name: string
  service: string
  metric: string
  value: number
  threshold: number
  timestamp: string
}

export interface Incident {
  id: string
  severity: Severity
  status: IncidentStatus
  start_time: string
  end_time?: string
  affected_services: string[]
  brief: string
  trigger_event: TriggerEvent
  confidence_score: number
  root_cause?: string
}
