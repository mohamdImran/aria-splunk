import { useIncidentStore } from '@/stores/incidentStore'

export function StatusBar() {
  const { incident, agents, pipelineRunning } = useIncidentStore()

  const workingAgents = Object.values(agents).filter(a => a.status === 'working')
  const doneAgents    = Object.values(agents).filter(a => a.status === 'done')

  return (
    <footer className="h-7 bg-gray-950 border-t border-gray-800 flex items-center px-4 gap-6 text-xs text-gray-500">
      <span>
        Status:{' '}
        <span className={pipelineRunning ? 'text-orange-400' : 'text-green-400'}>
          {pipelineRunning ? 'Pipeline running' : incident ? 'Idle' : 'Standby'}
        </span>
      </span>

      {pipelineRunning && (
        <>
          <span>Active agents: <span className="text-yellow-400">{workingAgents.length}</span></span>
          <span>Completed: <span className="text-green-400">{doneAgents.length}/4</span></span>
        </>
      )}

      {incident && (
        <span>
          Affected services:{' '}
          <span className="text-orange-400">{incident.affected_services?.length ?? 0}</span>
        </span>
      )}

      <span className="ml-auto text-gray-600 font-mono">ARIA v1.0.0 · Splunk Agentic Ops Hackathon 2025</span>
    </footer>
  )
}
