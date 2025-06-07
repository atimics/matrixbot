'use client'

import { useEffect, useState } from 'react'
import SetupWizard from '@/components/SetupWizard'
import Dashboard from '@/components/Dashboard'
import LoadingSpinner from '@/components/ui/LoadingSpinner'
import { apiClient } from '@/lib/api'

type SystemStatus = 'SETUP_REQUIRED' | 'OPERATIONAL' | 'ERROR' | 'LOADING'

interface SystemInfo {
  status: SystemStatus
  setup_status?: string
  version?: string
  uptime?: number
  message?: string
}

export default function Home() {
  const [systemInfo, setSystemInfo] = useState<SystemInfo>({ status: 'LOADING' })
  const [error, setError] = useState<string | null>(null)

  const checkSystemStatus = async () => {
    try {
      const response = await apiClient.get('/api/status')
      setSystemInfo(response.data)
      setError(null)
    } catch (err: any) {
      console.error('Failed to fetch system status:', err)
      setError(err.response?.data?.detail || 'Failed to connect to the backend')
      setSystemInfo({ status: 'ERROR' })
    }
  }

  useEffect(() => {
    checkSystemStatus()
    // Poll status every 30 seconds
    const interval = setInterval(checkSystemStatus, 30000)
    return () => clearInterval(interval)
  }, [])

  const handleSetupComplete = () => {
    // Refresh system status after setup completion
    checkSystemStatus()
  }

  if (systemInfo.status === 'LOADING') {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <LoadingSpinner size="large" />
          <h2 className="mt-4 text-xl font-medium text-gray-700">
            Connecting to Ratichat...
          </h2>
          <p className="mt-2 text-gray-500">
            Initializing the administrative interface
          </p>
        </div>
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
