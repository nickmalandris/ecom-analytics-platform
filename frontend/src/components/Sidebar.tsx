import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard,
  MessageSquare,
  Plug,
  LogOut,
  BarChart3,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { api, clearToken } from '@/lib/api';

const NAV_ITEMS = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/chat', label: 'Assistant', icon: MessageSquare },
  { path: '/connectors', label: 'Connectors', icon: Plug },
];

export interface SidebarProps {
  email?: string;
  collapsed: boolean;
  mobileOpen: boolean;
  onToggleCollapse: () => void;
  onCloseMobile: () => void;
}

export default function Sidebar({
  email,
  collapsed,
  mobileOpen,
  onToggleCollapse,
  onCloseMobile,
}: SidebarProps) {
  const location = useLocation();
  const navigate = useNavigate();

  const handleLogout = async () => {
    try {
      await api.post('/auth/jwt/logout');
    } catch {
      // Bearer logout returns 204 -- errors are non-critical
    } finally {
      clearToken();
      navigate('/login');
    }
  };

  const handleNavClick = () => {
    // Auto-close drawer on mobile when navigating
    onCloseMobile();
  };

  const initials = email ? email.slice(0, 2).toUpperCase() : '??';

  /* ── Shared sidebar content (used by both desktop & mobile) ── */
  const sidebarContent = (
    <>
      {/* Logo */}
      <div className={cn('flex items-center gap-2.5 py-5', collapsed ? 'justify-center px-2' : 'px-5')}>
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand">
          <BarChart3 className="h-4.5 w-4.5 text-white" />
        </div>
        {!collapsed && (
          <span className="text-[15px] font-semibold tracking-tight">Analytics</span>
        )}
      </div>

      {/* Separator */}
      <div className="mx-4 border-t border-sidebar-border" />

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4">
        <ul className="space-y-1">
          {NAV_ITEMS.map(({ path, label, icon: Icon }) => {
            const isActive = location.pathname === path;
            return (
              <li key={path}>
                <Link
                  to={path}
                  onClick={handleNavClick}
                  title={collapsed ? label : undefined}
                  className={cn(
                    'flex items-center rounded-lg py-2 text-[13px] font-medium transition-colors',
                    collapsed ? 'justify-center px-2' : 'gap-3 px-3',
                    isActive
                      ? 'bg-sidebar-active text-white'
                      : 'text-sidebar-muted hover:bg-sidebar-hover hover:text-sidebar-foreground',
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  {!collapsed && label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Collapse toggle — desktop only */}
      <div className="hidden lg:block px-3 pb-1">
        <button
          onClick={onToggleCollapse}
          className="flex w-full items-center justify-center rounded-lg py-2 text-sidebar-muted transition-colors hover:bg-sidebar-hover hover:text-sidebar-foreground"
          title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >
          {collapsed ? (
            <PanelLeftOpen className="h-4 w-4" />
          ) : (
            <PanelLeftClose className="h-4 w-4" />
          )}
        </button>
      </div>

      {/* User section */}
      <div className="border-t border-sidebar-border px-3 py-3">
        <button
          onClick={handleLogout}
          title={collapsed ? 'Log out' : undefined}
          className={cn(
            'flex w-full items-center rounded-lg py-2 text-[13px] font-medium text-sidebar-muted transition-colors hover:bg-sidebar-hover hover:text-sidebar-foreground',
            collapsed ? 'justify-center px-2' : 'gap-3 px-3',
          )}
        >
          {/* Avatar */}
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand/20 text-[10px] font-bold text-brand-light">
            {initials}
          </div>
          {!collapsed && (
            <>
              <div className="flex-1 text-left">
                <p className="truncate text-[12px] text-sidebar-muted">
                  {email || 'User'}
                </p>
              </div>
              <LogOut className="h-3.5 w-3.5 shrink-0 opacity-60" />
            </>
          )}
        </button>
      </div>
    </>
  );

  return (
    <>
      {/* ── Desktop sidebar ─────────────────────────────── */}
      <aside
        className={cn(
          'hidden lg:flex h-screen flex-col bg-sidebar text-sidebar-foreground transition-all duration-200',
          collapsed ? 'w-16' : 'w-[240px]',
        )}
      >
        {sidebarContent}
      </aside>

      {/* ── Mobile drawer overlay ───────────────────────── */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 lg:hidden"
          onClick={onCloseMobile}
          aria-hidden="true"
        />
      )}

      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 flex w-[240px] flex-col bg-sidebar text-sidebar-foreground transition-transform duration-200 lg:hidden',
          mobileOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        {/* Re-render content in mobile mode — always expanded */}
        <>
          {/* Logo */}
          <div className="flex items-center gap-2.5 px-5 py-5">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand">
              <BarChart3 className="h-4.5 w-4.5 text-white" />
            </div>
            <span className="text-[15px] font-semibold tracking-tight">Analytics</span>
          </div>

          <div className="mx-4 border-t border-sidebar-border" />

          <nav className="flex-1 px-3 py-4">
            <ul className="space-y-1">
              {NAV_ITEMS.map(({ path, label, icon: Icon }) => {
                const isActive = location.pathname === path;
                return (
                  <li key={path}>
                    <Link
                      to={path}
                      onClick={handleNavClick}
                      className={cn(
                        'flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors',
                        isActive
                          ? 'bg-sidebar-active text-white'
                          : 'text-sidebar-muted hover:bg-sidebar-hover hover:text-sidebar-foreground',
                      )}
                    >
                      <Icon className="h-4 w-4 shrink-0" />
                      {label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>

          <div className="border-t border-sidebar-border px-3 py-3">
            <button
              onClick={handleLogout}
              className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-[13px] font-medium text-sidebar-muted transition-colors hover:bg-sidebar-hover hover:text-sidebar-foreground"
            >
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-brand/20 text-[10px] font-bold text-brand-light">
                {initials}
              </div>
              <div className="flex-1 text-left">
                <p className="truncate text-[12px] text-sidebar-muted">
                  {email || 'User'}
                </p>
              </div>
              <LogOut className="h-3.5 w-3.5 shrink-0 opacity-60" />
            </button>
          </div>
        </>
      </aside>
    </>
  );
}
