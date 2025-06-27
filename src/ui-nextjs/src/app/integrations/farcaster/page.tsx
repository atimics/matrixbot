'use client';

import React, { useState } from 'react';
import { DashboardLayout } from '@/components/layout/dashboard-layout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

export default function FarcasterIntegrationPage() {
  const [isLoading, setIsLoading] = useState(false);

  return (
    <DashboardLayout>
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-foreground">Farcaster Integration</h1>
            <p className="text-muted-foreground">
              Configure Farcaster protocol integration, signer delegation, and Frame hosting
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

        {/* Signer Configuration */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Signer Configuration</CardTitle>
              <CardDescription>
                Manage Farcaster signer delegation and authentication
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-3">
                <div className="flex items-center justify-between p-3 bg-green-50 rounded-lg border border-green-200">
                  <div className="flex items-center space-x-3">
                    <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                    <div>
                      <div className="font-medium text-green-900">Signer Active</div>
                      <div className="text-sm text-green-700">Connected and approved for posting</div>
                    </div>
                  </div>
                  <Badge variant="success">Approved</Badge>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm font-medium text-muted-foreground">Bot FID</label>
                    <div className="mt-1 text-sm font-mono">12345</div>
                  </div>
                  <div>
                    <label className="text-sm font-medium text-muted-foreground">Signer UUID</label>
                    <div className="mt-1 text-sm font-mono truncate">abc123...def456</div>
                  </div>
                </div>

                <div>
                  <label className="text-sm font-medium text-muted-foreground">Custody Address</label>
                  <div className="mt-1 text-sm font-mono truncate">0x1234...5678</div>
                </div>
              </div>

              <div className="flex space-x-2 pt-4 border-t">
                <Button variant="outline" className="flex-1">
                  Generate New Signer
                </Button>
                <Button variant="outline">
                  View Details
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>API Configuration</CardTitle>
              <CardDescription>
                Configure Neynar API integration and fallback settings
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-4">
                <div>
                  <Input
                    label="Neynar API Key"
                    type="password"
                    placeholder="Enter your Neynar API key"
                    helper="Used for Farcaster data fetching and fallback operations"
                  />
                </div>

                <div>
                  <Input
                    label="Webhook URL"
                    type="url"
                    placeholder="https://your-domain.com/webhooks/farcaster"
                    helper="URL for receiving Farcaster webhooks"
                  />
                </div>

                <div className="flex items-center justify-between p-3 bg-blue-50 rounded-lg border border-blue-200">
                  <div>
                    <div className="font-medium text-blue-900">Internal API Service</div>
                    <div className="text-sm text-blue-700">Using in-house Snapchain integration</div>
                  </div>
                  <Badge variant="outline">Active</Badge>
                </div>
              </div>

              <div className="flex space-x-2 pt-4 border-t">
                <Button className="flex-1">
                  Save Configuration
                </Button>
                <Button variant="outline">
                  Test API
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Frames Configuration */}
        <Card>
          <CardHeader>
            <CardTitle>Farcaster Frames</CardTitle>
            <CardDescription>
              Configure Frame hosting, NFT minting, and interactive content
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="space-y-4">
                <h3 className="text-lg font-medium">Frame Settings</h3>
                
                <div>
                  <Input
                    label="Base URL"
                    type="url"
                    placeholder="https://your-domain.com"
                    helper="Base URL for Frame hosting"
                  />
                </div>

                <div>
                  <Input
                    label="Default Frame Image"
                    type="url"
                    placeholder="https://your-domain.com/default-frame.png"
                    helper="Default image for Frames (1200x630px recommended)"
                  />
                </div>

                <div className="flex items-center justify-between p-3 bg-gray-50 rounded-lg border">
                  <div>
                    <div className="font-medium">Frame Hosting</div>
                    <div className="text-sm text-muted-foreground">Enable interactive Frame content</div>
                  </div>
                  <Badge variant="success">Enabled</Badge>
                </div>
              </div>

              <div className="space-y-4">
                <h3 className="text-lg font-medium">NFT Minting</h3>

                <div>
                  <Input
                    label="NFT Contract Address"
                    placeholder="0x1234...5678"
                    helper="Contract address for NFT minting frames"
                  />
                </div>

                <div className="space-y-3">
                  <div className="flex items-center justify-between p-3 bg-purple-50 rounded-lg border border-purple-200">
                    <div>
                      <div className="font-medium text-purple-900">Mint Frames</div>
                      <div className="text-sm text-purple-700">Allow users to mint NFTs via Frames</div>
                    </div>
                    <Badge variant="outline">Enabled</Badge>
                  </div>

                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <span className="text-muted-foreground">Total Mints:</span>
                      <span className="ml-2 font-medium">142</span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Active Frames:</span>
                      <span className="ml-2 font-medium">8</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div className="flex space-x-2 pt-6 border-t">
              <Button>
                Save Frame Configuration
              </Button>
              <Button variant="outline">
                Preview Frame
              </Button>
              <Button variant="outline">
                Create New Frame
              </Button>
            </div>
          </CardContent>
        </Card>

        {/* Activity & Analytics */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle>Recent Activity</CardTitle>
              <CardDescription>
                Latest Farcaster interactions and system events
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-3">
                {[
                  { action: 'Posted cast', user: '@alice', time: '2 min ago', status: 'success' },
                  { action: 'Frame interaction', user: '@bob', time: '5 min ago', status: 'success' },
                  { action: 'NFT minted', user: '@charlie', time: '12 min ago', status: 'success' },
                  { action: 'Signer approved', user: 'System', time: '1 hour ago', status: 'info' },
                ].map((item, i) => (
                  <div key={i} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                    <div className="flex items-center space-x-3">
                      <div className={`w-2 h-2 rounded-full ${
                        item.status === 'success' ? 'bg-green-500' :
                        item.status === 'info' ? 'bg-blue-500' : 'bg-gray-400'
                      }`}></div>
                      <div>
                        <div className="font-medium">{item.action}</div>
                        <div className="text-sm text-muted-foreground">{item.user}</div>
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
                Analytics and performance data for Farcaster integration
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="text-center p-4 bg-blue-50 rounded-lg">
                    <div className="text-2xl font-bold text-blue-600">284</div>
                    <div className="text-sm text-blue-800">Total Casts</div>
                  </div>
                  <div className="text-center p-4 bg-green-50 rounded-lg">
                    <div className="text-2xl font-bold text-green-600">142</div>
                    <div className="text-sm text-green-800">Frame Views</div>
                  </div>
                  <div className="text-center p-4 bg-purple-50 rounded-lg">
                    <div className="text-2xl font-bold text-purple-600">67</div>
                    <div className="text-sm text-purple-800">NFT Mints</div>
                  </div>
                  <div className="text-center p-4 bg-orange-50 rounded-lg">
                    <div className="text-2xl font-bold text-orange-600">98.5%</div>
                    <div className="text-sm text-orange-800">Uptime</div>
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
