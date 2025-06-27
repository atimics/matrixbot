// Core system types
export interface SystemStatus {
  system_running: boolean;
  config: {
    processing_mode: string;
    ai_model: string;
    max_actions_per_cycle: number;
  };
  world_state: {
    channels_count: number;
    total_messages: number;
    action_history_count: number;
    pending_invites: number;
    generated_media_count: number;
    research_entries: number;
  };
  tools: Record<string, any>;
  rate_limits: Record<string, any>;
  integrations: Integration[] | { error: string };
  processing: Record<string, any>;
  uptime_seconds: number;
}

// Integration types
export interface Integration {
  id: string;
  type: string;
  display_name: string;
  status: 'connected' | 'disconnected' | 'error' | 'connecting';
  config: Record<string, any>;
  last_activity?: string;
  error_message?: string;
}

export interface IntegrationConfig {
  integration_type: string;
  display_name: string;
  config: Record<string, any>;
  credentials?: Record<string, string>;
}

// Farcaster specific types
export interface FarcasterConfig {
  api_key?: string;
  signer_uuid?: string;
  bot_fid?: string;
  webhook_url?: string;
  frames_base_url?: string;
}

export interface FarcasterSignerStatus {
  connected: boolean;
  signer_uuid?: string;
  approved: boolean;
  fid?: number;
  custody_address?: string;
  error?: string;
}

// Matrix types
export interface MatrixConfig {
  homeserver_url: string;
  username: string;
  password?: string;
  access_token?: string;
  device_id?: string;
  sync_token?: string;
}

export interface MatrixConnectionStatus {
  connected: boolean;
  homeserver_url?: string;
  user_id?: string;
  device_id?: string;
  rooms_count?: number;
  sync_status?: 'syncing' | 'idle' | 'error';
  error?: string;
}

// Arweave types
export interface ArweaveConfig {
  wallet_path?: string;
  gateway_url?: string;
  uploader_service_url?: string;
  api_key?: string;
}

export interface ArweaveWalletInfo {
  address: string;
  balance_ar: string;
  balance_winston: string;
  status: 'ready' | 'loading' | 'error';
  error?: string;
}

// Frame types
export interface FrameConfig {
  enabled: boolean;
  base_url: string;
  default_image?: string;
  mint_enabled?: boolean;
  nft_contract?: string;
}

// Tool types
export interface Tool {
  name: string;
  enabled: boolean;
  description: string;
  status: 'active' | 'disabled' | 'error';
  usage_count?: number;
  last_used?: string;
}

// AI Configuration
export interface AIConfig {
  model: string;
  system_prompt: string;
  temperature: number;
  max_tokens: number;
  api_key?: string;
}

// Log types
export interface LogEntry {
  timestamp: string;
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';
  logger: string;
  message: string;
  module?: string;
  function?: string;
  line?: number;
}

// Service health types
export interface ServiceHealth {
  name: string;
  status: 'healthy' | 'degraded' | 'unhealthy';
  url?: string;
  last_check: string;
  response_time?: number;
  error?: string;
}

// Setup and onboarding types
export interface SetupStep {
  id: string;
  title: string;
  description: string;
  status: 'pending' | 'in_progress' | 'completed' | 'error';
  required: boolean;
  component?: string;
}

export interface SetupState {
  current_step: string;
  completed_steps: string[];
  setup_status: 'not_started' | 'in_progress' | 'completed';
  errors: Record<string, string>;
}

// API response types
export interface ApiResponse<T = any> {
  data?: T;
  error?: string;
  message?: string;
  status?: string;
  timestamp?: string;
}

export interface StatusResponse {
  status: string;
  message: string;
  timestamp: string;
}

// Dashboard widget types
export interface DashboardWidget {
  id: string;
  title: string;
  type: 'metric' | 'chart' | 'status' | 'log' | 'config';
  size: 'small' | 'medium' | 'large';
  data: any;
  refreshInterval?: number;
}

// Navigation types
export interface NavItem {
  id: string;
  label: string;
  icon: string;
  href: string;
  badge?: string | number;
  children?: NavItem[];
}

// Configuration forms
export interface ConfigFormField {
  name: string;
  label: string;
  type: 'text' | 'password' | 'url' | 'number' | 'boolean' | 'select' | 'textarea';
  required: boolean;
  placeholder?: string;
  description?: string;
  options?: { value: string; label: string }[];
  validation?: {
    pattern?: string;
    min?: number;
    max?: number;
  };
}

export interface ConfigSection {
  id: string;
  title: string;
  description: string;
  fields: ConfigFormField[];
}
