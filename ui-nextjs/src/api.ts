import axios from 'axios'

let adminToken: string | null = null

export const apiClient = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  timeout: 15_000,
})

apiClient.interceptors.request.use((config) => {
  if (adminToken) {
    config.headers.Authorization = `Bearer ${adminToken}`
  }
  return config
})

export function setAdminToken(token: string | null): void {
  adminToken = token
}

export function getAdminWebSocketProtocols(): string[] {
  if (!adminToken) {
    return []
  }
  const bytes = new TextEncoder().encode(adminToken)
  let binary = ''
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte)
  })
  const encoded = btoa(binary)
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
  return ['ratichat-admin', `auth.${encoded}`]
}
