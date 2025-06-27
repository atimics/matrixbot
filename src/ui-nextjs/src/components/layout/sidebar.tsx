import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { cn } from '@/lib/utils';
import { Badge } from '@/components/ui/badge';

interface NavItem {
  id: string;
  label: string;
  href: string;
  icon: React.ReactNode;
  badge?: string | number;
  children?: NavItem[];
}

interface SidebarProps {
  items: NavItem[];
  collapsed?: boolean;
  onToggle?: () => void;
}

export function Sidebar({ items, collapsed = false, onToggle }: SidebarProps) {
  const pathname = usePathname();
  const [expandedItems, setExpandedItems] = useState<Set<string>>(new Set());

  const toggleExpanded = (itemId: string) => {
    const newExpanded = new Set(expandedItems);
    if (newExpanded.has(itemId)) {
      newExpanded.delete(itemId);
    } else {
      newExpanded.add(itemId);
    }
    setExpandedItems(newExpanded);
  };

  const renderNavItem = (item: NavItem, depth = 0) => {
    const hasChildren = item.children && item.children.length > 0;
    const isExpanded = expandedItems.has(item.id);
    const isActive = pathname === item.href;

    return (
      <div key={item.id}>
        {hasChildren ? (
          <div
            className={cn(
              'flex items-center px-3 py-2 text-sm font-medium rounded-lg cursor-pointer transition-colors',
              depth > 0 && 'ml-6',
              'text-muted-foreground hover:text-foreground hover:bg-accent',
              collapsed && 'justify-center px-2'
            )}
            onClick={() => toggleExpanded(item.id)}
          >
            <div className="flex items-center min-w-0 flex-1">
              <div className="flex-shrink-0">{item.icon}</div>
              {!collapsed && (
                <>
                  <span className="ml-3 truncate">{item.label}</span>
                  {item.badge && (
                    <Badge variant="secondary" className="ml-auto">
                      {item.badge}
                    </Badge>
                  )}
                </>
              )}
            </div>
            {!collapsed && (
              <div className="flex-shrink-0 ml-2">
                <svg
                  className={cn(
                    'h-4 w-4 transition-transform',
                    isExpanded && 'rotate-90'
                  )}
                  viewBox="0 0 20 20"
                  fill="currentColor"
                >
                  <path
                    fillRule="evenodd"
                    d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z"
                    clipRule="evenodd"
                  />
                </svg>
              </div>
            )}
          </div>
        ) : (
          <Link
            href={item.href}
            className={cn(
              'flex items-center px-3 py-2 text-sm font-medium rounded-lg transition-colors',
              depth > 0 && 'ml-6',
              isActive
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:text-foreground hover:bg-accent',
              collapsed && 'justify-center px-2'
            )}
          >
            <div className="flex items-center min-w-0 flex-1">
              <div className="flex-shrink-0">{item.icon}</div>
              {!collapsed && (
                <>
                  <span className="ml-3 truncate">{item.label}</span>
                  {item.badge && (
                    <Badge variant="secondary" className="ml-auto">
                      {item.badge}
                    </Badge>
                  )}
                </>
              )}
            </div>
          </Link>
        )}
        {!collapsed && hasChildren && isExpanded && (
          <div className="mt-1 space-y-1">
            {item.children?.map((child) => renderNavItem(child, depth + 1))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className={cn(
      'flex flex-col bg-card border-r border-border h-full transition-all duration-300',
      collapsed ? 'w-16' : 'w-64'
    )}>
      {/* Header */}
      <div className="flex items-center h-16 px-4 border-b border-border">
        {!collapsed && (
          <div className="flex items-center">
            <h1 className="text-xl font-bold text-foreground">RatiChat</h1>
            <Badge variant="secondary" className="ml-2">Admin</Badge>
          </div>
        )}
        <button
          onClick={onToggle}
          className={cn(
            'flex items-center justify-center w-8 h-8 rounded-lg hover:bg-accent transition-colors',
            collapsed ? 'mx-auto' : 'ml-auto'
          )}
        >
          <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
            <path
              fillRule="evenodd"
              d="M3 5a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 10a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zM3 15a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1z"
              clipRule="evenodd"
            />
          </svg>
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4 space-y-2 overflow-y-auto">
        {items.map(renderNavItem)}
      </nav>

      {/* Footer */}
      {!collapsed && (
        <div className="p-4 border-t border-border">
          <div className="text-xs text-muted-foreground">
            RatiChat Admin v2.0.0
          </div>
        </div>
      )}
    </div>
  );
}
