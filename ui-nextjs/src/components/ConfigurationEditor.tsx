'use client'

import { useState, useEffect } from 'react'
import { apiClient } from '@/lib/api'

export default function ConfigurationEditor() {
  const [config, setConfig] = useState<any>({})
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchConfig()
  }, [])

  const fetchConfig = async () => {
    try {
      const response = await apiClient.get<any>('/api/config')
      setConfig(response.data)
    } catch (error) {
      console.error('Failed to fetch config:', error)
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return <div className="text-center py-8">Loading configuration...</div>
  }

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="px-6 py-4 border-b border-gray-200">
        <h3 className="text-lg font-medium text-gray-900">Configuration Editor</h3>
        <p className="text-sm text-gray-500 mt-1">
          Manage runtime configuration parameters
        </p>
      </div>
      <div className="p-6">
        <p className="text-gray-500">Configuration editor coming soon...</p>
      </div>
    </div>
  )
}
