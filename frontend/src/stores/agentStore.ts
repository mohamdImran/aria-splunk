import { create } from 'zustand'
import type { AgentDefinition } from '@/types/agent'

interface AgentStore {
  definitions: AgentDefinition[]
  setDefinitions: (defs: AgentDefinition[]) => void
}

export const useAgentStore = create<AgentStore>((set) => ({
  definitions: [
    {
      id: 'sentinel',
      name: 'Sentinel',
      role: 'Anomaly Detection',
      description: 'Monitors Splunk for anomalies. Classifies incident severity P1-P4.',
      tools: ['splunk_search', 'splunk_get_alerts', 'splunk_get_metrics'],
      icon: '',
    },
    {
      id: 'forensic',
      name: 'Forensic',
      role: 'Causal Root Cause Analysis',
      description: 'True causal inference via PC algorithm + DoWhy. Not correlation — causation.',
      tools: ['splunk_search', 'splunk_get_metrics', 'splunk_run_model'],
      icon: '',
    },
    {
      id: 'propagation',
      name: 'Propagation',
      role: 'Blast Radius Prediction',
      description: 'Predicts which services WILL fail next — 3-5 min early warning.',
      tools: ['splunk_get_metrics', 'splunk_search'],
      icon: '',
    },
    {
      id: 'remediation',
      name: 'Remediation',
      role: 'Auto-Remediation',
      description: 'Generates and executes runbooks. Human-in-the-loop approval gate.',
      tools: ['splunk_execute_action', 'splunk_create_alert', 'splunk_update_dashboard'],
      icon: '',
    },
  ],
  setDefinitions: (definitions) => set({ definitions }),
}))
