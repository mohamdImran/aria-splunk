import { useIncidentStore } from '@/stores/incidentStore'
import { useRef, useEffect } from 'react'
import dayjs from 'dayjs'
import { MessageSquare } from 'lucide-react'

const AGENT_META: Record<string, { color: string; bg: string; icon: string }> = {
  sentinel:    { color: 'text-red-400',    bg: 'bg-red-900/20',    icon: '' },
  forensic:    { color: 'text-blue-400',   bg: 'bg-blue-900/20',   icon: '' },
  propagation: { color: 'text-amber-400',  bg: 'bg-amber-900/20',  icon: '' },
  remediation: { color: 'text-emerald-400',bg: 'bg-emerald-900/20',icon: '' },
  commander:   { color: 'text-orange-400', bg: 'bg-orange-900/20', icon: '' },
}

export function AgentChat() {
  const { agentMessages } = useIncidentStore()
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [agentMessages])

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Fixed header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-gray-800 shrink-0">
        <MessageSquare size={12} className="text-gray-500" />
        <span className="text-[10px] font-semibold uppercase tracking-widest text-gray-500">Agent Communications</span>
        {agentMessages.length > 0 && (
          <span className="ml-auto text-[10px] text-gray-600 tabular-nums">{agentMessages.length} msg</span>
        )}
      </div>

      {/* Scrollable feed */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-2 min-h-0">
        {agentMessages.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <p className="text-[11px] text-gray-700 italic">Agent communications will appear here once the pipeline starts…</p>
          </div>
        ) : (
          agentMessages.map((msg, i) => {
            const meta = AGENT_META[msg.from] ?? { color: 'text-gray-400', bg: 'bg-gray-800/30', icon: '🤖' }
            return (
              <div key={i} className="flex gap-2 min-w-0">
                <span className="shrink-0 text-xs leading-none mt-0.5">{meta.icon}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-baseline gap-1.5 flex-wrap">
                    <span className={`text-[11px] font-semibold ${meta.color}`}>
                      {msg.from.charAt(0).toUpperCase() + msg.from.slice(1)}
                    </span>
                    {msg.to && (
                      <span className="text-[10px] text-gray-600">→ {msg.to}</span>
                    )}
                    <span className="text-[10px] text-gray-700 tabular-nums ml-auto">
                      {dayjs(msg.ts).format('HH:mm:ss')}
                    </span>
                  </div>
                  <p className="text-[11px] text-gray-400 leading-relaxed mt-0.5">
                    {msg.content}
                  </p>
                </div>
              </div>
            )
          })
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
