import React from 'react';
import { useAuth } from '../../context/AuthContext';
import { FileText, LayoutDashboard, CreditCard, LogOut, SplitSquareVertical } from 'lucide-react';

interface NavbarProps {
  currentView: 'dashboard' | 'workspace' | 'billing';
  onNavigate: (view: 'dashboard' | 'workspace' | 'billing') => void;
  activeStatementId?: string | null;
}

export const Navbar: React.FC<NavbarProps> = ({ currentView, onNavigate, activeStatementId }) => {
  const { user, logout } = useAuth();

  const getTierBadge = (tier?: string) => {
    switch (tier) {
      case 'pro':
        return <span className="px-2 py-0.5 text-xs font-semibold uppercase tracking-wider rounded bg-purple-100 text-purple-800 border border-purple-200">Pro</span>;
      case 'starter':
        return <span className="px-2 py-0.5 text-xs font-semibold uppercase tracking-wider rounded bg-blue-100 text-blue-800 border border-blue-200">Starter</span>;
      default:
        return <span className="px-2 py-0.5 text-xs font-semibold uppercase tracking-wider rounded bg-slate-100 text-slate-700 border border-slate-200">Free</span>;
    }
  };

  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-50 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16 items-center">
          {/* Brand */}
          <div className="flex items-center space-x-3 cursor-pointer" onClick={() => onNavigate('dashboard')}>
            <div className="h-10 w-10 rounded-lg bg-navy-800 flex items-center justify-center text-white shadow-md">
              <FileText className="h-5 w-5" />
            </div>
            <div>
              <div className="font-bold text-lg text-slate-900 tracking-tight flex items-center gap-2">
                StatementParser <span className="text-xs bg-indigo-600 text-white px-1.5 py-0.5 rounded font-mono font-medium">AI</span>
              </div>
              <p className="text-xs text-slate-500">Multimodal Micro-SaaS Engine</p>
            </div>
          </div>

          {/* Navigation Links */}
          <nav className="flex items-center space-x-1 sm:space-x-4">
            <button
              onClick={() => onNavigate('dashboard')}
              className={`flex items-center space-x-1.5 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                currentView === 'dashboard'
                  ? 'bg-slate-100 text-slate-900 font-semibold shadow-xs'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
              }`}
            >
              <LayoutDashboard className="h-4 w-4" />
              <span>Dashboard</span>
            </button>

            {activeStatementId && (
              <button
                onClick={() => onNavigate('workspace')}
                className={`flex items-center space-x-1.5 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  currentView === 'workspace'
                    ? 'bg-slate-100 text-slate-900 font-semibold shadow-xs'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                }`}
              >
                <SplitSquareVertical className="h-4 w-4" />
                <span>Workspace</span>
              </button>
            )}

            <button
              onClick={() => onNavigate('billing')}
              className={`flex items-center space-x-1.5 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                currentView === 'billing'
                  ? 'bg-slate-100 text-slate-900 font-semibold shadow-xs'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
              }`}
            >
              <CreditCard className="h-4 w-4" />
              <span>Billing & Plan</span>
            </button>
          </nav>

          {/* User Profile & Actions */}
          <div className="flex items-center space-x-3">
            <div className="hidden sm:flex flex-col items-end">
              <span className="text-sm font-medium text-slate-900">{user?.email}</span>
              <div className="mt-0.5">{getTierBadge(user?.subscription_tier)}</div>
            </div>

            <button
              onClick={logout}
              title="Sign Out"
              className="p-2 text-slate-500 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors"
            >
              <LogOut className="h-5 w-5" />
            </button>
          </div>
        </div>
      </div>
    </header>
  );
};
