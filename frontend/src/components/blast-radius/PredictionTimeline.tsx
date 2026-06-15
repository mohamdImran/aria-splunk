import { useIncidentStore } from '@/stores/incidentStore'
import { Clock } from 'lucide-react'

export function PredictionTimeline() {
  const { blastRadius } = useIncidentStore()

  if (blastRadius.length === 0) return null

  const groups: Record<number, typeof blastRadius> = {}
  blastRadius.forEach(b => {
    const bucket = Math.ceil(b.eta_minutes / 3) * 3
    groups[bucket] = groups[bucket] ?? []
    groups[bucket].push(b)
  })

  return (
    <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-3">
      <div className="flex items-center gap-2 mb-3">
        <Clock size={14} className="text-yellow-400" />
        <span className="text-xs font-semibold text-gray-300">Prediction Timeline</span>
      </div>

      <div className="space-y-2">
        {Object.entries(groups)
          .sort(([a], [b]) => +a - +b)
          .map(([eta, services]) => (
            <div key={eta} className="flex items-start gap-3">
              <div className="shrink-0 text-xs text-yellow-400 font-mono w-12 pt-0.5">
                T+{eta}m
              </div>
              <div className="flex flex-wrap gap-1">
                {services.map(s => (
                  <span
                    key={s.service}
                    className={`text-xs px-1.5 py-0.5 rounded font-mono ${
                      s.priority === 'critical' ? 'bg-red-900/50 text-red-300 border border-red-500/30' :
                      s.priority === 'high'     ? 'bg-orange-900/50 text-orange-300 border border-orange-500/30' :
                      'bg-yellow-900/30 text-yellow-300 border border-yellow-500/20'
                    }`}
                  >
                    {s.service}
                  </span>
                ))}
              </div>
            </div>
          ))}
      </div>
    </div>
  )
}
