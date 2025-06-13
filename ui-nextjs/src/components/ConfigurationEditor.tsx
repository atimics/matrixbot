'use client'

import { useState, useEffect } from 'react'
import { apiClient } from '@/lib/api'
import { Configuration } from '@/types'

export default function ConfigurationEditor() {
  const [config, setConfig] = useState<Configuration | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    fetchConfig()
  }, [])

  const fetchConfig = async () => {
    try {
      const response = await apiClient.get<Configuration>('/api/config')
      setConfig(response.data)
    } catch (error) {
      console.error('Failed to fetch config:', error)
    } finally {
      setLoading(false)
    }
  }

  const saveConfig = async () => {
    if (!config) return
    
    setSaving(true)
    try {
      await apiClient.put('/api/config', config)
      alert('Configuration saved successfully!')
    } catch (error) {
      console.error('Failed to save config:', error)
      alert('Failed to save configuration')
    } finally {
      setSaving(false)
    }
  }

  const updateFarcasterConfig = (key: string, value: number) => {
    if (!config) return
    
    setConfig({
      ...config,
      farcaster: {
        ...config.farcaster,
        [key]: value
      }
    })
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
      <div className="p-6 space-y-6">
        
        {/* Farcaster Settings */}
        <div className="bg-gray-50 p-4 rounded-lg">
          <h4 className="text-md font-medium text-gray-900 mb-4">Farcaster Settings</h4>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Minimum Time Between Posts (minutes)
              </label>
              <input
                type="range"
                min="1"
                max="60"
                value={config?.farcaster?.min_post_interval_minutes || 5}
                onChange={(e) => updateFarcasterConfig('min_post_interval_minutes', parseInt(e.target.value))}
                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
              />
              <div className="flex justify-between text-xs text-gray-500 mt-1">
                <span>1min</span>
                <span className="font-medium">
                  {config?.farcaster?.min_post_interval_minutes || 5} minutes
                </span>
                <span>1hr</span>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Duplicate Check Period (hours)
              </label>
              <input
                type="range"
                min="1"
                max="24"
                value={config?.farcaster?.duplicate_check_hours || 1}
                onChange={(e) => updateFarcasterConfig('duplicate_check_hours', parseInt(e.target.value))}
                className="w-full h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
              />
              <div className="flex justify-between text-xs text-gray-500 mt-1">
                <span>1hr</span>
                <span className="font-medium">
                  {config?.farcaster?.duplicate_check_hours || 1} hours
                </span>
                <span>24hr</span>
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Recent Posts Limit
              </label>
              <input
                type="number"
                min="5"
                max="50"
                value={config?.farcaster?.recent_posts_limit || 10}
                onChange={(e) => updateFarcasterConfig('recent_posts_limit', parseInt(e.target.value))}
                className="block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm"
              />
              <p className="text-xs text-gray-500 mt-1">
                Number of recent posts to fetch for rate limiting checks
              </p>
            </div>
          </div>
        </div>

        {/* Save Button */}
        <div className="pt-4 border-t border-gray-200">
          <button
            onClick={saveConfig}
            disabled={saving}
            className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 disabled:opacity-50"
          >
            {saving ? 'Saving...' : 'Save Configuration'}
          </button>
        </div>
      </div>
    </div>
  )
}
