'use client'

import { useState, useEffect, useRef } from 'react'
import { io, Socket } from 'socket.io-client'

interface LogEntry {
  timestamp: string
  level: string
  message: string
  source?: string
}

export default function LogViewer() {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const [autoScroll, setAutoScroll] = useState(true)
  const logsContainerRef = useRef<HTMLDivElement>(null)
  const socketRef = useRef<Socket | null>(null)

  useEffect(() => {
    // Initialize WebSocket connection
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    const wsUrl = apiUrl.replace('http', 'ws')
    
    socketRef.current = io(wsUrl, {
      path: '/ws/logs'
    })

    socketRef.current.on('connect', () => {
      setIsConnected(true)
      console.log('Connected to log stream')
    })

    socketRef.current.on('disconnect', () => {
      setIsConnected(false)
      console.log('Disconnected from log stream')
    })

    socketRef.current.on('log', (logEntry: LogEntry) => {
      setLogs(prevLogs => {
        const newLogs = [...prevLogs, logEntry]
        // Keep only last 1000 log entries
        return newLogs.slice(-1000)
      })
    })

    return () => {
      if (socketRef.current) {
        socketRef.current.disconnect()
      }
    }
  }, [])

  useEffect(() => {
    if (autoScroll && logsContainerRef.current) {
      logsContainerRef.current.scrollTop = logsContainerRef.current.scrollHeight
    }
  }, [logs, autoScroll])

  const getLevelColor = (level: string) => {
    switch (level.toLowerCase()) {
      case 'error':
        return 'text-red-600 bg-red-50'
      case 'warning':
      case 'warn':
        return 'text-yellow-600 bg-yellow-50'
      case 'info':
        return 'text-blue-600 bg-blue-50'
      case 'debug':
        return 'text-gray-600 bg-gray-50'
      default:
        return 'text-gray-800 bg-white'
    }
  }

  const clearLogs = () => {
    setLogs([])
  }

  const downloadLogs = () => {
    const logText = logs.map(log => 
      `${log.timestamp} [${log.level}] ${log.source ? `[${log.source}] ` : ''}${log.message}`
    ).join('\n')
    
    const blob = new Blob([logText], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `ratichat-logs-${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.txt`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  return (
    <div className="bg-white rounded-lg shadow h-[calc(100vh-200px)] flex flex-col">
      {/* Header */}
      <div className="px-6 py-4 border-b border-gray-200 flex justify-between items-center">
        <div className="flex items-center space-x-3">
          <h3 className="text-lg font-medium text-gray-900">Live Log Stream</h3>
          <div className={`flex items-center space-x-2 px-3 py-1 rounded-full text-xs font-medium ${
            isConnected ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
          }`}>
            <div className={`w-2 h-2 rounded-full ${
              isConnected ? 'bg-green-400' : 'bg-red-400'
            }`}></div>
            <span>{isConnected ? 'Connected' : 'Disconnected'}</span>
          </div>
        </div>
        
        <div className="flex items-center space-x-3">
          <label className="flex items-center space-x-2 text-sm text-gray-600">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <span>Auto-scroll</span>
          </label>
          
          <button
            onClick={downloadLogs}
            className="px-3 py-1 text-sm text-blue-600 hover:text-blue-800 border border-blue-300 rounded-md hover:bg-blue-50"
          >
            Download
          </button>
          
          <button
            onClick={clearLogs}
            className="px-3 py-1 text-sm text-red-600 hover:text-red-800 border border-red-300 rounded-md hover:bg-red-50"
          >
            Clear
          </button>
        </div>
      </div>

      {/* Log Content */}
      <div 
        ref={logsContainerRef}
        className="flex-1 overflow-y-auto p-4 font-mono text-sm bg-gray-900 text-gray-100"
      >
        {logs.length === 0 ? (
          <div className="flex items-center justify-center h-full text-gray-400">
            <div className="text-center">
              <svg className="w-12 h-12 mx-auto mb-4 opacity-50" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <p>No logs available</p>
              <p className="text-xs mt-1">Logs will appear here when the system is active</p>
            </div>
          </div>
        ) : (
          <div className="space-y-1">
            {logs.map((log, index) => (
              <div key={index} className="flex space-x-3 hover:bg-gray-800 px-2 py-1 rounded">
                <span className="text-gray-400 text-xs min-w-[100px]">
                  {new Date(log.timestamp).toLocaleTimeString()}
                </span>
                <span className={`text-xs min-w-[60px] px-2 py-0.5 rounded font-medium ${getLevelColor(log.level)}`}>
                  {log.level.toUpperCase()}
                </span>
                {log.source && (
                  <span className="text-blue-400 text-xs min-w-[80px]">
                    [{log.source}]
                  </span>
                )}
                <span className="flex-1 text-gray-100 break-words">
                  {log.message}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-6 py-2 border-t border-gray-200 bg-gray-50 text-xs text-gray-500">
        {logs.length} log entries • 
        {isConnected ? ' Receiving live updates' : ' Waiting for connection...'}
      </div>
    </div>
  )
}
