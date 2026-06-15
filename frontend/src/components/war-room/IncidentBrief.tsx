import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useIncidentStore } from '@/stores/incidentStore'
import { AlertCircle } from 'lucide-react'

/* Custom renderer map — maps markdown elements to styled HTML */
const mdComponents = {
  h1: ({ children }: { children?: React.ReactNode }) => (
    <h1 className="text-base font-bold text-white mb-2 mt-0">{children}</h1>
  ),
  h2: ({ children }: { children?: React.ReactNode }) => (
    <h2 className="text-sm font-semibold text-gray-200 mb-1.5 mt-3 first:mt-0 border-b border-gray-700/60 pb-1">{children}</h2>
  ),
  h3: ({ children }: { children?: React.ReactNode }) => (
    <h3 className="text-xs font-semibold text-gray-300 mb-1 mt-2 uppercase tracking-wider">{children}</h3>
  ),
  p: ({ children }: { children?: React.ReactNode }) => (
    <p className="text-xs text-gray-300 leading-relaxed mb-1.5">{children}</p>
  ),
  strong: ({ children }: { children?: React.ReactNode }) => (
    <strong className="font-semibold text-gray-100">{children}</strong>
  ),
  em: ({ children }: { children?: React.ReactNode }) => (
    <em className="italic text-gray-400">{children}</em>
  ),
  code: ({ children, className }: { children?: React.ReactNode; className?: string }) => {
    const isBlock = className?.includes('language-')
    return isBlock ? (
      <code className="block bg-gray-800 border border-gray-700 rounded-md p-2.5 text-xs text-green-300 font-mono my-2 overflow-x-auto whitespace-pre">
        {children}
      </code>
    ) : (
      <code className="bg-gray-800 border border-gray-700/60 rounded px-1.5 py-0.5 text-xs text-orange-300 font-mono">
        {children}
      </code>
    )
  },
  ul: ({ children }: { children?: React.ReactNode }) => (
    <ul className="list-none space-y-0.5 my-1.5 pl-0">{children}</ul>
  ),
  ol: ({ children }: { children?: React.ReactNode }) => (
    <ol className="list-decimal list-inside space-y-0.5 my-1.5 text-xs text-gray-300">{children}</ol>
  ),
  li: ({ children }: { children?: React.ReactNode }) => (
    <li className="flex items-start gap-1.5 text-xs text-gray-300">
      <span className="text-orange-500 mt-0.5 shrink-0 text-[8px]">▶</span>
      <span>{children}</span>
    </li>
  ),
  blockquote: ({ children }: { children?: React.ReactNode }) => (
    <blockquote className="border-l-2 border-orange-500/60 pl-3 my-2 text-xs text-gray-400 italic">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="border-gray-700/60 my-3" />,
  a: ({ children, href }: { children?: React.ReactNode; href?: string }) => (
    <a href={href} className="text-orange-400 hover:text-orange-300 underline underline-offset-2 text-xs transition-colors" target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
  table: ({ children }: { children?: React.ReactNode }) => (
    <div className="overflow-x-auto my-2">
      <table className="w-full text-xs border-collapse">{children}</table>
    </div>
  ),
  th: ({ children }: { children?: React.ReactNode }) => (
    <th className="text-left py-1.5 px-2 bg-gray-800 border border-gray-700 font-semibold text-gray-300 text-[10px] uppercase tracking-wider">{children}</th>
  ),
  td: ({ children }: { children?: React.ReactNode }) => (
    <td className="py-1.5 px-2 border border-gray-800 text-gray-400">{children}</td>
  ),
}

export function IncidentBrief() {
  const { incidentBrief, incident } = useIncidentStore()

  if (!incidentBrief && !incident) return (
    <div className="flex flex-col items-center justify-center h-full gap-2 text-gray-600">
      <AlertCircle size={24} className="opacity-30" />
      <p className="text-xs">Brief will appear after Commander synthesis</p>
    </div>
  )

  if (!incidentBrief) return (
    <div className="text-xs text-gray-600 italic">
      Waiting for all agents to complete…
    </div>
  )

  return (
    <div className="text-xs">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={mdComponents as Record<string, React.ComponentType>}
      >
        {incidentBrief}
      </ReactMarkdown>
    </div>
  )
}
