import { useQuery } from '@tanstack/react-query'
import { useSettingsStore } from '@/stores/settingsStore'
import type { AgentDefinition } from '@/types/agent'

export function useAgentDefinitions() {
  const { apiUrl } = useSettingsStore()
  return useQuery<AgentDefinition[]>({
    queryKey: ['agents'],
    queryFn: async () => {
      const res = await fetch(`${apiUrl}/api/agents`)
      if (!res.ok) throw new Error('Failed to fetch agents')
      return res.json()
    },
    staleTime: Infinity,
  })
}
