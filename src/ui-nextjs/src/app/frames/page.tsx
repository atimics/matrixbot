'use client';

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { Plus, ExternalLink, Edit, Trash2, Copy, Eye, Settings } from 'lucide-react';

interface Frame {
  id: string;
  name: string;
  url: string;
  description: string;
  status: 'active' | 'inactive' | 'error';
  views: number;
  interactions: number;
  lastActivity: string;
  created: string;
}

const mockFrames: Frame[] = [
  {
    id: '1',
    name: 'Welcome Frame',
    url: 'https://frames.ratimics.com/welcome',
    description: 'Interactive welcome experience for new users',
    status: 'active',
    views: 1250,
    interactions: 340,
    lastActivity: '2 minutes ago',
    created: '2024-01-15'
  },
  {
    id: '2',
    name: 'Poll Frame',
    url: 'https://frames.ratimics.com/poll/latest',
    description: 'Community polling and voting interface',
    status: 'active',
    views: 890,
    interactions: 156,
    lastActivity: '15 minutes ago',
    created: '2024-01-20'
  },
  {
    id: '3',
    name: 'NFT Showcase',
    url: 'https://frames.ratimics.com/nft/gallery',
    description: 'Display and interact with NFT collections',
    status: 'inactive',
    views: 450,
    interactions: 78,
    lastActivity: '2 hours ago',
    created: '2024-01-10'
  }
];

export default function FramesPage() {
  const [frames, setFrames] = useState<Frame[]>(mockFrames);
  const [isLoading, setIsLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');

  const filteredFrames = frames.filter(frame =>
    frame.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    frame.description.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const getStatusColor = (status: Frame['status']) => {
    switch (status) {
      case 'active': return 'bg-green-100 text-green-800';
      case 'inactive': return 'bg-yellow-100 text-yellow-800';
      case 'error': return 'bg-red-100 text-red-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  const handleCreateFrame = () => {
    // TODO: Implement frame creation
    console.log('Create new frame');
  };

  const handleEditFrame = (frameId: string) => {
    // TODO: Implement frame editing
    console.log('Edit frame:', frameId);
  };

  const handleDeleteFrame = (frameId: string) => {
    // TODO: Implement frame deletion
    console.log('Delete frame:', frameId);
  };

  const handleCopyUrl = (url: string) => {
    navigator.clipboard.writeText(url);
    // TODO: Show toast notification
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="large" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Farcaster Frames</h1>
          <p className="text-gray-600 mt-2">
            Manage and monitor your interactive Farcaster Frames
          </p>
        </div>
        <Button onClick={handleCreateFrame} className="flex items-center gap-2">
          <Plus className="w-4 h-4" />
          Create Frame
        </Button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-600">Total Frames</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{frames.length}</div>
            <p className="text-sm text-gray-600">
              {frames.filter(f => f.status === 'active').length} active
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-600">Total Views</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {frames.reduce((sum, f) => sum + f.views, 0).toLocaleString()}
            </div>
            <p className="text-sm text-green-600">+12% from last week</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-600">Interactions</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {frames.reduce((sum, f) => sum + f.interactions, 0).toLocaleString()}
            </div>
            <p className="text-sm text-green-600">+8% from last week</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-600">Engagement Rate</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {((frames.reduce((sum, f) => sum + f.interactions, 0) / 
                 frames.reduce((sum, f) => sum + f.views, 0)) * 100).toFixed(1)}%
            </div>
            <p className="text-sm text-green-600">+2.1% from last week</p>
          </CardContent>
        </Card>
      </div>

      {/* Search and Filters */}
      <Card>
        <CardHeader>
          <div className="flex justify-between items-center">
            <CardTitle>Frames Management</CardTitle>
            <div className="flex gap-2">
              <Input
                placeholder="Search frames..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-64"
              />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {filteredFrames.map((frame) => (
              <div
                key={frame.id}
                className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 transition-colors"
              >
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <h3 className="text-lg font-semibold text-gray-900">{frame.name}</h3>
                      <Badge className={getStatusColor(frame.status)}>
                        {frame.status}
                      </Badge>
                    </div>
                    <p className="text-gray-600 mb-3">{frame.description}</p>
                    <div className="flex items-center gap-4 text-sm text-gray-500">
                      <span className="flex items-center gap-1">
                        <Eye className="w-4 h-4" />
                        {frame.views.toLocaleString()} views
                      </span>
                      <span>{frame.interactions.toLocaleString()} interactions</span>
                      <span>Last activity: {frame.lastActivity}</span>
                      <span>Created: {frame.created}</span>
                    </div>
                    <div className="flex items-center gap-2 mt-2">
                      <code className="text-xs bg-gray-100 px-2 py-1 rounded">
                        {frame.url}
                      </code>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleCopyUrl(frame.url)}
                        className="h-6 px-2"
                      >
                        <Copy className="w-3 h-3" />
                      </Button>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => window.open(frame.url, '_blank')}
                    >
                      <ExternalLink className="w-4 h-4" />
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleEditFrame(frame.id)}
                    >
                      <Edit className="w-4 h-4" />
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleEditFrame(frame.id)}
                    >
                      <Settings className="w-4 h-4" />
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleDeleteFrame(frame.id)}
                      className="text-red-600 hover:text-red-700"
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
