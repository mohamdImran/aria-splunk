import { create } from 'zustand'

interface SettingsStore {
  apiUrl: string
  wsUrl: string
  autoApproveTimeout: number
  demoMode: boolean
  theme: 'dark' | 'light'
  setApiUrl: (url: string) => void
  setDemoMode: (v: boolean) => void
}

/**
 * API URL strategy:
 *
 * Development (Vite dev server on :3000):
 *   - I'll Use EMPTY string so every fetch goes to a relative path (/api/...).
 *   - Vite's proxy (vite.config.ts) forwards /api → http://localhost:8001
 *     and /ws → ws://localhost:8001 — this sidesteps all CORS issues.
 *
 * Production / Docker:
 *   - Set VITE_API_URL=http://your-backend-host in the environment.
 *   - Nginx handles the proxy and CORS headers server-side.
 *
 * Note: Splunk Enterprise occupies port 8000. ARIA backend runs on 8001.
 */
const _env = (import.meta as unknown as { env: Record<string, string> }).env

// In dev, VITE_API_URL is intentionally not set → empty string → relative URLs
const API_URL: string = _env?.VITE_API_URL ?? ''

// WebSocket URL: in dev use the same host/port as the page (Vite proxies /ws)
const WS_URL: string = API_URL
  ? API_URL.replace(/^http/, 'ws')
  : ''   // empty → relative ws:// constructed at connection time

export const useSettingsStore = create<SettingsStore>((set) => ({
  apiUrl: API_URL,
  wsUrl: WS_URL,
  autoApproveTimeout: 30,
  demoMode: true,
  theme: 'dark',
  setApiUrl: (apiUrl) => set({ apiUrl, wsUrl: apiUrl.replace(/^http/, 'ws') }),
  setDemoMode: (demoMode) => set({ demoMode }),
}))
