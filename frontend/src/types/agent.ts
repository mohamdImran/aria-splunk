export type AgentStatus = 'idle' | 'working' | 'done' | 'error'

export interface AgentState {
  agent_id: string
  name: string
  status: AgentStatus
  current_task: string
  finding: string
  confidence: number
  error?: string
}

export interface AgentMessage {
  from: string
  to: string
  content: string
  ts: string
  message_type?: 'info' | 'finding' | 'request' | 'handoff'
}

export interface AgentDefinition {
  id: string
  name: string
  role: string
  description: string
  tools: string[]
  icon: string
}
