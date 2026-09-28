import React, { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { Lock, Mail, ArrowRight, AlertCircle, FileSpreadsheet } from 'lucide-react';

interface LoginViewProps {
  onSwitchToRegister: () => void;
}

export const LoginView: React.FC<LoginViewProps> = ({ onSwitchToRegister }) => {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
    } catch (err: any) {
      setError(err.message || 'Login failed. Please verify credentials.');
    } finally {
      setLoading(false);
    }
  };

  const handleDemoFill = (tier: string) => {
    if (tier === 'pro') {
      setEmail('pro_user@example.com');
      setPassword('Password123!');
    } else if (tier === 'starter') {
      setEmail('starter_user@example.com');
      setPassword('Password123!');
    } else {
      setEmail('demo@example.com');
      setPassword('DemoPass123!');
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8 bg-white p-8 rounded-xl shadow-lg border border-slate-200">
        <div className="text-center">
          <div className="mx-auto h-12 w-12 rounded-xl bg-navy-800 flex items-center justify-center text-white shadow-md">
            <FileSpreadsheet className="h-6 w-6" />
          </div>
          <h2 className="mt-4 text-3xl font-extrabold text-slate-900 tracking-tight">
            Sign in to StatementParser
          </h2>
          <p className="mt-2 text-sm text-slate-600">
            Multimodal AI statement parser, reconciliation & export engine
          </p>
        </div>

        {error && (
          <div className="p-4 bg-rose-50 border border-rose-200 rounded-lg flex items-start space-x-3 text-rose-800 text-sm">
            <AlertCircle className="h-5 w-5 text-rose-500 shrink-0 mt-0.5" />
            <div>{error}</div>
          </div>
        )}

        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Email address</label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                  <Mail className="h-5 w-5" />
                </div>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@company.com"
                  className="block w-full pl-10 pr-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">Password</label>
              <div className="relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-400">
                  <Lock className="h-5 w-5" />
                </div>
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="block w-full pl-10 pr-3 py-2 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 text-sm"
                />
              </div>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full flex justify-center items-center py-2.5 px-4 border border-transparent rounded-lg shadow-sm text-sm font-medium text-white bg-navy-800 hover:bg-navy-900 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 transition-colors disabled:opacity-50"
          >
            {loading ? 'Authenticating...' : 'Sign in'}
            {!loading && <ArrowRight className="ml-2 h-4 w-4" />}
          </button>
        </form>

        {/* Quick Demo Fill Buttons */}
        <div className="pt-2 border-t border-slate-200">
          <div className="text-xs text-slate-500 text-center mb-2">Or quick-fill demo credentials:</div>
          <div className="grid grid-cols-3 gap-2">
            <button
              type="button"
              onClick={() => handleDemoFill('free')}
              className="px-2 py-1 text-xs font-medium border border-slate-200 rounded hover:bg-slate-50 text-slate-700"
            >
              Free Demo
            </button>
            <button
              type="button"
              onClick={() => handleDemoFill('starter')}
              className="px-2 py-1 text-xs font-medium border border-slate-200 rounded hover:bg-slate-50 text-blue-700 bg-blue-50"
            >
              Starter Demo
            </button>
            <button
              type="button"
              onClick={() => handleDemoFill('pro')}
              className="px-2 py-1 text-xs font-medium border border-slate-200 rounded hover:bg-slate-50 text-purple-700 bg-purple-50"
            >
              Pro Demo
            </button>
          </div>
        </div>

        <div className="text-center text-sm">
          <span className="text-slate-500">Don't have an account? </span>
          <button
            onClick={onSwitchToRegister}
            className="font-medium text-indigo-600 hover:text-indigo-500 underline"
          >
            Create account
          </button>
        </div>
      </div>
    </div>
  );
};
