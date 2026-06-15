import { useIncidentStore } from '@/stores/incidentStore'
import { ArrowRight } from 'lucide-react'
import { motion } from 'framer-motion'

export function CausalChain() {
  const { causalGraph } = useIncidentStore()

  if (!causalGraph?.rootCause) return null

  const edges = causalGraph.edges ?? []

  return (
    <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-4">
      <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
        Causal Chain
      </h3>

      <div className="flex items-center gap-1 flex-wrap">
        {/* Root cause */}
        <motion.div
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          className="px-2 py-1 rounded bg-red-900/50 border border-red-500/50 text-red-300 text-xs font-mono"
        >
          {causalGraph.rootCause.replace(/_/g, ' ')}
        </motion.div>

        {/* Chain steps */}
        {edges.slice(0, 5).map((edge, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.1 }}
            className="flex items-center gap-1"
          >
            <ArrowRight size={12} className="text-gray-500" />
            <div className="flex flex-col items-center">
              <div className="px-2 py-1 rounded bg-orange-900/40 border border-orange-600/40 text-orange-300 text-xs font-mono">
                {typeof edge.target === 'string'
                  ? edge.target.replace(/_/g, ' ')
                  : (edge.target as { id: string }).id.replace(/_/g, ' ')}
              </div>
              <span className="text-gray-600 text-xs">{(edge.strength * 100).toFixed(0)}%</span>
            </div>
          </motion.div>
        ))}
      </div>

      <div className="mt-2 text-xs text-gray-500">
        Confidence: <span className="text-orange-400">{(causalGraph.confidence * 100).toFixed(0)}%</span>
      </div>
    </div>
  )
}
