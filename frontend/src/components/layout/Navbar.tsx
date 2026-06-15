import { Activity, Zap, Settings, Bell } from 'lucide-react'
import { useIncidentStore } from '@/stores/incidentStore'
import dayjs from 'dayjs'

export function Navbar() {
  const { incident, pipelineRunning } = useIncidentStore()

  return (
    <header className="h-14 bg-gray-900 border-b border-gray-700 flex items-center px-4 gap-4 z-50">
      {/* Logo */}
      <div className="flex items-center gap-2">
        <Zap className="text-orange-500" size={22} />
        <span className="font-bold text-white text-lg tracking-tight">ARIA</span>
        <span className="text-gray-400 text-xs font-mono">Agentic Resilience Intelligence Architect</span>
      </div>

      <div className="flex-1" />

      {/* Live indicator */}
      {pipelineRunning && (
        <div className="flex items-center gap-1.5 bg-red-900/40 border border-red-500/50 rounded px-2 py-0.5">
          <span className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
          <span className="text-red-400 text-xs font-semibold">LIVE INCIDENT</span>
        </div>
      )}

      {/* Incident badge */}
      {incident && (
        <div className="flex items-center gap-2 text-xs">
          <span className={`px-2 py-0.5 rounded font-bold ${
            incident.severity === 'P1' ? 'bg-red-600 text-white' :
            incident.severity === 'P2' ? 'bg-orange-600 text-white' :
            incident.severity === 'P3' ? 'bg-yellow-600 text-black' :
            'bg-gray-600 text-white'
          }`}>
            {incident.severity}
          </span>
          <span className="text-gray-400 font-mono">{incident.id}</span>
          <span className="text-gray-500">{dayjs(incident.start_time).format('HH:mm:ss')}</span>
        </div>
      )}

      <button className="p-2 text-gray-400 hover:text-white transition-colors">
        <Bell size={18} />
      </button>
      <button className="p-2 text-gray-400 hover:text-white transition-colors">
        <Settings size={18} />
      </button>
    </header>
  )
}
