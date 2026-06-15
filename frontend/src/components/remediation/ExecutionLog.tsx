import { useIncidentStore } from '@/stores/incidentStore'
import { CheckCircle, XCircle, Loader, Clock } from 'lucide-react'
import type { RunbookStepStatus } from '@/types/causal'

const STATUS_ICON: Record<RunbookStepStatus, React.ReactNode> = {
  pending:   <Clock size={14} className="text-gray-500" />,
  approved:  <Clock size={14} className="text-blue-400" />,
  running:   <Loader size={14} className="text-yellow-400 animate-spin" />,
  completed: <CheckCircle size={14} className="text-green-400" />,
  failed:    <XCircle size={14} className="text-red-400" />,
  rejected:  <XCircle size={14} className="text-orange-400" />,
}

export function ExecutionLog() {
  const { runbook } = useIncidentStore()

  if (!runbook) return null

  const executedSteps = runbook.steps.filter(s =>
    ['running', 'completed', 'failed'].includes(s.status)
  )

  if (executedSteps.length === 0) return null

  return (
    <div className="bg-gray-900 border border-gray-700 rounded-lg p-3 font-mono text-xs">
      <p className="text-gray-500 mb-2">// Execution Log</p>
      {executedSteps.map(step => (
        <div key={step.step} className="flex items-center gap-2 py-1 border-b border-gray-800 last:border-0">
          {STATUS_ICON[step.status]}
          <span className="text-gray-400">[{step.step.toString().padStart(2, '0')}]</span>
          <span className={step.status === 'completed' ? 'text-green-300' : step.status === 'failed' ? 'text-red-300' : 'text-yellow-300'}>
            {step.action}
          </span>
        </div>
      ))}
    </div>
  )
}
