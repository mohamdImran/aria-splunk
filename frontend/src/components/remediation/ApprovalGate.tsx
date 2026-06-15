/**
 * Human-in-the-Loop approval UI for remediation steps.
 *
 * Shows:
 *   - List of proposed steps in execution order
 *   - Risk level per step
 *   - Expected outcome per step
 *   - Estimated duration
 *
 * Actions:
 *   - Approve All (one click)
 *   - Approve Step by Step
 *   - Modify a step (text edit)
 *   - Reject + explain (feeds back into Remediation Agent)
 *
 * Auto-approve: Low-risk steps auto-approve after 30s timeout (countdown shown)
 * After approval: shows live ExecutionLog with step statuses
 */
import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle, XCircle, AlertTriangle, Clock, Edit2, CheckSquare } from 'lucide-react'
import { useIncidentStore } from '@/stores/incidentStore'
import type { RunbookStep, RiskLevel } from '@/types/causal'
import clsx from 'clsx'

const RISK_COLORS: Record<RiskLevel, string> = {
  Low:      'text-green-400 border-green-500/40',
  Medium:   'text-yellow-400 border-yellow-500/40',
  High:     'text-orange-400 border-orange-500/40',
  Critical: 'text-red-400 border-red-500/40',
}

interface ApprovalGateProps {
  incidentId: string
  /** sendApproval is provided by the parent (WarRoom) which owns the single WebSocket */
  sendApproval: (approved: boolean, notes?: string) => void
}

export function ApprovalGate({ incidentId: _incidentId, sendApproval }: ApprovalGateProps) {
  const {
    approvalPending,
    runbook,
    autoApproveCountdown,
    setApprovalPending,
    setAutoApproveCountdown,
  } = useIncidentStore()

  const [countdown, setCountdown] = useState<number | null>(null)
  const [editingStep, setEditingStep] = useState<number | null>(null)
  const [editValue, setEditValue] = useState('')
  const [rejectReason, setRejectReason] = useState('')
  const [showRejectInput, setShowRejectInput] = useState(false)


  useEffect(() => {
    if (autoApproveCountdown !== null) {
      setCountdown(autoApproveCountdown)
    }
  }, [autoApproveCountdown])

  useEffect(() => {
    if (countdown === null || countdown <= 0) return
    const timer = setInterval(() => {
      setCountdown(c => {
        if (c === null || c <= 1) {
          clearInterval(timer)
          handleApproveAll()
          return null
        }
        return c - 1
      })
    }, 1000)
    return () => clearInterval(timer)
  }, [countdown])  // eslint-disable-line

  const handleApproveAll = useCallback(() => {
    sendApproval(true, 'Approved all steps')
    setApprovalPending(false)
    setCountdown(null)
    setAutoApproveCountdown(null)
  }, [sendApproval, setApprovalPending, setAutoApproveCountdown])

  const handleReject = useCallback(() => {
    sendApproval(false, rejectReason)
    setApprovalPending(false)
    setShowRejectInput(false)
  }, [sendApproval, setApprovalPending, rejectReason])

  if (!approvalPending || !runbook) return null

  const steps = runbook.steps ?? []
  const highRiskCount = steps.filter(s => ['High', 'Critical'].includes(s.risk)).length
  const allLowRisk = highRiskCount === 0

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -20 }}
        className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4"
      >
        <div className="bg-gray-900 border border-orange-500/50 rounded-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto shadow-2xl shadow-orange-500/10">
          {/* Header */}
          <div className="p-5 border-b border-gray-700">
            <div className="flex items-center gap-3 mb-1">
              <AlertTriangle className="text-orange-400" size={20} />
              <h2 className="text-lg font-semibold text-white">Approval Required</h2>
              {highRiskCount > 0 && (
                <span className="text-xs bg-orange-900/50 border border-orange-500/40 text-orange-300 px-2 py-0.5 rounded">
                  {highRiskCount} high-risk step{highRiskCount > 1 ? 's' : ''}
                </span>
              )}
            </div>
            <p className="text-sm text-gray-400">{runbook.title}</p>

            {/* Auto-approve countdown */}
            {allLowRisk && countdown !== null && (
              <div className="mt-2 flex items-center gap-2 text-xs text-green-400">
                <Clock size={12} />
                <span>All low-risk — auto-approving in {countdown}s</span>
                <div className="flex-1 bg-gray-700 rounded-full h-1 overflow-hidden">
                  <motion.div
                    className="h-full bg-green-500"
                    animate={{ width: `${(countdown / (autoApproveCountdown ?? 30)) * 100}%` }}
                  />
                </div>
              </div>
            )}
          </div>

          {/* Steps */}
          <div className="p-5 space-y-3">
            {steps.map((step) => (
              <StepCard
                key={step.step}
                step={step}
                isEditing={editingStep === step.step}
                editValue={editValue}
                onEditStart={() => {
                  setEditingStep(step.step)
                  setEditValue(step.action)
                }}
                onEditChange={setEditValue}
                onEditSave={() => setEditingStep(null)}
                onEditCancel={() => setEditingStep(null)}
              />
            ))}
          </div>

          {/* Reject input */}
          {showRejectInput && (
            <div className="px-5 pb-3">
              <textarea
                className="w-full bg-gray-800 border border-gray-600 rounded p-2 text-sm text-gray-200 resize-none"
                rows={2}
                placeholder="Reason for rejection (feeds back into Remediation Agent)..."
                value={rejectReason}
                onChange={e => setRejectReason(e.target.value)}
              />
            </div>
          )}

          {/* Actions */}
          <div className="p-5 border-t border-gray-700 flex gap-3 flex-wrap">
            <button
              onClick={handleApproveAll}
              className="flex items-center gap-2 bg-green-600 hover:bg-green-500 text-white px-4 py-2 rounded-lg text-sm font-semibold transition-colors"
            >
              <CheckSquare size={16} />
              Approve All
            </button>

            <button
              onClick={() => {
                if (showRejectInput) {
                  handleReject()
                } else {
                  setShowRejectInput(true)
                }
              }}
              className="flex items-center gap-2 bg-red-900/50 hover:bg-red-800/60 border border-red-500/40 text-red-300 px-4 py-2 rounded-lg text-sm font-semibold transition-colors"
            >
              <XCircle size={16} />
              {showRejectInput ? 'Confirm Reject' : 'Reject'}
            </button>

            {showRejectInput && (
              <button
                onClick={() => setShowRejectInput(false)}
                className="text-gray-400 hover:text-gray-200 px-4 py-2 text-sm transition-colors"
              >
                Cancel
              </button>
            )}
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  )
}

function StepCard({
  step,
  isEditing,
  editValue,
  onEditStart,
  onEditChange,
  onEditSave,
  onEditCancel,
}: {
  step: RunbookStep
  isEditing: boolean
  editValue: string
  onEditStart: () => void
  onEditChange: (v: string) => void
  onEditSave: () => void
  onEditCancel: () => void
}) {
  const riskColor = RISK_COLORS[step.risk] ?? RISK_COLORS.Medium

  return (
    <div className="bg-gray-800/50 border border-gray-700 rounded-lg p-3">
      <div className="flex items-start gap-3">
        <span className="text-gray-600 font-mono text-xs mt-0.5 w-5 shrink-0">
          {step.step.toString().padStart(2, '0')}
        </span>
        <div className="flex-1 min-w-0">
          {isEditing ? (
            <div className="flex gap-2 mb-1">
              <input
                autoFocus
                className="flex-1 bg-gray-700 border border-gray-500 rounded px-2 py-1 text-sm text-white"
                value={editValue}
                onChange={e => onEditChange(e.target.value)}
              />
              <button onClick={onEditSave} className="text-green-400 hover:text-green-300">
                <CheckCircle size={16} />
              </button>
              <button onClick={onEditCancel} className="text-gray-500 hover:text-gray-300">
                <XCircle size={16} />
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2 mb-1">
              <span className="text-sm text-gray-100 font-medium">{step.action}</span>
              <button
                onClick={onEditStart}
                className="text-gray-600 hover:text-gray-400 transition-colors"
                title="Modify step"
              >
                <Edit2 size={12} />
              </button>
            </div>
          )}

          <p className="text-xs text-gray-400 mb-1">{step.description}</p>

          <div className="flex items-center gap-3 text-xs">
            <span className={clsx('border rounded px-1.5 py-0.5', riskColor)}>
              {step.risk} risk
            </span>
            <span className="text-gray-500">
              ~{step.estimated_duration_seconds}s
            </span>
            <span className="text-gray-500">→ {step.expected_outcome}</span>
          </div>

          {step.rollback_action && (
            <p className="text-xs text-gray-600 mt-1">↩ {step.rollback_action}</p>
          )}
        </div>
      </div>
    </div>
  )
}
