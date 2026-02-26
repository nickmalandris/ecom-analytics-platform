import type { ReactNode } from 'react';
import Sidebar from './Sidebar';

interface LayoutProps {
  children: ReactNode;
  email?: string;
}

export default function Layout({ children, email }: LayoutProps) {
  return (
    <div className="flex h-screen bg-gray-50">
      <Sidebar email={email} />
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-7xl px-6 py-6 lg:px-8">
          {children}
        </div>
      </main>
    </div>
  );
}
