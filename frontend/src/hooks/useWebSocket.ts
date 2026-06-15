/**
 * useIncidentWebSocket
 *
 * Single WebSocket connection per incident ID.
 * Exposes a `connected` boolean backed by React state (not a ref)
 * so the UI banner re-renders correctly when the socket opens/closes.
 *
 * On every successful open it immediately requests a full state
 * snapshot so late-joiners (e.g. curl-triggered) see the final data.
 */
import { useEffect, useRef, useCallback, useState } from 'react'
import { useIncidentStore } from '@/stores/incidentStore'
import { useSettingsStore  } from '@/stores/settingsStore'
import type { CausalGraph, BlastRadiusItem, Runbook } from '@/types/causal'
import type { AgentState, AgentMessage }              from '@/types/agent'

const BASE_DELAY_MS = 1_000
const MAX_DELAY_MS  = 16_000      

export function useIncidentWebSocket(incidentId: string | null) {
  const [connected, setConnected] = useState(false)  

  const wsRef          = useRef<WebSocket | null>(null)
  const delayRef       = useRef(BASE_DELAY_MS)
  const timerRef       = useRef<ReturnType<typeof setTimeout> | null>(null)
  const destroyedRef   = useRef(false)


  const { wsUrl } = useSettingsStore()

  const store = useIncidentStore()

  const dispatch = useCallback((raw: MessageEvent) => {
    let msg: Record<string, unknown>
    try { msg = JSON.parse(raw.data as string) } catch { return }

    const type = msg.type as string

    switch (type) {

      case 'connected':
        wsRef.current?.send(JSON.stringify({ type: 'get_state' }))
        break

      case 'state_snapshot': {
        const s = msg.state as Record<string, unknown> | null
        if (!s) break
        if (s.causal_graph)     store.setCausalGraph(s.causal_graph   as CausalGraph)
        if (s.causal_chain)     store.setCausalChain(s.causal_chain   as [])
        if (s.counterfactuals)  store.setCounterfactuals(s.counterfactuals as [])
        if (s.blast_radius)     store.setBlastRadius(s.blast_radius   as BlastRadiusItem[])
        if (s.incident_brief)   store.setIncidentBrief(s.incident_brief as string)
        if (s.root_cause || s.affected_services || s.confidence_score) {
          const current = store.incident
          if (current) {
            store.setIncident({
              ...current,
              root_cause:        (s.root_cause       as string) ?? current.root_cause,
              affected_services: (s.affected_services as string[]) ?? current.affected_services,
              confidence_score:  (s.confidence_score  as number) ?? current.confidence_score,
              brief:             (s.incident_brief    as string) ?? current.brief,
              status:            (s.status            as typeof current.status) ?? current.status,
            })
          }
        }
        if (s.runbook) {
          const rb = s.runbook as Runbook
          if (rb?.id) store.setRunbook({ id: rb.id, title: rb.title, steps: rb.steps })
        }
        if (s.completed_at) {
          store.setPipelineRunning(false)
          store.setPipelineComplete(true)
        }
        break
      }

      case 'agent_status':
        store.updateAgent(msg.agent_id as string, {
          status:       msg.status       as AgentState['status'],
          current_task: msg.task         as string,
          finding:      msg.finding      as string,
          confidence:   msg.confidence   as number,
        })
        break

      case 'agent_message':
        store.addMessage({
          from:    msg.from    as string,
          to:      msg.to      as string,
          content: msg.content as string,
          ts:      msg.ts      as string,
        } as AgentMessage)
        break

      case 'causal_update':
        store.setCausalGraph(msg.graph as CausalGraph)
        break

      case 'blast_update':
        store.setBlastRadius(msg.radius as BlastRadiusItem[])
        break

      case 'approval_required': {
        const rb = msg.runbook as Runbook
        if (rb?.id) store.setRunbook({ id: rb.id, title: rb.title, steps: rb.steps })
        store.setApprovalPending(true)
        break
      }

      case 'auto_approve_countdown':
        store.setAutoApproveCountdown(msg.seconds as number)
        break

      case 'incident_brief':
        store.setIncidentBrief(msg.brief as string)
        break

      case 'incident_started':
        store.setPipelineRunning(true)
        break

      case 'incident_completed':
        store.setPipelineRunning(false)
        store.setPipelineComplete(true)
        if (msg.brief) store.setIncidentBrief(msg.brief as string)
        break
    }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])


  const connect = useCallback(() => {
    if (!incidentId || destroyedRef.current) return
    if (wsRef.current?.readyState === WebSocket.OPEN) return 

    // Build WebSocket URL.
    // Dev:  wsUrl is '' → use same host as the page (Vite proxy forwards /ws/* to :8001)
    // Prod: wsUrl is explicit (e.g. ws://api.example.com) → connect directly.
    const wsBase = wsUrl
      ? wsUrl
      : `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`
    const url = `${wsBase}/ws/incident/${incidentId}`

    const sock = new WebSocket(url)
    wsRef.current = sock

    sock.onopen = () => {
      delayRef.current = BASE_DELAY_MS  
      setConnected(true)
    }

    sock.onmessage = dispatch

    sock.onclose = () => {
      wsRef.current = null
      setConnected(false)
      if (destroyedRef.current) return
      timerRef.current = setTimeout(() => {
        delayRef.current = Math.min(delayRef.current * 2, MAX_DELAY_MS)
        connect()
      }, delayRef.current)
    }

    sock.onerror = () => sock.close()
  }, [incidentId, wsUrl, dispatch])

  useEffect(() => {
    if (!incidentId) {
      setConnected(false)
      return
    }
    destroyedRef.current = false
    delayRef.current     = BASE_DELAY_MS
    connect()

    return () => {
      destroyedRef.current = true
      if (timerRef.current) clearTimeout(timerRef.current)
      wsRef.current?.close()
      wsRef.current = null
      setConnected(false)
    }
  }, [incidentId, connect])

  const sendApproval = useCallback((approved: boolean, notes = '') => {
    wsRef.current?.send(JSON.stringify({ type: 'approval_response', approved, notes }))
    store.setApprovalPending(false)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const sendPing = useCallback(() => {
    wsRef.current?.send(JSON.stringify({ type: 'ping' }))
  }, [])

  return { connected, sendApproval, sendPing }
}
