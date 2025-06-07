'use client'

import { useState, useEffect } from 'react'
import { apiClient } from '@/lib/api'
import LoadingSpinner from '@/components/ui/LoadingSpinner'

interface Tool {
  name: string
  enabled: boolean
  description: string
  category: string
}

export default function ToolManager() {
  const [tools, setTools] = useState<Tool[]>([])
  const [loading, setLoading] = useState(true)
  const [updating, setUpdating] = useState<string | null>(null)

  useEffect(() => {
    fetchTools()
  }, [])

  const fetchTools = async () => {
    try {
      const response = await apiClient.get('/api/tools')
      setTools(response.data.tools || [])
    } catch (error) {
      console.error('Failed to fetch tools:', error)
    } finally {
      setLoading(false)
    }
  }

  const toggleTool = async (toolName: string) => {
    setUpdating(toolName)
    try {
      const tool = tools.find(t => t.name === toolName)
      if (!tool) return

      await apiClient.post(`/api/tools/${toolName}/toggle`, {
        enabled: !tool.enabled
      })

      setTools(prevTools =>
        prevTools.map(t =>
          t.name === toolName ? { ...t, enabled: !t.enabled } : t
        )
      )
    } catch (error) {
      console.error(`Failed to toggle tool ${toolName}:`, error)
    } finally {
      setUpdating(null)
    }
  }

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <LoadingSpinner size="large" />
      </div>
    )
  }

  const groupedTools = tools.reduce((acc, tool) => {
    if (!acc[tool.category]) {
      acc[tool.category] = []
    }
    acc[tool.category].push(tool)
    return acc
  }, {} as Record<string, Tool[]>)

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-lg shadow">
        <div className="px-6 py-4 border-b border-gray-200">
          <h3 className="text-lg font-medium text-gray-900">Tool Registry</h3>
          <p className="text-sm text-gray-500 mt-1">
            Enable or disable AI agent capabilities on the fly
          </p>
        </div>

        <div className="p-6">
          {Object.entries(groupedTools).map(([category, categoryTools]) => (
            <div key={category} className="mb-8 last:mb-0">
              <h4 className="text-md font-medium text-gray-800 mb-4 capitalize">
                {category.replace('_', ' ')} Tools
              </h4>
              
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {categoryTools.map((tool) => (
                  <div
                    key={tool.name}
                    className="border border-gray-200 rounded-lg p-4 hover:border-gray-300 transition-colors"
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1 min-w-0">
                        <h5 className="text-sm font-medium text-gray-900 truncate">
                          {tool.name}
                        </h5>
                        <p className="text-xs text-gray-500 mt-1">
                          {tool.description}
                        </p>
                      </div>
                      
                      <div className="ml-3 flex-shrink-0">
                        {updating === tool.name ? (
                          <LoadingSpinner size="small" />
                        ) : (
                          <button
                            onClick={() => toggleTool(tool.name)}
                            className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 ${
                              tool.enabled ? 'bg-blue-600' : 'bg-gray-200'
                            }`}
                          >
                            <span
                              className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                                tool.enabled ? 'translate-x-5' : 'translate-x-0'
                              }`}
                            />
                          </button>
                        )}
                      </div>
                    </div>
                    
                    <div className="mt-3">
                      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                        tool.enabled
                          ? 'bg-green-100 text-green-800'
                          : 'bg-gray-100 text-gray-800'
                      }`}>
                        {tool.enabled ? 'Enabled' : 'Disabled'}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
