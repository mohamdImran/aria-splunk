/**
 * War Room — Main Incident Command view.
 *
 * Two ways an incident can appear:
 *
 *  1. UI button  — POST /api/incidents/demo → receive ID → open WS immediately
 *  2. curl / API — detected within ~2 s via polling → open WS → replay state
 *
 * A single WebSocket per incident is owned here and passed down where needed.
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { AgentPanel }    from './AgentPanel'
import { AgentChat }     from './AgentChat'
import { IncidentBrief } from './IncidentBrief'
import { CausalGraph }   from '@/components/causal/CausalGraph'
import { BlastMap }      from '@/components/blast-radius/BlastMap'
import { RunbookViewer } from '@/components/remediation/RunbookViewer'
import { ApprovalGate }  from '@/components/remediation/ApprovalGate'
import { ExecutionLog }  from '@/components/remediation/ExecutionLog'
import { useIncidentStore }           from '@/stores/incidentStore'
import { useSettingsStore }            from '@/stores/settingsStore'
import { useTriggerDemoIncident }      from '@/hooks/useIncident'
import { useIncidentWebSocket }        from '@/hooks/useWebSocket'
import { Play, RefreshCw, Radio, Activity } from 'lucide-react'
import { motion, AnimatePresence }     from 'framer-motion'
import type { Incident }               from '@/types/incident'

export function WarRoom() {
  const store       = useIncidentStore()
  const { apiUrl }  = useSettingsStore()
  const triggerDemo = useTriggerDemoIncident()

  const [activeId, setActiveId]   = useState<string | null>(null)

 
  const activeIdRef  = useRef<string | null>(null)
  activeIdRef.current = activeId

  const { connected, sendApproval } = useIncidentWebSocket(activeId)

  const activateIncident = useCallback((inc: Incident) => {
    store.reset()
    store.setIncident(inc)
    setActiveId(inc.id)
  }, [store])

  useEffect(() => {
    let lastSeenId: string | null = null

    const poll = async () => {
      if (activeIdRef.current) return   
      try {
        const res = await fetch(`${apiUrl}/api/incidents?limit=1`)
        if (!res.ok) return
        const list: Incident[] = await res.json()
        if (!list.length) return
        const newest = list[0]
        if (newest.id !== lastSeenId) {
          lastSeenId = newest.id
          if (!activeIdRef.current) activateIncident(newest)
        }
      } catch { /* network not ready yet */ }
    }

    const timer = setInterval(poll, 2000)
    poll()  
    return () => clearInterval(timer)
  }, [apiUrl, activateIncident])

  useEffect(() => {
    if (!activeId) return
    const timer = setInterval(async () => {
      try {
        const res = await fetch(`${apiUrl}/api/incidents/${activeId}`)
        if (!res.ok) return
        const data: Incident = await res.json()
        store.setIncident(data)
      } catch { /* non-critical */ }
    }, 3000)
    return () => clearInterval(timer)
  }, [activeId, apiUrl, store])


  const handleTriggerDemo = async () => {
    const created = await triggerDemo.mutateAsync()
    activateIncident(created)
  }

  const { incident, approvalPending, pipelineRunning } = store

  return (
    <div className="flex flex-col h-full overflow-hidden bg-gray-950">

      {/* ── Toolbar ──────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 px-5 py-3 border-b border-gray-800/80 shrink-0 bg-gray-900/60 backdrop-blur-sm">

        {/* Title + live badge */}
        <div className="flex items-center gap-2.5">
          <h1 className="text-sm font-semibold text-gray-200 tracking-wide">War Room</h1>

          <AnimatePresence>
            {pipelineRunning && (
              <motion.div
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.8 }}
                className="flex items-center gap-1.5 bg-red-900/30 border border-red-500/40 rounded px-2 py-0.5"
              >
                <Activity size={10} className="text-red-400 animate-pulse" />
                <span className="text-[10px] font-semibold text-red-400 uppercase tracking-widest">
                  Live
                </span>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Incident metadata */}
        {incident && (
          <div className="flex items-center gap-2 ml-1">
            <SeverityBadge severity={incident.severity} />
            <span className="text-gray-500 text-xs font-mono">{incident.id}</span>
            <StatusBadge status={incident.status} />
          </div>
        )}

        <div className="flex-1" />

        {/* WebSocket indicator — only show when we have an active incident */}
        {activeId && (
          <WsIndicator connected={connected} />
        )}

        {/* Demo trigger / new demo button */}
        {!incident ? (
          <motion.button
            whileHover={{ scale: 1.02 }}
            whileTap={{ scale: 0.97 }}
            onClick={handleTriggerDemo}
            disabled={triggerDemo.isPending}
            className="flex items-center gap-2 bg-orange-600 hover:bg-orange-500 disabled:opacity-50 text-white px-4 py-2 rounded-lg text-xs font-semibold transition-colors shadow-lg shadow-orange-900/30"
          >
            <Play size={13} />
            {triggerDemo.isPending ? 'Starting…' : 'Trigger Demo Incident'}
          </motion.button>
        ) : (
          <button
            onClick={handleTriggerDemo}
            disabled={triggerDemo.isPending}
            className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 border border-gray-700 hover:border-gray-500 rounded-lg px-3 py-1.5 transition-colors"
          >
            <RefreshCw size={12} className={triggerDemo.isPending ? 'animate-spin' : ''} />
            New Demo
          </button>
        )}
      </div>

      {/* ── Content grid ─────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col gap-2 p-3 overflow-hidden min-h-0">

        {/* ROW 1 — Agents | Causal Graph | Blast Radius */}
        <div className="flex gap-2 overflow-hidden min-h-0" style={{ flex: '5 5 0' }}>

          <Panel className="w-52 shrink-0" header="Agents">
            <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
              <AgentPanel />
            </div>
          </Panel>

          <Panel className="flex-1 min-w-0"
                 header="Causal Graph"
                 hint="drag · scroll to zoom · click for details">
            <div className="flex-1 min-h-0 overflow-hidden">
              <CausalGraph />
            </div>
          </Panel>

          <Panel className="w-52 shrink-0" header="Blast Radius">
            <div className="flex-1 overflow-y-auto p-2">
              <BlastMap />
            </div>
          </Panel>
        </div>

        {/* ROW 2 — Agent Communications */}
        <div className="overflow-hidden rounded-xl border border-gray-800 bg-gray-900/40"
             style={{ flex: '2 2 0' }}>
          <AgentChat />
        </div>

        {/* ROW 3 — Incident Brief | Runbook */}
        <div className="flex gap-2 overflow-hidden min-h-0" style={{ flex: '3 3 0' }}>

          <Panel className="flex-1" header="Incident Brief">
            <div className="flex-1 overflow-y-auto p-3 space-y-3">
              <IncidentBrief />
              <ExecutionLog />
            </div>
          </Panel>

          <Panel className="w-72 shrink-0" header="Runbook">
            <div className="flex-1 overflow-y-auto p-2">
              <RunbookViewer />
            </div>
          </Panel>
        </div>
      </div>

      {approvalPending && activeId && (
        <ApprovalGate incidentId={activeId} sendApproval={sendApproval} />
      )}
    </div>
  )
}


function Panel({
  children,
  header,
  hint,
  className = '',
}: {
  children: React.ReactNode
  header: string
  hint?: string
  className?: string
}) {
  return (
    <div className={`flex flex-col overflow-hidden rounded-xl border border-gray-800 bg-gray-900/40 ${className}`}>
      <div className="px-3 pt-2.5 pb-2 border-b border-gray-800 shrink-0 flex items-center gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-widest text-gray-500">
          {header}
        </span>
        {hint && (
          <span className="text-[10px] text-gray-700">{hint}</span>
        )}
      </div>
      {children}
    </div>
  )
}

function WsIndicator({ connected }: { connected: boolean }) {
  return (
    <div
      title={connected ? 'WebSocket connected' : 'WebSocket connecting…'}
      className="flex items-center gap-1.5 mr-1"
    >
      <Radio
        size={12}
        className={connected ? 'text-emerald-500' : 'text-gray-600 animate-pulse'}
      />
      <span className={`text-[10px] ${connected ? 'text-emerald-600' : 'text-gray-600'}`}>
        {connected ? 'connected' : 'connecting…'}
      </span>
    </div>
  )
}

function SeverityBadge({ severity }: { severity: string }) {
  const cls: Record<string, string> = {
    P1: 'bg-red-600/20 text-red-400 border-red-500/40',
    P2: 'bg-orange-600/20 text-orange-400 border-orange-500/40',
    P3: 'bg-yellow-600/20 text-yellow-400 border-yellow-500/40',
    P4: 'bg-gray-600/20 text-gray-400 border-gray-500/40',
  }
  return (
    <span className={`text-xs font-bold px-2 py-0.5 rounded border ${cls[severity] ?? cls.P4}`}>
      {severity}
    </span>
  )
}

function StatusBadge({ status }: { status: string }) {
  const cls: Record<string, string> = {
    investigating: 'bg-yellow-900/40 text-yellow-400',
    identified:    'bg-blue-900/40 text-blue-400',
    remediating:   'bg-orange-900/40 text-orange-400',
    resolved:      'bg-green-900/40 text-green-400',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${cls[status] ?? 'bg-gray-900/40 text-gray-400'}`}>
      {status}
    </span>
  )
}
