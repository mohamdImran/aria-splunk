import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Navbar }     from '@/components/layout/Navbar'
import { Sidebar }    from '@/components/layout/Sidebar'
import { StatusBar }  from '@/components/layout/StatusBar'
import { WarRoom }    from '@/components/war-room/WarRoom'
import { CausalGraph }        from '@/components/causal/CausalGraph'
import { CausalChain }        from '@/components/causal/CausalChain'
import { Counterfactual }     from '@/components/causal/Counterfactual'
import { BlastMap }           from '@/components/blast-radius/BlastMap'
import { ImpactScore }        from '@/components/blast-radius/ImpactScore'
import { PredictionTimeline } from '@/components/blast-radius/PredictionTimeline'
import { RunbookViewer }      from '@/components/remediation/RunbookViewer'
import { useAgentStore }      from '@/stores/agentStore'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 2000 } },
})

/* ── Page wrappers ─────────────────────────────────────────────────────────── */

function PageShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-800 shrink-0">
        <h1 className="text-sm font-semibold text-gray-300 tracking-wide">{title}</h1>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-4 min-h-0">
        {children}
      </div>
    </div>
  )
}

function CausalPage() {
  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="px-5 py-3 border-b border-gray-800 shrink-0">
        <h1 className="text-sm font-semibold text-gray-300 tracking-wide">Causal Analysis</h1>
      </div>
      {/* Graph takes the majority of height */}
      <div className="flex-1 min-h-0 overflow-hidden p-4 flex flex-col gap-4">
        <div className="flex-1 min-h-0 rounded-xl border border-gray-800 bg-gray-900/40 overflow-hidden">
          <CausalGraph />
        </div>
        <div className="grid grid-cols-2 gap-4 shrink-0">
          <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-3">
            <CausalChain />
          </div>
          <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-3">
            <Counterfactual />
          </div>
        </div>
      </div>
    </div>
  )
}

function BlastPage() {
  return (
    <PageShell title="Blast Radius">
      <ImpactScore />
      <div className="grid grid-cols-2 gap-4">
        <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-3">
          <BlastMap />
        </div>
        <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-3">
          <PredictionTimeline />
        </div>
      </div>
    </PageShell>
  )
}

function RunbooksPage() {
  return (
    <PageShell title="Runbooks">
      <div className="max-w-2xl">
        <RunbookViewer />
      </div>
    </PageShell>
  )
}

function HistoryPage() {
  return (
    <PageShell title="Incident History">
      <div className="rounded-xl border border-gray-800 bg-gray-900/40 p-6 text-center">
        <p className="text-gray-600 text-sm">No past incidents recorded yet.</p>
        <p className="text-gray-700 text-xs mt-1">Resolved incidents will appear here.</p>
      </div>
    </PageShell>
  )
}

function AgentsPage() {
  const { definitions } = useAgentStore()
  return (
    <PageShell title="Agent Registry">
      <div className="grid grid-cols-2 gap-4">
        {definitions.map(def => (
          <div key={def.id} className="rounded-xl border border-gray-800 bg-gray-900/50 p-4">
            <div className="flex items-center gap-3 mb-3">
              <span className="text-2xl">{def.icon}</span>
              <div>
                <h3 className="text-sm font-semibold text-white">{def.name}</h3>
                <p className="text-xs text-gray-500">{def.role}</p>
              </div>
            </div>
            <p className="text-xs text-gray-400 leading-relaxed mb-3">{def.description}</p>
            <div className="flex flex-wrap gap-1">
              {def.tools.map(t => (
                <span key={t} className="text-[10px] bg-gray-800 border border-gray-700 text-gray-400 px-2 py-0.5 rounded-full font-mono">
                  {t}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </PageShell>
  )
}

/* ── Root app ──────────────────────────────────────────────────────────────── */
export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="h-screen flex flex-col bg-gray-950 text-gray-100 overflow-hidden">
          <Navbar />
          <div className="flex flex-1 overflow-hidden min-h-0">
            <Sidebar />
            <main className="flex-1 overflow-hidden min-h-0 min-w-0">
              <Routes>
                <Route path="/"         element={<WarRoom />} />
                <Route path="/causal"   element={<CausalPage />} />
                <Route path="/blast"    element={<BlastPage />} />
                <Route path="/runbooks" element={<RunbooksPage />} />
                <Route path="/history"  element={<HistoryPage />} />
                <Route path="/agents"   element={<AgentsPage />} />
              </Routes>
            </main>
          </div>
          <StatusBar />
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
