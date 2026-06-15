import { create } from 'zustand'
import type { Incident } from '@/types/incident'
import type { CausalGraph, BlastRadiusItem, RunbookStep, Counterfactual } from '@/types/causal'
import type { AgentState, AgentMessage } from '@/types/agent'

interface IncidentStore {

  incident: Incident | null
  incidentBrief: string

  causalGraph: CausalGraph | null
  causalChain: { cause: string; effect: string; strength: number }[]
  counterfactuals: Counterfactual[]

  blastRadius: BlastRadiusItem[]

  agents: Record<string, AgentState>
  agentMessages: AgentMessage[]

  runbook: { steps: RunbookStep[]; title: string; id: string } | null
  approvalPending: boolean
  autoApproveCountdown: number | null

  pipelineRunning: boolean
  pipelineComplete: boolean

  setIncident: (i: Incident) => void
  setIncidentBrief: (brief: string) => void
  updateAgent: (id: string, data: Partial<AgentState>) => void
  addMessage: (msg: AgentMessage) => void
  setCausalGraph: (g: CausalGraph) => void
  setCausalChain: (chain: IncidentStore['causalChain']) => void
  setCounterfactuals: (cf: Counterfactual[]) => void
  setBlastRadius: (b: BlastRadiusItem[]) => void
  setRunbook: (r: IncidentStore['runbook']) => void
  setApprovalPending: (p: boolean) => void
  setAutoApproveCountdown: (n: number | null) => void
  setPipelineRunning: (r: boolean) => void
  setPipelineComplete: (c: boolean) => void
  reset: () => void
}

const INITIAL_AGENTS: Record<string, AgentState> = {
  sentinel:    { agent_id: 'sentinel',    name: 'Sentinel',    status: 'idle', current_task: '', finding: '', confidence: 0 },
  forensic:    { agent_id: 'forensic',    name: 'Forensic',    status: 'idle', current_task: '', finding: '', confidence: 0 },
  propagation: { agent_id: 'propagation', name: 'Propagation', status: 'idle', current_task: '', finding: '', confidence: 0 },
  remediation: { agent_id: 'remediation', name: 'Remediation', status: 'idle', current_task: '', finding: '', confidence: 0 },
}

export const useIncidentStore = create<IncidentStore>((set) => ({
  incident: null,
  incidentBrief: '',
  causalGraph: null,
  causalChain: [],
  counterfactuals: [],
  blastRadius: [],
  agents: INITIAL_AGENTS,
  agentMessages: [],
  runbook: null,
  approvalPending: false,
  autoApproveCountdown: null,
  pipelineRunning: false,
  pipelineComplete: false,

  setIncident: (incident) => set({ incident }),
  setIncidentBrief: (incidentBrief) => set({ incidentBrief }),
  updateAgent: (id, data) =>
    set((s) => ({
      agents: {
        ...s.agents,
        [id]: { ...s.agents[id], ...data },
      },
    })),
  addMessage: (msg) =>
    set((s) => ({ agentMessages: [...s.agentMessages, msg] })),
  setCausalGraph: (causalGraph) => set({ causalGraph }),
  setCausalChain: (causalChain) => set({ causalChain }),
  setCounterfactuals: (counterfactuals) => set({ counterfactuals }),
  setBlastRadius: (blastRadius) => set({ blastRadius }),
  setRunbook: (runbook) => set({ runbook }),
  setApprovalPending: (approvalPending) => set({ approvalPending }),
  setAutoApproveCountdown: (autoApproveCountdown) => set({ autoApproveCountdown }),
  setPipelineRunning: (pipelineRunning) => set({ pipelineRunning }),
  setPipelineComplete: (pipelineComplete) => set({ pipelineComplete }),
  reset: () =>
    set({
      incident: null,
      incidentBrief: '',
      causalGraph: null,
      causalChain: [],
      counterfactuals: [],
      blastRadius: [],
      agents: INITIAL_AGENTS,
      agentMessages: [],
      runbook: null,
      approvalPending: false,
      autoApproveCountdown: null,
      pipelineRunning: false,
      pipelineComplete: false,
    }),
}))
