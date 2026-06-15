import { useIncidentStore } from '@/stores/incidentStore'
import { FlaskConical } from 'lucide-react'
import { motion } from 'framer-motion'

export function Counterfactual() {
  const { counterfactuals } = useIncidentStore()

  if (!counterfactuals || counterfactuals.length === 0) return null

  return (
    <div className="bg-gray-800/50 border border-purple-500/30 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-3">
        <FlaskConical size={15} className="text-purple-400" />
        <h3 className="text-xs font-semibold text-gray-300 uppercase tracking-wider">
          Counterfactual Analysis
        </h3>
      </div>

      <div className="space-y-3">
        {counterfactuals.map((cf, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.1 }}
            className="border border-gray-700 rounded p-3"
          >
            <p className="text-xs text-purple-300 font-medium mb-1">
              🔮 {cf.scenario}
            </p>
            <p className="text-xs text-gray-300 mb-2">{cf.predicted_impact}</p>

            {/* Comparison bar */}
            {cf.actual_value > 0 && (
              <div className="space-y-1">
                <div className="flex items-center gap-2 text-xs">
                  <span className="text-gray-500 w-20">Actual:</span>
                  <div className="flex-1 bg-gray-700 rounded-full h-1.5">
                    <div className="bg-red-500 h-full rounded-full" style={{ width: '100%' }} />
                  </div>
                  <span className="text-red-400 w-12 text-right">{cf.actual_value.toFixed(1)}</span>
                </div>
                <div className="flex items-center gap-2 text-xs">
                  <span className="text-gray-500 w-20">Counterfactual:</span>
                  <div className="flex-1 bg-gray-700 rounded-full h-1.5">
                    <div
                      className="bg-green-500 h-full rounded-full"
                      style={{ width: `${Math.min(100, (cf.counterfactual_value / cf.actual_value) * 100)}%` }}
                    />
                  </div>
                  <span className="text-green-400 w-12 text-right">{cf.counterfactual_value.toFixed(1)}</span>
                </div>
              </div>
            )}

            <p className="text-xs text-gray-600 mt-1">
              Confidence: {(cf.confidence * 100).toFixed(0)}%
            </p>
          </motion.div>
        ))}
      </div>
    </div>
  )
}
