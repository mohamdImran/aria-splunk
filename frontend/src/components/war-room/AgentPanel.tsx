import { useIncidentStore } from '@/stores/incidentStore'
import { useAgentStore }    from '@/stores/agentStore'
import { motion }           from 'framer-motion'
import clsx from 'clsx'

type AgentStatus = 'idle' | 'working' | 'done' | 'error'

const STATUS: Record<AgentStatus, { label: string; dotCls: string; textCls: string; cardCls: string }> = {
  idle:    { label: 'Standby',  dotCls: 'bg-gray-600',               textCls: 'text-gray-600', cardCls: '' },
  working: { label: 'Working',  dotCls: 'bg-amber-400 animate-pulse', textCls: 'text-amber-400', cardCls: 'border-amber-500/30 shadow-amber-900/20 shadow-sm' },
  done:    { label: 'Complete', dotCls: 'bg-emerald-400',             textCls: 'text-emerald-400', cardCls: 'border-emerald-600/25' },
  error:   { label: 'Error',    dotCls: 'bg-red-500',                 textCls: 'text-red-400', cardCls: 'border-red-500/30' },
}

export function AgentPanel() {
  const { agents } = useIncidentStore()
  const { definitions } = useAgentStore()

  return (
    <>
      {definitions.map((def, i) => {
        const state  = agents[def.id]
        const status = (state?.status ?? 'idle') as AgentStatus
        const cfg    = STATUS[status]

        return (
          <motion.div
            key={def.id}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            className={clsx(
              'rounded-lg border border-gray-800 bg-gray-800/50 p-2.5 transition-all duration-300',
              cfg.cardCls
            )}
          >
            {/* Header row */}
            <div className="flex items-center gap-2">
              <span className="text-sm leading-none">{def.icon}</span>
              <span className="text-xs font-semibold text-gray-200 flex-1 min-w-0 truncate">{def.name}</span>
              <div className="flex items-center gap-1 shrink-0">
                <span className={clsx('w-1.5 h-1.5 rounded-full shrink-0', cfg.dotCls)} />
                <span className={clsx('text-[10px] font-medium', cfg.textCls)}>{cfg.label}</span>
              </div>
            </div>

            {/* Role */}
            <p className="text-[10px] text-gray-600 mt-0.5 mb-1">{def.role}</p>

            {/* Current task (working state) */}
            {status === 'working' && state?.current_task && (
              <p className="text-[10px] text-amber-300/80 truncate leading-tight">
                {state.current_task}
              </p>
            )}

            {/* Finding (done state) */}
            {status === 'done' && state?.finding && (
              <p className="text-[10px] text-emerald-300/80 leading-relaxed line-clamp-2">
                {state.finding}
              </p>
            )}

            {/* Confidence bar */}
            {(state?.confidence ?? 0) > 0 && (
              <div className="mt-2">
                <div className="flex justify-between items-center mb-0.5">
                  <span className="text-[9px] text-gray-600 uppercase tracking-wider">Confidence</span>
                  <span className="text-[10px] font-semibold text-gray-300">
                    {(state!.confidence * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="h-0.5 bg-gray-700 rounded-full overflow-hidden">
                  <motion.div
                    className="h-full rounded-full bg-gradient-to-r from-orange-600 to-amber-400"
                    initial={{ width: 0 }}
                    animate={{ width: `${state!.confidence * 100}%` }}
                    transition={{ duration: 1, ease: 'easeOut' }}
                  />
                </div>
              </div>
            )}
          </motion.div>
        )
      })}
    </>
  )
}
