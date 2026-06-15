import { useIncidentStore } from '@/stores/incidentStore'
import { motion }           from 'framer-motion'
import { Layers }           from 'lucide-react'

const P: Record<string, { bar: string; text: string; badge: string }> = {
  critical: { bar: 'bg-red-500',    text: 'text-red-400',    badge: 'bg-red-900/40 border-red-500/40 text-red-300' },
  high:     { bar: 'bg-orange-500', text: 'text-orange-400', badge: 'bg-orange-900/40 border-orange-500/40 text-orange-300' },
  medium:   { bar: 'bg-amber-500',  text: 'text-amber-400',  badge: 'bg-amber-900/30 border-amber-500/30 text-amber-300' },
  low:      { bar: 'bg-emerald-500',text: 'text-emerald-400',badge: 'bg-emerald-900/20 border-emerald-500/25 text-emerald-300' },
}

export function BlastMap() {
  const { blastRadius } = useIncidentStore()

  if (blastRadius.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-2 text-gray-700 py-6">
        <Layers size={22} className="opacity-40" />
        <p className="text-[11px] text-center leading-relaxed">
          Blast radius prediction<br />appears after Propagation Agent
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-1.5">
      {blastRadius.map((item, i) => {
        const c = P[item.priority] ?? P.low
        return (
          <motion.div
            key={item.service}
            initial={{ opacity: 0, x: 12 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.04, duration: 0.25 }}
            className="rounded-lg border border-gray-800 bg-gray-800/40 p-2"
          >
            {/* Service + badges */}
            <div className="flex items-center gap-1.5 mb-1.5">
              <span className="text-[11px] font-mono text-gray-200 flex-1 min-w-0 truncate">{item.service}</span>
              <span className={`text-[9px] font-semibold px-1.5 py-0.5 rounded border shrink-0 ${c.badge}`}>
                {item.priority.toUpperCase()}
              </span>
              {item.eta_minutes > 0 && (
                <span className="text-[10px] text-gray-600 shrink-0 tabular-nums">T+{item.eta_minutes}m</span>
              )}
            </div>

            {/* Impact bar */}
            <div className="flex items-center gap-2">
              <div className="flex-1 h-1 bg-gray-700/80 rounded-full overflow-hidden">
                <motion.div
                  className={`h-full rounded-full ${c.bar}`}
                  initial={{ width: 0 }}
                  animate={{ width: `${item.probability * 100}%` }}
                  transition={{ duration: 0.7, delay: i * 0.04, ease: 'easeOut' }}
                />
              </div>
              <span className={`text-[10px] font-bold ${c.text} w-7 text-right tabular-nums shrink-0`}>
                {(item.probability * 100).toFixed(0)}%
              </span>
            </div>

            {/* Path */}
            {(item.propagation_path?.length ?? 0) > 1 && (
              <p className="text-[9px] text-gray-700 mt-1 truncate font-mono">
                {item.propagation_path!.join(' → ')}
              </p>
            )}
          </motion.div>
        )
      })}
    </div>
  )
}
