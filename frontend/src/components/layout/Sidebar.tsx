import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { LayoutDashboard, Shield, Network, BookOpen, History, Cpu, ChevronLeft, ChevronRight } from 'lucide-react'
import { useIncidentStore } from '@/stores/incidentStore'
import { motion, AnimatePresence } from 'framer-motion'
import clsx from 'clsx'

const NAV_ITEMS = [
  { path: '/',          label: 'War Room',   icon: LayoutDashboard },
  { path: '/causal',    label: 'Causal',     icon: Network },
  { path: '/blast',     label: 'Blast Map',  icon: Shield },
  { path: '/runbooks',  label: 'Runbooks',   icon: BookOpen },
  { path: '/history',   label: 'History',    icon: History },
  { path: '/agents',    label: 'Agents',     icon: Cpu },
]

export function Sidebar() {
  const location = useLocation()
  const { approvalPending } = useIncidentStore()
  const [expanded, setExpanded] = useState(false)

  return (
    <motion.aside
      animate={{ width: expanded ? 200 : 56 }}
      transition={{ duration: 0.22, ease: 'easeInOut' }}
      className="bg-gray-900 border-r border-gray-700 flex flex-col py-3 overflow-hidden shrink-0"
      style={{ minWidth: expanded ? 200 : 56 }}
    >
      {/* Nav items */}
      <nav className="flex flex-col gap-0.5 px-2 flex-1">
        {NAV_ITEMS.map(({ path, label, icon: Icon }) => {
          const active = location.pathname === path
          const badge  = path === '/runbooks' && approvalPending

          return (
            <Link
              key={path}
              to={path}
              className={clsx(
                'relative flex items-center gap-3 h-10 rounded-lg px-2.5 transition-colors group',
                active
                  ? 'bg-orange-500/15 text-orange-400'
                  : 'text-gray-500 hover:text-gray-100 hover:bg-gray-800'
              )}
            >
              {/* Active bar */}
              {active && (
                <span className="absolute left-0 top-2 bottom-2 w-0.5 rounded-full bg-orange-400" />
              )}

              <Icon size={18} className="shrink-0" />

              <AnimatePresence>
                {expanded && (
                  <motion.span
                    initial={{ opacity: 0, width: 0 }}
                    animate={{ opacity: 1, width: 'auto' }}
                    exit={{ opacity: 0, width: 0 }}
                    transition={{ duration: 0.15 }}
                    className="text-sm font-medium whitespace-nowrap overflow-hidden"
                  >
                    {label}
                  </motion.span>
                )}
              </AnimatePresence>

              {badge && (
                <span className="absolute top-2 right-2 w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
              )}

              {/* Tooltip when collapsed */}
              {!expanded && (
                <span className="
                  pointer-events-none absolute left-full ml-2 px-2 py-1
                  bg-gray-800 border border-gray-600 text-gray-200 text-xs rounded
                  whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity z-50
                ">
                  {label}
                </span>
              )}
            </Link>
          )
        })}
      </nav>

      {/* Expand / collapse toggle */}
      <div className="px-2 mt-2 border-t border-gray-800 pt-2">
        <button
          onClick={() => setExpanded(e => !e)}
          className={clsx(
            'flex items-center gap-3 w-full h-10 rounded-lg px-2.5',
            'text-gray-500 hover:text-gray-200 hover:bg-gray-800 transition-colors'
          )}
        >
          {expanded ? <ChevronLeft size={18} className="shrink-0" /> : <ChevronRight size={18} className="shrink-0" />}
          <AnimatePresence>
            {expanded && (
              <motion.span
                initial={{ opacity: 0, width: 0 }}
                animate={{ opacity: 1, width: 'auto' }}
                exit={{ opacity: 0, width: 0 }}
                transition={{ duration: 0.15 }}
                className="text-sm whitespace-nowrap overflow-hidden"
              >
                Collapse
              </motion.span>
            )}
          </AnimatePresence>
        </button>
      </div>
    </motion.aside>
  )
}
