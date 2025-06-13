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
  total_cycles?: number
  messages_processed?: number
  integrations?: Record<string, any>
  recent_activities?: Array<{
    timestamp: string
    activity: string
    details?: string
  }>
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

// World State types
export interface WorldState {
  [key: string]: any
  channels?: Record<string, any>
  recent_media_actions?: {
    recent_media_actions: any[]
    images_recently_described: string[]
    recent_generations: any[]
    summary: {
      total_recent_media_actions: number
      described_images_count: number
      generated_media_count: number
    }
  }
  action_history?: any[]
  meta_info?: Record<string, any>
  current_task?: string
  processing_mode?: string
  nodes?: Array<{
    id: string
    type: string
    data: any
    connections: string[]
  }>
  recent_actions?: Array<{
    timestamp: string
    action: string
    result: any
  }>
  summary?: {
    total_nodes: number
    active_channels: number
    recent_activity_count: number
  }
}

// Configuration types
export interface Configuration {
  [key: string]: any
  ai?: {
    temperature?: number
    model?: string
    multimodal_model?: string
  }
  processing?: {
    max_expanded_nodes?: number
    auto_collapse_threshold?: number
  }
  rate_limits?: {
    max_cycles_per_hour?: number
    max_actions_per_hour?: number
  }
  farcaster?: {
    min_post_interval_minutes?: number
    duplicate_check_hours?: number
    recent_posts_limit?: number
  }
  storage?: {
    history_retention_days?: number
  }
  logging?: {
    level?: string
  }
  editable_keys?: string[]
}
