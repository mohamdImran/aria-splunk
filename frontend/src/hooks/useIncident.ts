import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useSettingsStore } from '@/stores/settingsStore'
import { useIncidentStore } from '@/stores/incidentStore'
import type { Incident } from '@/types/incident'

export function useIncidents() {
  const { apiUrl } = useSettingsStore()
  return useQuery<Incident[]>({
    queryKey: ['incidents'],
    queryFn: async () => {
      const res = await fetch(`${apiUrl}/api/incidents`)
      if (!res.ok) throw new Error('Failed to fetch incidents')
      return res.json()
    },
    refetchInterval: 5000,
  })
}

export function useIncident(incidentId: string | null) {
  const { apiUrl } = useSettingsStore()
  return useQuery<Incident>({
    queryKey: ['incident', incidentId],
    queryFn: async () => {
      const res = await fetch(`${apiUrl}/api/incidents/${incidentId}`)
      if (!res.ok) throw new Error('Failed to fetch incident')
      return res.json()
    },
    enabled: !!incidentId,
    refetchInterval: 3000,
  })
}

export function useTriggerDemoIncident() {
  const { apiUrl } = useSettingsStore()
  const qc = useQueryClient()

  return useMutation<Incident>({
    mutationFn: async () => {
      const res = await fetch(`${apiUrl}/api/incidents/demo`, { method: 'POST' })
      if (!res.ok) throw new Error('Failed to trigger demo incident')
      return res.json()
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['incidents'] })
      // NOTE: setIncident + reset are called by the WarRoom activateIncident()
      // function which receives the mutation result directly — do NOT call
      // reset() here because that would clear state the WarRoom just set.
    },
  })
}

export function useTriggerIncident() {
  const { apiUrl } = useSettingsStore()
  const qc = useQueryClient()
  const { reset } = useIncidentStore()

  return useMutation<Incident, Error, { service: string; metric: string; value: number; severity: string }>({
    mutationFn: async (payload) => {
      const body = {
        severity: payload.severity,
        trigger_event: {
          alert_name: `manual_trigger_${payload.service}`,
          service: payload.service,
          metric: payload.metric,
          value: payload.value,
          threshold: payload.value * 0.5,
          timestamp: new Date().toISOString(),
        },
      }
      const res = await fetch(`${apiUrl}/api/incidents`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error('Failed to trigger incident')
      return res.json()
    },
    onSuccess: () => {
      reset()
      qc.invalidateQueries({ queryKey: ['incidents'] })
    },
  })
}
