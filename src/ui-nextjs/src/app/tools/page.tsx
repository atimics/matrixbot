'use client';

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { 
  Plus, 
  Settings, 
  Power, 
  AlertTriangle, 
  Zap, 
  Brain, 
  MessageSquare, 
  Image, 
  Code, 
  Search,
  MoreVertical
} from 'lucide-react';

interface Tool {
  id: string;
  name: string;
  category: 'ai' | 'integration' | 'utility' | 'social';
  description: string;
  status: 'enabled' | 'disabled' | 'error' | 'configuring';
  version: string;
  lastUsed: string;
  usageCount: number;
  configuration: Record<string, any>;
  dependencies: string[];
}

const mockTools: Tool[] = [
  {
    id: '1',
    name: 'GPT-4 Assistant',
    category: 'ai',
    description: 'Primary AI conversation engine with advanced reasoning capabilities',
    status: 'enabled',
    version: '4.0.1',
    lastUsed: '2 minutes ago',
    usageCount: 15420,
    configuration: {
      model: 'gpt-4-turbo-preview',
      temperature: 0.7,
      maxTokens: 4096
    },
    dependencies: ['OpenAI API']
  },
  {
    id: '2',
    name: 'Image Generator',
    category: 'ai',
    description: 'DALL-E powered image generation for creative content',
    status: 'enabled',
    version: '3.0.2',
    lastUsed: '15 minutes ago',
    usageCount: 850,
    configuration: {
      model: 'dall-e-3',
      quality: 'hd',
      size: '1024x1024'
    },
    dependencies: ['OpenAI API', 'Image Storage']
  },
  {
    id: '3',
    name: 'Code Analyzer',
    category: 'utility',
    description: 'Static code analysis and debugging assistance',
    status: 'enabled',
    version: '2.1.0',
    lastUsed: '1 hour ago',
    usageCount: 340,
    configuration: {
      supportedLanguages: ['python', 'javascript', 'typescript', 'solidity'],
      securityScan: true
    },
    dependencies: ['GitHub API']
  },
  {
    id: '4',
    name: 'Sentiment Analysis',
    category: 'ai',
    description: 'Real-time sentiment analysis for message moderation',
    status: 'disabled',
    version: '1.3.1',
    lastUsed: '3 days ago',
    usageCount: 2150,
    configuration: {
      threshold: 0.8,
      languages: ['en', 'es', 'fr']
    },
    dependencies: ['Hugging Face API']
  },
  {
    id: '5',
    name: 'Web Search',
    category: 'utility',
    description: 'Real-time web search and information retrieval',
    status: 'error',
    version: '1.2.3',
    lastUsed: '2 hours ago',
    usageCount: 680,
    configuration: {
      searchEngine: 'google',
      resultsLimit: 10
    },
    dependencies: ['Google Search API']
  },
  {
    id: '6',
    name: 'Social Monitor',
    category: 'social',
    description: 'Monitor social media platforms for mentions and trends',
    status: 'configuring',
    version: '0.9.0',
    lastUsed: 'Never',
    usageCount: 0,
    configuration: {
      platforms: ['twitter', 'farcaster'],
      keywords: []
    },
    dependencies: ['Twitter API', 'Farcaster Hub']
  }
];

export default function ToolsPage() {
  const [tools, setTools] = useState<Tool[]>(mockTools);
  const [isLoading, setIsLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');

  const categories = [
    { id: 'all', name: 'All Tools', icon: MoreVertical },
    { id: 'ai', name: 'AI Tools', icon: Brain },
    { id: 'integration', name: 'Integrations', icon: Zap },
    { id: 'utility', name: 'Utilities', icon: Settings },
    { id: 'social', name: 'Social', icon: MessageSquare }
  ];

  const filteredTools = tools.filter(tool => {
    const matchesSearch = tool.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         tool.description.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesCategory = selectedCategory === 'all' || tool.category === selectedCategory;
    return matchesSearch && matchesCategory;
  });

  const getStatusColor = (status: Tool['status']) => {
    switch (status) {
      case 'enabled': return 'bg-green-100 text-green-800';
      case 'disabled': return 'bg-gray-100 text-gray-800';
      case 'error': return 'bg-red-100 text-red-800';
      case 'configuring': return 'bg-yellow-100 text-yellow-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  const getCategoryIcon = (category: Tool['category']) => {
    switch (category) {
      case 'ai': return Brain;
      case 'integration': return Zap;
      case 'utility': return Code;
      case 'social': return MessageSquare;
      default: return Settings;
    }
  };

  const handleToggleTool = (toolId: string) => {
    setTools(prev => prev.map(tool => 
      tool.id === toolId 
        ? { ...tool, status: tool.status === 'enabled' ? 'disabled' : 'enabled' }
        : tool
    ));
  };

  const handleConfigureTool = (toolId: string) => {
    console.log('Configure tool:', toolId);
  };

  const handleAddTool = () => {
    console.log('Add new tool');
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <LoadingSpinner size="large" />
      </div>
    );
  }

  const enabledTools = tools.filter(t => t.status === 'enabled').length;
  const errorTools = tools.filter(t => t.status === 'error').length;
  const totalUsage = tools.reduce((sum, t) => sum + t.usageCount, 0);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">AI Tools & Capabilities</h1>
          <p className="text-gray-600 mt-2">
            Manage and configure your AI tools and integrations
          </p>
        </div>
        <Button onClick={handleAddTool} className="flex items-center gap-2">
          <Plus className="w-4 h-4" />
          Add Tool
        </Button>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-600">Total Tools</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{tools.length}</div>
            <p className="text-sm text-gray-600">{enabledTools} enabled</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-600">Active Tools</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-green-600">{enabledTools}</div>
            <p className="text-sm text-gray-600">Running smoothly</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-600">Total Usage</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{totalUsage.toLocaleString()}</div>
            <p className="text-sm text-green-600">+15% this week</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-gray-600">Issues</CardTitle>
          </CardHeader>
          <CardContent>
            <div className={`text-2xl font-bold ${errorTools > 0 ? 'text-red-600' : 'text-green-600'}`}>
              {errorTools}
            </div>
            <p className="text-sm text-gray-600">
              {errorTools > 0 ? 'Need attention' : 'All healthy'}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Category Filter */}
      <Card>
        <CardHeader>
          <CardTitle>Tool Categories</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {categories.map((category) => {
              const Icon = category.icon;
              const isSelected = selectedCategory === category.id;
              return (
                <Button
                  key={category.id}
                  variant={isSelected ? "default" : "outline"}
                  size="sm"
                  onClick={() => setSelectedCategory(category.id)}
                  className="flex items-center gap-2"
                >
                  <Icon className="w-4 h-4" />
                  {category.name}
                </Button>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Search and Tools List */}
      <Card>
        <CardHeader>
          <div className="flex justify-between items-center">
            <CardTitle>Tools Management</CardTitle>
            <Input
              placeholder="Search tools..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-64"
            />
          </div>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {filteredTools.map((tool) => {
              const CategoryIcon = getCategoryIcon(tool.category);
              return (
                <div
                  key={tool.id}
                  className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 transition-colors"
                >
                  <div className="flex justify-between items-start">
                    <div className="flex items-start gap-3 flex-1">
                      <div className="p-2 bg-gray-100 rounded-lg">
                        <CategoryIcon className="w-5 h-5 text-gray-600" />
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center gap-3 mb-2">
                          <h3 className="text-lg font-semibold text-gray-900">{tool.name}</h3>
                          <Badge className={getStatusColor(tool.status)}>
                            {tool.status}
                          </Badge>
                          <span className="text-sm text-gray-500">v{tool.version}</span>
                        </div>
                        <p className="text-gray-600 mb-3">{tool.description}</p>
                        <div className="flex items-center gap-6 text-sm text-gray-500">
                          <span>Used {tool.usageCount.toLocaleString()} times</span>
                          <span>Last used: {tool.lastUsed}</span>
                          <span>Dependencies: {tool.dependencies.join(', ')}</span>
                        </div>
                        {tool.status === 'error' && (
                          <div className="flex items-center gap-2 mt-2 text-red-600 text-sm">
                            <AlertTriangle className="w-4 h-4" />
                            Configuration error - check dependencies
                          </div>
                        )}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleToggleTool(tool.id)}
                        className={tool.status === 'enabled' ? 'text-red-600' : 'text-green-600'}
                      >
                        <Power className="w-4 h-4" />
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleConfigureTool(tool.id)}
                      >
                        <Settings className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
