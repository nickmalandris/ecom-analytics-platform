import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard,
  MessageSquare,
  Plug,
  LogOut,
  BarChart3,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { api, clearToken } from '@/lib/api';

const NAV_ITEMS = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/chat', label: 'Assistant', icon: MessageSquare },
  { path: '/connectors', label: 'Connectors', icon: Plug },
];

export default function Sidebar({ email }: { email?: string }) {
  const location = useLocation();
  const navigate = useNavigate();

  const handleLogout = async () => {
    try {
      await api.post('/auth/jwt/logout');
    } catch {
      // Bearer logout returns 204 — errors are non-critical
    } finally {
      clearToken();
      navigate('/login');
    }
  };

  const initials = email
    ? email.slice(0, 2).toUpperCase()
    : '??';

  return (
    <aside className="flex h-screen w-[240px] flex-col bg-sidebar text-sidebar-foreground">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-5 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand">
          <BarChart3 className="h-4.5 w-4.5 text-white" />
        </div>
        <span className="text-[15px] font-semibold tracking-tight">Analytics</span>
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
                  className={cn(
                    'flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] font-medium transition-colors',
                    isActive
                      ? 'bg-sidebar-active text-white'
                      : 'text-sidebar-muted hover:bg-sidebar-hover hover:text-sidebar-foreground'
                  )}
                >
                  <Icon className="h-4 w-4 flex-shrink-0" />
                  {label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* User section */}
      <div className="border-t border-sidebar-border px-3 py-3">
        <button
          onClick={handleLogout}
          className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-[13px] font-medium text-sidebar-muted transition-colors hover:bg-sidebar-hover hover:text-sidebar-foreground"
        >
          {/* Avatar */}
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-brand/20 text-[10px] font-bold text-brand-light">
            {initials}
          </div>
          <div className="flex-1 text-left">
            <p className="truncate text-[12px] text-sidebar-muted">{email || 'User'}</p>
          </div>
          <LogOut className="h-3.5 w-3.5 flex-shrink-0 opacity-60" />
        </button>
      </div>
    </aside>
  );
}
