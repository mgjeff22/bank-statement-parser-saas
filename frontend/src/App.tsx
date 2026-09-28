import React, { useState, useEffect } from 'react';
import { useAuth, AuthProvider } from './context/AuthContext';
import { Navbar } from './components/layout/Navbar';
import { LoginView } from './components/auth/LoginView';
import { RegisterView } from './components/auth/RegisterView';
import { QuotaMeter } from './components/dashboard/QuotaMeter';
import { UploadZone } from './components/dashboard/UploadZone';
import { HistoryTable } from './components/dashboard/HistoryTable';
import { WorkspaceView } from './components/workspace/WorkspaceView';
import { BillingView } from './components/billing/BillingView';
import { QuotaStatus, StatementHistoryItem } from './types';
import { api } from './api/client';
import { Loader2 } from 'lucide-react';

const AppContent: React.FC = () => {
  const { user, loading } = useAuth();
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login');
  const [currentView, setCurrentView] = useState<'dashboard' | 'workspace' | 'billing'>('dashboard');
  const [activeStatementId, setActiveStatementId] = useState<string | null>(null);

  const [quota, setQuota] = useState<QuotaStatus | null>(null);
  const [statements, setStatements] = useState<StatementHistoryItem[]>([]);
  const [loadingStatements, setLoadingStatements] = useState(false);

  // Fetch dashboard data
  const loadDashboardData = async () => {
    if (!user) return;
    try {
      const q = await api.getQuota();
      setQuota(q);
    } catch (e) {
      console.error('Failed to fetch quota', e);
    }

    setLoadingStatements(true);
    try {
      const list = await api.getStatementsHistory();
      setStatements(list);
    } catch (e) {
      console.error('Failed to fetch statement history', e);
    } finally {
      setLoadingStatements(false);
    }
  };

  useEffect(() => {
    if (user) {
      loadDashboardData();
    }
  }, [user]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <Loader2 className="h-10 w-10 text-indigo-600 animate-spin" />
      </div>
    );
  }

  // If not logged in, show auth screens
  if (!user) {
    return authMode === 'login' ? (
      <LoginView onSwitchToRegister={() => setAuthMode('register')} />
    ) : (
      <RegisterView onSwitchToLogin={() => setAuthMode('login')} />
    );
  }

  const handleOpenWorkspace = (statementId: string) => {
    setActiveStatementId(statementId);
    setCurrentView('workspace');
  };

  const handleUploadSuccess = async (statementId: string) => {
    await loadDashboardData();
    handleOpenWorkspace(statementId);
  };

  const handleDeleteStatement = async (statementId: string) => {
    try {
      await api.deleteStatement(statementId);
      if (activeStatementId === statementId) {
        setActiveStatementId(null);
        setCurrentView('dashboard');
      }
      await loadDashboardData();
    } catch (e) {
      console.error('Failed to delete statement', e);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col">
      <Navbar
        currentView={currentView}
        onNavigate={(v) => setCurrentView(v)}
        activeStatementId={activeStatementId}
      />

      <main className="flex-1">
        {currentView === 'dashboard' && (
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
            {/* Header banner */}
            <div>
              <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
                SaaS Dashboard
              </h1>
              <p className="text-sm text-slate-500 mt-1">
                Manage your statement extraction pipeline, quota consumption, and audit ledgers
              </p>
            </div>

            {/* Consumption Quota Meter */}
            <QuotaMeter
              quota={quota}
              onUpgradeClick={() => setCurrentView('billing')}
            />

            {/* Upload Zone */}
            <UploadZone
              quota={quota}
              onUploadSuccess={handleUploadSuccess}
              onQuotaExceeded={() => setCurrentView('billing')}
            />

            {/* Statement Processing History */}
            <HistoryTable
              statements={statements}
              loading={loadingStatements}
              onOpenWorkspace={handleOpenWorkspace}
              onDeleteStatement={handleDeleteStatement}
            />
          </div>
        )}

        {currentView === 'workspace' && activeStatementId && (
          <WorkspaceView
            statementId={activeStatementId}
            onBackToDashboard={() => setCurrentView('dashboard')}
          />
        )}

        {currentView === 'billing' && <BillingView />}
      </main>
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
};

export default App;
