'use client';

import React, { useState } from 'react';
import { DashboardLayout } from '@/components/layout/dashboard-layout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

export default function MatrixIntegrationPage() {
  const [isLoading, setIsLoading] = useState(false);

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-foreground">Matrix Integration</h1>
            <p className="text-muted-foreground">
              Configure Matrix homeserver connection and manage room participation
            </p>
          </div>
          <div className="flex items-center space-x-2">
            <Badge variant="success">Connected</Badge>
            <Button variant="outline">
              <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Refresh Status
            </Button>
          </div>
        </div>

        {/* Connection Configuration */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Homeserver Connection</CardTitle>
              <CardDescription>
                Configure Matrix homeserver URL and authentication
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-3">
                <div className="flex items-center justify-between p-3 bg-green-50 rounded-lg border border-green-200">
                  <div className="flex items-center space-x-3">
                    <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                    <div>
                      <div className="font-medium text-green-900">Connected</div>
                      <div className="text-sm text-green-700">Syncing with homeserver</div>
                    </div>
                  </div>
                  <Badge variant="success">Active</Badge>
                </div>

                <div>
                  <Input
                    label="Homeserver URL"
                    type="url"
                    value="https://chat.ratimics.com"
                    helper="The Matrix homeserver to connect to"
                  />
                </div>

                <div>
                  <Input
                    label="User ID"
                    value="@ratichat:chat.ratimics.com"
                    helper="Your Matrix user ID"
                    disabled
                  />
                </div>

                <div>
                  <Input
                    label="Device ID"
                    value="RATICHAT_DEVICE_01"
                    helper="Device identifier for this bot instance"
                    disabled
                  />
                </div>
              </div>

              <div className="flex space-x-2 pt-4 border-t">
                <Button variant="outline" className="flex-1">
                  Reconnect
                </Button>
                <Button variant="outline">
                  Test Connection
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Sync Status</CardTitle>
              <CardDescription>
                Matrix synchronization and room management status
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm font-medium text-muted-foreground">Sync State</label>
                    <div className="mt-1">
                      <Badge variant="success">Syncing</Badge>
                    </div>
                  </div>
                  <div>
                    <label className="text-sm font-medium text-muted-foreground">Last Sync</label>
                    <div className="mt-1 text-sm">2 minutes ago</div>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm font-medium text-muted-foreground">Joined Rooms</label>
                    <div className="mt-1 text-2xl font-bold">8</div>
                  </div>
                  <div>
                    <label className="text-sm font-medium text-muted-foreground">Pending Invites</label>
                    <div className="mt-1 text-2xl font-bold text-orange-600">2</div>
                  </div>
                </div>

                <div className="flex items-center justify-between p-3 bg-blue-50 rounded-lg border border-blue-200">
                  <div>
                    <div className="font-medium text-blue-900">E2E Encryption</div>
                    <div className="text-sm text-blue-700">End-to-end encryption support</div>
                  </div>
                  <Badge variant="outline">Enabled</Badge>
                </div>
              </div>

              <div className="flex space-x-2 pt-4 border-t">
                <Button className="flex-1">
                  Force Sync
                </Button>
                <Button variant="outline">
                  View Logs
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Room Management */}
        <Card>
          <CardHeader>
            <CardTitle>Room Management</CardTitle>
            <CardDescription>
              Manage Matrix rooms, invitations, and permissions
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-medium">Active Rooms</h3>
              <Button size="sm">
                <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                </svg>
                Join Room
              </Button>
            </div>

            <div className="space-y-3">
              {[
                { id: '!abc123:chat.ratimics.com', name: 'General Chat', members: 24, type: 'public', active: true },
                { id: '!def456:chat.ratimics.com', name: 'AI Development', members: 8, type: 'private', active: true },
                { id: '!ghi789:chat.ratimics.com', name: 'Bot Testing', members: 3, type: 'private', active: true },
                { id: '!jkl012:chat.ratimics.com', name: 'Community Support', members: 45, type: 'public', active: false },
              ].map((room, i) => (
                <div key={i} className="flex items-center justify-between p-4 bg-gray-50 rounded-lg border">
                  <div className="flex items-center space-x-4">
                    <div className={`w-3 h-3 rounded-full ${room.active ? 'bg-green-500' : 'bg-gray-400'}`}></div>
                    <div className="flex-1">
                      <div className="font-medium">{room.name}</div>
                      <div className="text-sm text-muted-foreground font-mono truncate">{room.id}</div>
                    </div>
                    <div className="text-sm text-muted-foreground">
                      {room.members} members
                    </div>
                    <Badge variant={room.type === 'public' ? 'outline' : 'secondary'}>
                      {room.type}
                    </Badge>
                  </div>
                  <div className="flex space-x-2">
                    <Button size="sm" variant="outline">
                      Configure
                    </Button>
                    {!room.active && (
                      <Button size="sm" variant="outline">
                        Rejoin
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>

            {/* Pending Invitations */}
            <div className="pt-4 border-t">
              <h4 className="font-medium mb-3">Pending Invitations</h4>
              <div className="space-y-2">
                {[
                  { id: '!xyz789:matrix.org', name: 'Open Source AI', inviter: '@alice:matrix.org' },
                  { id: '!uvw456:another.com', name: 'Bot Developers', inviter: '@bob:another.com' },
                ].map((invite, i) => (
                  <div key={i} className="flex items-center justify-between p-3 bg-yellow-50 rounded-lg border border-yellow-200">
                    <div>
                      <div className="font-medium">{invite.name}</div>
                      <div className="text-sm text-muted-foreground">Invited by {invite.inviter}</div>
                    </div>
                    <div className="flex space-x-2">
                      <Button size="sm" variant="outline">
                        Accept
                      </Button>
                      <Button size="sm" variant="outline">
                        Decline
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Activity & Analytics */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Recent Activity</CardTitle>
              <CardDescription>
                Latest Matrix events and interactions
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {[
                  { action: 'Message sent', room: 'General Chat', time: '1 min ago', status: 'success' },
                  { action: 'Joined room', room: 'AI Development', time: '15 min ago', status: 'info' },
                  { action: 'Sync completed', room: 'All rooms', time: '30 min ago', status: 'success' },
                  { action: 'Invitation received', room: 'Bot Developers', time: '1 hour ago', status: 'warning' },
                ].map((item, i) => (
                  <div key={i} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                    <div className="flex items-center space-x-3">
                      <div className={`w-2 h-2 rounded-full ${
                        item.status === 'success' ? 'bg-green-500' :
                        item.status === 'info' ? 'bg-blue-500' :
                        item.status === 'warning' ? 'bg-yellow-500' : 'bg-gray-400'
                      }`}></div>
                      <div>
                        <div className="font-medium">{item.action}</div>
                        <div className="text-sm text-muted-foreground">{item.room}</div>
                      </div>
                    </div>
                    <div className="text-sm text-muted-foreground">{item.time}</div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Performance Metrics</CardTitle>
              <CardDescription>
                Matrix integration performance and statistics
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="text-center p-4 bg-blue-50 rounded-lg">
                    <div className="text-2xl font-bold text-blue-600">1,284</div>
                    <div className="text-sm text-blue-800">Messages Sent</div>
                  </div>
                  <div className="text-center p-4 bg-green-50 rounded-lg">
                    <div className="text-2xl font-bold text-green-600">8</div>
                    <div className="text-sm text-green-800">Active Rooms</div>
                  </div>
                  <div className="text-center p-4 bg-purple-50 rounded-lg">
                    <div className="text-2xl font-bold text-purple-600">24h</div>
                    <div className="text-sm text-purple-800">Uptime</div>
                  </div>
                  <div className="text-center p-4 bg-orange-50 rounded-lg">
                    <div className="text-2xl font-bold text-orange-600">99.8%</div>
                    <div className="text-sm text-orange-800">Sync Success</div>
                  </div>
                </div>

                <div className="pt-4 border-t">
                  <Button variant="outline" className="w-full">
                    View Detailed Analytics
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </DashboardLayout>
  );
}
