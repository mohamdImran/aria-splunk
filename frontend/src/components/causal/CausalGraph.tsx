import { useEffect, useRef, useState, useCallback } from 'react'
import * as d3 from 'd3'
import { Network, ZoomIn, ZoomOut, Maximize2 } from 'lucide-react'
import { useIncidentStore } from '@/stores/incidentStore'

interface D3Node extends d3.SimulationNodeDatum {
  id: string
  type: 'root' | 'affected' | 'at_risk' | 'healthy'
}

interface D3Link extends d3.SimulationLinkDatum<D3Node> {
  source: string | D3Node
  target: string | D3Node
  strength: number
  discovered: boolean
  p_value?: number
}

type TooltipNode = { kind: 'node'; id: string; type: string }
type TooltipEdge = { kind: 'edge'; strength: number; discovered: boolean; p_value?: number }
type TooltipData = TooltipNode | TooltipEdge

const NODE_COLOR: Record<string, string> = {
  root:     '#ef4444',
  affected: '#f97316',
  at_risk:  '#eab308',
  healthy:  '#22c55e',
  default:  '#6b7280',
}

const LEGEND = [
  { color: '#ef4444', label: 'Root Cause' },
  { color: '#f97316', label: 'Affected' },
  { color: '#eab308', label: 'At Risk' },
  { color: '#22c55e', label: 'Healthy' },
] as const

export function CausalGraph() {
  const containerRef   = useRef<HTMLDivElement>(null)
  const svgRef         = useRef<SVGSVGElement>(null)
  const zoomRef        = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null)
  const simRef         = useRef<d3.Simulation<D3Node, D3Link> | null>(null)
  const rafRef         = useRef<number>(0)

  const graphRef       = useRef(useIncidentStore.getState().causalGraph)
  const blastRef       = useRef(useIncidentStore.getState().blastRadius)
  const runningRef     = useRef(useIncidentStore.getState().pipelineRunning)

  const [tooltip, setTooltip] = useState<TooltipData | null>(null)
  const [hasGraph, setHasGraph]     = useState(false)

  useEffect(() => {
    return useIncidentStore.subscribe((s) => {
      const changed =
        s.causalGraph  !== graphRef.current ||
        s.blastRadius  !== blastRef.current ||
        s.pipelineRunning !== runningRef.current

      graphRef.current   = s.causalGraph
      blastRef.current   = s.blastRadius
      runningRef.current = s.pipelineRunning
      setHasGraph(s.causalGraph !== null)

      if (changed && s.causalGraph) {
        if (containerRef.current) {
          const { clientWidth: w, clientHeight: h } = containerRef.current
          if (w > 0 && h > 0) buildGraph(w, h)
        }
      }
    })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const buildGraph = useCallback((width: number, height: number) => {
    const causalGraph = graphRef.current
    if (!svgRef.current || !causalGraph || width < 10 || height < 10) return

    simRef.current?.stop()
    cancelAnimationFrame(rafRef.current)

    const svg  = d3.select(svgRef.current)
    svg.selectAll('*').remove()
    svg.attr('width', width).attr('height', height)

    svg.append('defs').append('marker')
      .attr('id', 'aria-arrow')
      .attr('viewBox', '0 -4 8 8')
      .attr('refX', 24).attr('refY', 0)
      .attr('markerWidth', 5).attr('markerHeight', 5)
      .attr('orient', 'auto')
      .append('path').attr('d', 'M0,-4L8,0L0,4')
      .attr('fill', '#4b5563')

    const g    = svg.append('g').attr('class', 'zoom-group')
    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.15, 5])
      .on('zoom', (e) => g.attr('transform', e.transform.toString()))
    svg.call(zoom)
    zoomRef.current = zoom

    const atRisk = new Set(blastRef.current.map(b => b.service.replace(/-/g, '_')))
    const rootId = (causalGraph.rootCause ?? '').replace(/-/g, '_')

    const nodes: D3Node[] = causalGraph.nodes.map(n => {
      const id   = typeof n === 'string' ? n : (n as { id: string }).id
      const norm = id.replace(/-/g, '_')
      let type: D3Node['type'] = 'healthy'
      if (norm === rootId) type = 'root'
      else if (atRisk.has(norm)) type = 'at_risk'
      else if (causalGraph.edges?.some(e => {
        const s = typeof e.source === 'string' ? e.source : (e.source as D3Node).id
        const t = typeof e.target === 'string' ? e.target : (e.target as D3Node).id
        return s === norm || t === norm
      })) type = 'affected'
      return { id, type }
    })

    const nodeMap = new Map(nodes.map(n => [n.id, n]))

    const links: D3Link[] = causalGraph.edges
      .filter(e => {
        const s = typeof e.source === 'string' ? e.source : (e.source as D3Node).id
        const t = typeof e.target === 'string' ? e.target : (e.target as D3Node).id
        return nodeMap.has(s) && nodeMap.has(t)
      })
      .map(e => ({
        source:     typeof e.source === 'string' ? e.source : (e.source as D3Node).id,
        target:     typeof e.target === 'string' ? e.target : (e.target as D3Node).id,
        strength:   e.strength,
        discovered: e.discovered,
        p_value:    e.p_value,
      }))

    const sim = d3.forceSimulation<D3Node>(nodes)
      .force('link',      d3.forceLink<D3Node, D3Link>(links).id(d => d.id).distance(140).strength(0.6))
      .force('charge',    d3.forceManyBody().strength(-400))
      .force('center',    d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide<D3Node>(d => d.type === 'root' ? 34 : 26))
      .alphaDecay(0.02)
    simRef.current = sim

    const linkG   = g.append('g')
    const linkSel = linkG.selectAll<SVGLineElement, D3Link>('line')
      .data(links).join('line')
      .attr('stroke',       d => d.discovered ? '#4b5563' : '#2d3748')
      .attr('stroke-width', d => Math.max(1.5, d.strength * 5))
      .attr('stroke-dasharray', () => runningRef.current ? '8 4' : 'none')
      .attr('marker-end', 'url(#aria-arrow)')
      .attr('stroke-linecap', 'round')
      .style('cursor', 'pointer')
      .on('click', (_, d) => setTooltip({
        kind: 'edge',
        strength:   d.strength,
        discovered: d.discovered,
        p_value:    d.p_value,
      }))

    const edgeLabelG   = g.append('g')
    const edgeLabelSel = edgeLabelG.selectAll<SVGTextElement, D3Link>('text')
      .data(links).join('text')
      .attr('font-size', '9px').attr('fill', '#6b7280')
      .attr('text-anchor', 'middle').attr('pointer-events', 'none')
      .attr('font-family', 'Inter, system-ui, sans-serif')
      .text(d => `${(d.strength * 100).toFixed(0)}%`)

    const nodeG   = g.append('g')
    const nodeSel = nodeG.selectAll<SVGGElement, D3Node>('g')
      .data(nodes).join('g')
      .style('cursor', 'pointer')
      .on('click', (_, d) => setTooltip({ kind: 'node', id: d.id, type: d.type }))
      .call(
        d3.drag<SVGGElement, D3Node>()
          .on('start', (ev, d) => { if (!ev.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y })
          .on('drag',  (ev, d) => { d.fx = ev.x; d.fy = ev.y })
          .on('end',   (ev, d) => { if (!ev.active) sim.alphaTarget(0); d.fx = null; d.fy = null })
      )

    nodeSel.filter(d => d.type === 'root')
      .append('circle')
      .attr('r', 30)
      .attr('fill', 'none')
      .attr('stroke', '#ef4444')
      .attr('stroke-width', 1)
      .attr('stroke-opacity', 0.35)
      .attr('stroke-dasharray', '3 3')

    nodeSel.append('circle')
      .attr('r',            d => d.type === 'root' ? 22 : 16)
      .attr('fill',         d => NODE_COLOR[d.type] ?? NODE_COLOR.default)
      .attr('fill-opacity', d => d.type === 'root' ? 1 : 0.85)
      .attr('stroke',       d => NODE_COLOR[d.type] ?? NODE_COLOR.default)
      .attr('stroke-width', d => d.type === 'root' ? 0 : 1)
      .attr('stroke-opacity', 0.4)

    nodeSel.append('text')
      .attr('font-size', '10px')
      .attr('fill', '#e5e7eb')
      .attr('text-anchor', 'middle')
      .attr('dy', d => (d.type === 'root' ? 22 : 16) + 13)
      .attr('pointer-events', 'none')
      .attr('font-family', 'Inter, system-ui, sans-serif')
      .attr('font-weight', d => d.type === 'root' ? '600' : '400')
      .text(d => d.id.replace(/_/g, ' ').replace(/-/g, ' '))

    sim.on('tick', () => {
      linkSel
        .attr('x1', d => (d.source as D3Node).x ?? 0)
        .attr('y1', d => (d.source as D3Node).y ?? 0)
        .attr('x2', d => (d.target as D3Node).x ?? 0)
        .attr('y2', d => (d.target as D3Node).y ?? 0)

      edgeLabelSel
        .attr('x', d => (((d.source as D3Node).x ?? 0) + ((d.target as D3Node).x ?? 0)) / 2)
        .attr('y', d => (((d.source as D3Node).y ?? 0) + ((d.target as D3Node).y ?? 0)) / 2 - 5)

      nodeSel.attr('transform', d => `translate(${d.x ?? 0},${d.y ?? 0})`)
    })

    if (runningRef.current) {
      let offset = 0
      const animate = () => {
        offset -= 0.6
        linkSel.attr('stroke-dashoffset', String(offset))
        rafRef.current = requestAnimationFrame(animate)
      }
      rafRef.current = requestAnimationFrame(animate)
    }
  }, []) 

  useEffect(() => {
    if (!containerRef.current) return
    const ro = new ResizeObserver(entries => {
      const e = entries[0]
      if (e) buildGraph(e.contentRect.width, e.contentRect.height)
    })
    ro.observe(containerRef.current)
    return () => {
      ro.disconnect()
      simRef.current?.stop()
      cancelAnimationFrame(rafRef.current)
    }
  }, [buildGraph])

  const zoomBy = (factor: number) => {
    if (!svgRef.current || !zoomRef.current) return
    d3.select(svgRef.current).transition().duration(300)
      .call(zoomRef.current.scaleBy, factor)
  }
  const zoomReset = () => {
    if (!svgRef.current || !zoomRef.current) return
    d3.select(svgRef.current).transition().duration(400)
      .call(zoomRef.current.transform, d3.zoomIdentity)
  }

  return (
    <div ref={containerRef} className="relative w-full h-full select-none">
      <svg ref={svgRef} className="w-full h-full" />

      {/* Empty state */}
      {!hasGraph && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 pointer-events-none">
          <Network size={36} className="text-gray-700" />
          <p className="text-gray-500 text-sm">Causal graph appears after Forensic Agent runs</p>
        </div>
      )}

      {/* Zoom controls */}
      {hasGraph && (
        <div className="absolute top-3 left-3 flex flex-col gap-1">
          {[
            { icon: <ZoomIn  size={13} />, title: 'Zoom in',  action: () => zoomBy(1.4) },
            { icon: <ZoomOut size={13} />, title: 'Zoom out', action: () => zoomBy(0.7) },
            { icon: <Maximize2 size={13} />, title: 'Reset',  action: zoomReset },
          ].map(({ icon, title, action }) => (
            <button key={title} title={title} onClick={action}
              className="w-7 h-7 rounded bg-gray-800/90 border border-gray-600 text-gray-400 hover:text-white hover:border-gray-400 flex items-center justify-center transition-colors backdrop-blur-sm">
              {icon}
            </button>
          ))}
        </div>
      )}

      {/* Legend */}
      {hasGraph && (
        <div className="absolute bottom-3 left-3 flex flex-wrap gap-3 bg-gray-900/80 border border-gray-700/60 backdrop-blur-sm rounded-md px-3 py-1.5">
          {LEGEND.map(({ color, label }) => (
            <div key={label} className="flex items-center gap-1.5">
              <div className="w-2 h-2 rounded-full shrink-0" style={{ background: color }} />
              <span className="text-gray-400 text-xs">{label}</span>
            </div>
          ))}
        </div>
      )}

      {/* Tooltip */}
      {tooltip && (
        <div className="absolute top-3 right-3 bg-gray-900 border border-gray-600 rounded-lg p-3 text-xs shadow-2xl w-48 z-10">
          {tooltip.kind === 'node' ? (
            <>
              <p className="font-semibold text-white mb-1.5 capitalize">{tooltip.id.replace(/_/g, ' ')}</p>
              <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full" style={{ background: NODE_COLOR[tooltip.type] ?? NODE_COLOR.default }} />
                <span className="text-gray-300 capitalize">{tooltip.type.replace('_', ' ')}</span>
              </div>
            </>
          ) : (
            <>
              <p className="font-semibold text-white mb-1.5">Causal Edge</p>
              <p className="text-gray-400">Strength: <span className="text-orange-300 font-medium">{(tooltip.strength * 100).toFixed(1)}%</span></p>
              {tooltip.p_value != null && <p className="text-gray-400 mt-0.5">p-value: {tooltip.p_value}</p>}
              <p className="text-gray-500 mt-1">{tooltip.discovered ? '🔍 Data-discovered' : '🗺️ Topology-defined'}</p>
            </>
          )}
          <button onClick={() => setTooltip(null)}
            className="mt-2 text-gray-600 hover:text-gray-400 text-xs transition-colors">
            dismiss ×
          </button>
        </div>
      )}
    </div>
  )
}
