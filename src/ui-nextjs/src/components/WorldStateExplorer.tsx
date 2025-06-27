'use client'

import { useState, useEffect } from 'react'
import { apiClient } from '@/lib/api'
import { WorldState } from '@/types'

export default function WorldStateExplorer() {
  const [worldState, setWorldState] = useState<WorldState | null>(null)
  const [loading, setLoading] = useState(true)
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set())

  useEffect(() => {
    fetchWorldState()
  }, [])

  const fetchWorldState = async () => {
    try {
      const response = await apiClient.get<WorldState>('/api/worldstate')
      setWorldState(response.data)
    } catch (error) {
      console.error('Failed to fetch world state:', error)
    } finally {
      setLoading(false)
    }
  }

  const toggleNode = (nodeId: string) => {
    const newExpanded = new Set(expandedNodes)
    if (newExpanded.has(nodeId)) {
      newExpanded.delete(nodeId)
    } else {
      newExpanded.add(nodeId)
    }
    setExpandedNodes(newExpanded)
  }

  if (loading) {
    return <div className="text-center py-8">Loading world state...</div>
  }

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="px-6 py-4 border-b border-gray-200">
        <h3 className="text-lg font-medium text-gray-900">World State Explorer</h3>
        <p className="text-sm text-gray-500 mt-1">
          Deep inspection of the AI agent's memory and context
        </p>
      </div>
      <div className="p-6">
        <pre className="text-sm bg-gray-50 p-4 rounded-md overflow-auto">
          {JSON.stringify(worldState, null, 2)}
        </pre>
      </div>
    </div>
  )
}
