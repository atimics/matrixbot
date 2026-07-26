'use client'

import { useEffect, useState, type FormEvent } from 'react'
import SetupWizard from '@/components/SetupWizard'
import Dashboard from '@/components/Dashboard'
import LoadingSpinner from '@/components/ui/LoadingSpinner'
import { apiClient, setAdminToken } from '@/api'
import { SystemInfo } from '@/types'

export default function Home() {
  const [systemInfo, setSystemInfo] = useState<SystemInfo>({ status: 'LOADING' })
  const [error, setError] = useState<string | null>(null)
  const [tokenInput, setTokenInput] = useState('')
  const [authenticated, setAuthenticated] = useState(false)
  const [authenticating, setAuthenticating] = useState(false)

  const checkSystemStatus = async () => {
    try {
      const response = await apiClient.get('/api/status')
      const systemData = response.data as SystemInfo
      setSystemInfo(systemData)
      setError(null)
      return true
    } catch (err: any) {
      console.error('Failed to fetch system status:', err)
      setError(err.response?.data?.detail || 'Failed to connect to the backend')
      setSystemInfo({ status: 'ERROR' })
      return false
    }
  }

  useEffect(() => {
    if (!authenticated) return
    // Poll status every 30 seconds
    const interval = setInterval(checkSystemStatus, 30000)
    return () => clearInterval(interval)
  }, [authenticated])

  const handleAuthenticate = async (event: FormEvent) => {
    event.preventDefault()
    if (new TextEncoder().encode(tokenInput).length < 32) {
      setError('The management token must be at least 32 bytes.')
      return
    }

    setAuthenticating(true)
    setAdminToken(tokenInput)
    const accepted = await checkSystemStatus()
    if (accepted) {
      setAuthenticated(true)
      setTokenInput('')
    } else {
      setAdminToken(null)
    }
    setAuthenticating(false)
  }

  const handleSetupComplete = () => {
    // Refresh system status after setup completion
    checkSystemStatus()
  }

  if (!authenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <form
          onSubmit={handleAuthenticate}
          className="w-full max-w-md rounded-lg bg-white p-8 shadow"
        >
          <h1 className="text-2xl font-semibold text-gray-900">
            Ratichat administration
          </h1>
          <p className="mt-2 text-sm text-gray-600">
            Enter the local management token. It is kept only in this page&apos;s
            memory and is cleared on reload.
          </p>
          <label className="mt-6 block text-sm font-medium text-gray-700">
            Management token
          </label>
          <input
            type="password"
            autoComplete="off"
            value={tokenInput}
            onChange={(event) => setTokenInput(event.target.value)}
            className="mt-2 w-full rounded-md border border-gray-300 px-3 py-2"
          />
          {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
          <button
            type="submit"
            disabled={authenticating}
            className="mt-6 w-full rounded-md bg-blue-600 px-4 py-2 text-white disabled:bg-gray-400"
          >
            {authenticating ? 'Authenticating…' : 'Authenticate'}
          </button>
        </form>
      </div>
    )
  }

  if (systemInfo.status === 'LOADING') {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <LoadingSpinner size="large" />
      </div>
    )
  }

  if (systemInfo.status === 'ERROR') {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center max-w-md mx-auto p-6">
          <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <h2 className="text-xl font-semibold text-gray-900 mb-2">
            Connection Failed
          </h2>
          <p className="text-gray-600 mb-4">
            {error || 'Unable to connect to the Ratichat backend'}
          </p>
          <button
            onClick={checkSystemStatus}
            className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 transition-colors"
          >
            Retry Connection
          </button>
        </div>
      </div>
    )
  }

  if (systemInfo.setup_status === 'SETUP_REQUIRED' || systemInfo.status === 'SETUP_REQUIRED') {
    return <SetupWizard onComplete={handleSetupComplete} />
  }

  return <Dashboard systemInfo={systemInfo} onStatusChange={setSystemInfo} />
}
