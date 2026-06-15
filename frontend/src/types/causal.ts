export interface CausalNode {
  id: string
  type: 'root' | 'affected' | 'at_risk' | 'healthy'
  metric?: number
  label?: string
}

export interface CausalEdge {
  source: string
  target: string
  strength: number
  discovered: boolean
  p_value?: number
}

export interface CausalGraph {
  nodes: (string | CausalNode)[]
  edges: CausalEdge[]
  rootCause: string
  confidence: number
}

export interface CausalChainStep {
  cause: string
  effect: string
  strength: number
}

export interface Counterfactual {
  scenario: string
  predicted_impact: string
  confidence: number
  actual_value: number
  counterfactual_value: number
  cause_node?: string
  outcome_node?: string
}

export interface BlastRadiusItem {
  service: string
  probability: number
  eta_minutes: number
  priority: 'critical' | 'high' | 'medium' | 'low'
  propagation_path?: string[]
}

export type RunbookStepStatus = 'pending' | 'approved' | 'running' | 'completed' | 'failed' | 'rejected'
export type RiskLevel = 'Low' | 'Medium' | 'High' | 'Critical'

export interface RunbookStep {
  step: number
  action: string
  description: string
  risk: RiskLevel
  expected_outcome: string
  estimated_duration_seconds: number
  status: RunbookStepStatus
  rollback_action?: string
}

export interface Runbook {
  id: string
  incident_id: string
  title: string
  steps: RunbookStep[]
  generated_by: string
  requires_approval: boolean
  approved: boolean
  execution_log: unknown[]
}
