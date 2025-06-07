'use client'

import { useState, useEffect } from 'react'
import { apiClient } from '@/lib/api'
import LogViewer from '@/components/LogViewer'
import StatusPanel from '@/components/StatusPanel'
import ToolManager from '@/components/ToolManager'
import WorldStateExplorer from '@/components/WorldStateExplorer'
import ConfigurationEditor from '@/components/ConfigurationEditor'
import { SystemInfo, DashboardProps } from '@/types'

export default function Dashboard({ systemInfo, onStatusChange }: DashboardProps) {
  const [activeTab, setActiveTab] = useState('overview')

  const tabs = [
    { id: 'overview', name: 'Overview', icon: '📊' },
    { id: 'logs', name: 'Live Logs', icon: '📝' },
    { id: 'tools', name: 'Tool Manager', icon: '⚙️' },
    { id: 'worldstate', name: 'World State', icon: '🌍' },
    { id: 'config', name: 'Configuration', icon: '📋' }
  ]

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Header */}
      <header className="bg-white shadow-sm border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center space-x-4">
              <div className="w-8 h-8 bg-gradient-to-r from-blue-600 to-indigo-600 rounded-lg flex items-center justify-center">
                <span className="text-white font-bold text-sm">R</span>
              </div>
              <div>
                <h1 className="text-xl font-semibold text-gray-900">Ratichat Admin Panel</h1>
                <p className="text-sm text-gray-500">AI Agent Management Dashboard</p>
              </div>
            </div>
            
            <div className="flex items-center space-x-3">
              <div className={`px-3 py-1 rounded-full text-xs font-medium ${
                systemInfo.status === 'OPERATIONAL' 
                  ? 'bg-green-100 text-green-800' 
                  : 'bg-yellow-100 text-yellow-800'
              }`}>
                {systemInfo.status}
              </div>
              
              <button className="p-2 text-gray-400 hover:text-gray-600 rounded-md hover:bg-gray-100">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Navigation Tabs */}
      <div className="bg-white border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <nav className="flex space-x-8">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`py-4 px-1 border-b-2 font-medium text-sm ${
                  activeTab === tab.id
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                <span className="mr-2">{tab.icon}</span>
                {tab.name}
              </button>
            ))}
          </nav>
        </div>
      </div>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {activeTab === 'overview' && (
          <StatusPanel systemInfo={systemInfo} onStatusChange={onStatusChange} />
        )}
        
        {activeTab === 'logs' && (
          <LogViewer />
        )}
        
        {activeTab === 'tools' && (
          <ToolManager />
        )}
        
        {activeTab === 'worldstate' && (
          <WorldStateExplorer />
        )}
        
        {activeTab === 'config' && (
          <ConfigurationEditor />
        )}
      </main>
    </div>
  )
}
