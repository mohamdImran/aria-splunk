import { useIncidentStore } from '@/stores/incidentStore'

export function ImpactScore() {
  const { blastRadius } = useIncidentStore()

  if (blastRadius.length === 0) return null

  const criticalCount = blastRadius.filter(b => b.priority === 'critical').length
  const highCount     = blastRadius.filter(b => b.priority === 'high').length
  const totalScore    = blastRadius.reduce((sum, b) => sum + b.probability, 0) / blastRadius.length

  return (
    <div className="grid grid-cols-3 gap-2 text-center">
      <div className="bg-red-900/30 border border-red-500/30 rounded p-2">
        <div className="text-xl font-bold text-red-400">{criticalCount}</div>
        <div className="text-xs text-gray-400">Critical</div>
      </div>
      <div className="bg-orange-900/30 border border-orange-500/30 rounded p-2">
        <div className="text-xl font-bold text-orange-400">{highCount}</div>
        <div className="text-xs text-gray-400">High</div>
      </div>
      <div className="bg-gray-800 border border-gray-700 rounded p-2">
        <div className="text-xl font-bold text-white">{(totalScore * 100).toFixed(0)}%</div>
        <div className="text-xs text-gray-400">Avg Impact</div>
      </div>
    </div>
  )
}
