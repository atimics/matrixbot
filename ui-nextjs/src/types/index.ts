// Shared type definitions for the Ratichat Admin UI

export type SystemStatus = 'SETUP_REQUIRED' | 'OPERATIONAL' | 'ERROR' | 'LOADING'

export interface SystemInfo {
  status: SystemStatus
  setup_status?: string
  version?: string
  uptime?: number
  message?: string
  system_running?: boolean
  processing?: any
  world_state?: any
  tools?: any
  rate_limits?: any
  config?: any
  setup?: any
  timestamp?: string
}

export interface SetupStep {
  key: string
  question: string
  type: 'text' | 'password' | 'select'
  options?: string[]
  validation?: string
  completed?: boolean
}

export interface DashboardProps {
  systemInfo: SystemInfo
  onStatusChange: (info: SystemInfo) => void
}

// Tool-related types
export interface Tool {
  name: string
  enabled: boolean
  description: string
  parameters: Record<string, any>
  category: string
  last_used?: string | null
  success_rate?: number | null
}

export interface ToolsResponse {
  tools: Tool[]
  total_count: number
  enabled_count: number
  stats: Record<string, any>
}
