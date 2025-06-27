'use client';

import React from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import useSWR from 'swr';
import { apiClient } from '@/lib/api-client';
import { formatDuration } from '@/lib/utils';

export function Header() {
  // Fetch system status for header info
  const { data: systemStatus, error } = useSWR(
    '/api/system/status',
    () => apiClient.getSystemStatus(),
    { refreshInterval: 30000 } // Refresh every 30 seconds
  );

  const getSystemStatusBadge = () => {
    if (error) {
      return <Badge variant="destructive">Offline</Badge>;
    }
    if (!systemStatus) {
      return <Badge variant="outline">Loading...</Badge>;
    }
    if (systemStatus.system_running) {
      return <Badge variant="success">Online</Badge>;
    }
    return <Badge variant="warning">Degraded</Badge>;
  };

  const formatUptime = (seconds: number) => {
    if (!seconds) return 'Unknown';
    return formatDuration(seconds);
  };

  return (
    <header className="h-16 border-b border-border bg-card px-6 flex items-center justify-between">
      {/* Left side - Status info */}
      <div className="flex items-center space-x-6">
        <div className="flex items-center space-x-2">
          <span className="text-sm font-medium">Status:</span>
          {getSystemStatusBadge()}
        </div>
        
        {systemStatus && (
          <div className="flex items-center space-x-4 text-sm text-muted-foreground">
            <div>
              Uptime: {formatUptime(systemStatus.uptime_seconds)}
            </div>
            <div>
              Mode: {systemStatus.config?.processing_mode || 'Unknown'}
            </div>
            <div>
              Model: {systemStatus.config?.ai_model || 'Unknown'}
            </div>
          </div>
        )}
      </div>

      {/* Right side - Actions */}
      <div className="flex items-center space-x-3">
        {/* Quick stats */}
        {systemStatus && (
          <div className="flex items-center space-x-4 text-sm text-muted-foreground">
            <div className="flex items-center space-x-1">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
              <span>{systemStatus.world_state?.total_messages || 0}</span>
            </div>
            <div className="flex items-center space-x-1">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
              </svg>
              <span>{systemStatus.world_state?.channels_count || 0}</span>
            </div>
          </div>
        )}

        {/* Refresh button */}
        <Button
          variant="outline"
          size="sm"
          onClick={() => window.location.reload()}
        >
          <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
          Refresh
        </Button>

        {/* Settings button */}
        <Button variant="ghost" size="sm">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
        </Button>
      </div>
    </header>
  );
}
