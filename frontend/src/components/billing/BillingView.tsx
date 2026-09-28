import React, { useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { api } from '../../api/client';
import {
  Check,
  CreditCard,
  Zap,
  ArrowRight,
  ShieldCheck,
  Sparkles,
  ToggleLeft,
  ToggleRight,
  Send,
  AlertCircle,
  CheckCircle2,
} from 'lucide-react';

export const BillingView: React.FC = () => {
  const { user, refreshUser } = useAuth();
  const [billingInterval, setBillingInterval] = useState<'month' | 'year'>('month');
  const [loadingTier, setLoadingTier] = useState<string | null>(null);
  const [mockLoading, setMockLoading] = useState(false);
  const [webhookType, setWebhookType] = useState('invoice.payment_succeeded');
  const [webhookResult, setWebhookResult] = useState<string | null>(null);
  const [notification, setNotification] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const currentTier = user?.subscription_tier || 'free';

  const handleStripeCheckout = async (tier: string) => {
    setLoadingTier(tier);
    try {
      const res = await api.createCheckoutSession(tier, billingInterval);
      if (res.checkout_url) {
        window.location.href = res.checkout_url;
      }
    } catch (err: any) {
      setNotification({
        type: 'error',
        message: err.message || 'Failed to initialize Stripe checkout session.',
      });
    } finally {
      setLoadingTier(null);
    }
  };

  const handleMockUpgrade = async (targetTier: string) => {
    setMockLoading(true);
    setNotification(null);
    try {
      await api.mockUpgrade(targetTier);
      await refreshUser();
      setNotification({
        type: 'success',
        message: `Plan instantly switched to ${targetTier.toUpperCase()} in Mock Mode!`,
      });
      setTimeout(() => setNotification(null), 4000);
    } catch (err: any) {
      setNotification({
        type: 'error',
        message: err.message || 'Mock plan switch failed',
      });
    } finally {
      setMockLoading(false);
    }
  };

  const handleTestWebhook = async () => {
    setWebhookResult('Sending mock webhook event...');
    try {
      const res = await api.triggerMockWebhook(webhookType, {
        customer_email: user?.email,
        tier: 'pro',
      });
      setWebhookResult(`Webhook processed: ${JSON.stringify(res)}`);
      await refreshUser();
    } catch (err: any) {
      setWebhookResult(`Webhook error: ${err.message}`);
    }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-10">
      {/* Title */}
      <div className="text-center max-w-2xl mx-auto">
        <h2 className="text-3xl font-extrabold text-slate-900 tracking-tight">
          Subscription Plans & Quota Limits
        </h2>
        <p className="mt-2 text-sm text-slate-600">
          Scale your statement processing capacity with high-speed automated extraction and balance auditing
        </p>

        {/* Monthly / Annual Toggle */}
        <div className="mt-6 inline-flex items-center p-1 bg-slate-200/70 rounded-xl border border-slate-300">
          <button
            onClick={() => setBillingInterval('month')}
            className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              billingInterval === 'month'
                ? 'bg-white text-slate-900 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            Monthly Billing
          </button>
          <button
            onClick={() => setBillingInterval('year')}
            className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1 ${
              billingInterval === 'year'
                ? 'bg-white text-slate-900 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <span>Annual Billing</span>
            <span className="bg-emerald-100 text-emerald-800 text-[10px] px-1.5 py-0.2 rounded font-bold">
              Save 20%
            </span>
          </button>
        </div>
      </div>

      {notification && (
        <div
          className={`p-4 rounded-xl border text-sm flex items-center space-x-2 max-w-2xl mx-auto ${
            notification.type === 'success'
              ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
              : 'bg-rose-50 border-rose-200 text-rose-800'
          }`}
        >
          {notification.type === 'success' ? (
            <CheckCircle2 className="h-5 w-5 text-emerald-500 shrink-0" />
          ) : (
            <AlertCircle className="h-5 w-5 text-rose-500 shrink-0" />
          )}
          <span>{notification.message}</span>
        </div>
      )}

      {/* Pricing Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-8 items-stretch">
        {/* FREE PLAN */}
        <div
          className={`bg-white rounded-2xl border p-7 shadow-xs flex flex-col justify-between transition-all ${
            currentTier === 'free' ? 'border-indigo-500 ring-2 ring-indigo-500/20' : 'border-slate-200'
          }`}
        >
          <div>
            <div className="flex justify-between items-center">
              <h3 className="text-lg font-bold text-slate-900">Free Tier</h3>
              {currentTier === 'free' && (
                <span className="bg-indigo-100 text-indigo-800 text-xs font-bold px-2.5 py-0.5 rounded-full">
                  Current Plan
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500 mt-1">For testing and lightweight statement parsing</p>

            <div className="mt-5">
              <span className="text-3xl font-extrabold text-slate-900">$0</span>
              <span className="text-slate-500 text-xs"> / month</span>
            </div>

            <ul className="mt-6 space-y-3 text-xs text-slate-700">
              <li className="flex items-center gap-2">
                <Check className="h-4 w-4 text-emerald-600 shrink-0" />
                <span><strong>5 Pages</strong> monthly quota</span>
              </li>
              <li className="flex items-center gap-2">
                <Check className="h-4 w-4 text-emerald-600 shrink-0" />
                <span>PDF and scanned image OCR</span>
              </li>
              <li className="flex items-center gap-2">
                <Check className="h-4 w-4 text-emerald-600 shrink-0" />
                <span>Mathematical reconciliation check</span>
              </li>
              <li className="flex items-center gap-2">
                <Check className="h-4 w-4 text-emerald-600 shrink-0" />
                <span>CSV, XLSX, JSON downloads</span>
              </li>
            </ul>
          </div>

          <div className="mt-8">
            <button
              onClick={() => handleMockUpgrade('free')}
              disabled={currentTier === 'free' || mockLoading}
              className="w-full py-2.5 px-4 rounded-xl text-xs font-semibold border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {currentTier === 'free' ? 'Active Plan' : 'Downgrade to Free'}
            </button>
          </div>
        </div>

        {/* STARTER PLAN */}
        <div
          className={`bg-white rounded-2xl border p-7 shadow-xs flex flex-col justify-between transition-all relative ${
            currentTier === 'starter' ? 'border-indigo-500 ring-2 ring-indigo-500/20' : 'border-slate-200'
          }`}
        >
          <div>
            <div className="flex justify-between items-center">
              <h3 className="text-lg font-bold text-slate-900">Starter Tier</h3>
              {currentTier === 'starter' && (
                <span className="bg-indigo-100 text-indigo-800 text-xs font-bold px-2.5 py-0.5 rounded-full">
                  Current Plan
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500 mt-1">For freelancers, bookkeepers and solo accountants</p>

            <div className="mt-5">
              <span className="text-3xl font-extrabold text-slate-900">
                {billingInterval === 'month' ? '$29' : '$24'}
              </span>
              <span className="text-slate-500 text-xs"> / month</span>
            </div>

            <ul className="mt-6 space-y-3 text-xs text-slate-700">
              <li className="flex items-center gap-2">
                <Check className="h-4 w-4 text-emerald-600 shrink-0" />
                <span><strong>50 Pages</strong> monthly quota</span>
              </li>
              <li className="flex items-center gap-2">
                <Check className="h-4 w-4 text-emerald-600 shrink-0" />
                <span>High-resolution 300 DPI deskewing</span>
              </li>
              <li className="flex items-center gap-2">
                <Check className="h-4 w-4 text-emerald-600 shrink-0" />
                <span>Interactive Split-Pane Workspace</span>
              </li>
              <li className="flex items-center gap-2">
                <Check className="h-4 w-4 text-emerald-600 shrink-0" />
                <span>Anomaly resolution quick-fixes</span>
              </li>
            </ul>
          </div>

          <div className="mt-8 space-y-2">
            <button
              onClick={() => handleStripeCheckout('starter')}
              disabled={loadingTier !== null}
              className="w-full py-2.5 px-4 rounded-xl text-xs font-semibold bg-navy-800 hover:bg-navy-900 text-white shadow-xs transition-colors flex items-center justify-center gap-1.5"
            >
              <CreditCard className="h-4 w-4" />
              <span>Checkout with Stripe</span>
            </button>
            <button
              onClick={() => handleMockUpgrade('starter')}
              disabled={mockLoading || currentTier === 'starter'}
              className="w-full py-1.5 text-[11px] font-medium text-slate-600 hover:text-slate-900 border border-dashed border-slate-300 rounded-lg hover:bg-slate-50"
            >
              Mock Instant Switch
            </button>
          </div>
        </div>

        {/* PRO PLAN */}
        <div
          className={`bg-white rounded-2xl border p-7 shadow-md flex flex-col justify-between transition-all relative ${
            currentTier === 'pro'
              ? 'border-indigo-600 ring-2 ring-indigo-600/30'
              : 'border-indigo-200 bg-gradient-to-b from-indigo-50/20 to-white'
          }`}
        >
          <div className="absolute -top-3 right-6 bg-gradient-to-r from-indigo-600 to-purple-600 text-white text-[10px] font-bold uppercase tracking-wider py-1 px-3 rounded-full shadow-xs">
            Most Popular
          </div>

          <div>
            <div className="flex justify-between items-center">
              <h3 className="text-lg font-bold text-slate-900 flex items-center gap-1.5">
                <span>Pro Tier</span>
                <Sparkles className="h-4 w-4 text-indigo-600" />
              </h3>
              {currentTier === 'pro' && (
                <span className="bg-purple-100 text-purple-800 text-xs font-bold px-2.5 py-0.5 rounded-full">
                  Current Plan
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500 mt-1">For accounting firms and high-volume corporate teams</p>

            <div className="mt-5">
              <span className="text-3xl font-extrabold text-slate-900">
                {billingInterval === 'month' ? '$99' : '$79'}
              </span>
              <span className="text-slate-500 text-xs"> / month</span>
            </div>

            <ul className="mt-6 space-y-3 text-xs text-slate-700">
              <li className="flex items-center gap-2">
                <Check className="h-4 w-4 text-indigo-600 shrink-0" />
                <span><strong>500 Pages</strong> monthly quota</span>
              </li>
              <li className="flex items-center gap-2">
                <Check className="h-4 w-4 text-indigo-600 shrink-0" />
                <span>Multimodal Gemini 2.0 Flash fallback</span>
              </li>
              <li className="flex items-center gap-2">
                <Check className="h-4 w-4 text-indigo-600 shrink-0" />
                <span>Priority parsing queue & batch uploads</span>
              </li>
              <li className="flex items-center gap-2">
                <Check className="h-4 w-4 text-indigo-600 shrink-0" />
                <span>Multi-tenant isolation & team seats</span>
              </li>
            </ul>
          </div>

          <div className="mt-8 space-y-2">
            <button
              onClick={() => handleStripeCheckout('pro')}
              disabled={loadingTier !== null}
              className="w-full py-2.5 px-4 rounded-xl text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 text-white shadow-xs transition-colors flex items-center justify-center gap-1.5"
            >
              <Zap className="h-4 w-4" />
              <span>Checkout with Stripe</span>
            </button>
            <button
              onClick={() => handleMockUpgrade('pro')}
              disabled={mockLoading || currentTier === 'pro'}
              className="w-full py-1.5 text-[11px] font-medium text-slate-600 hover:text-slate-900 border border-dashed border-slate-300 rounded-lg hover:bg-slate-50"
            >
              Mock Instant Switch
            </button>
          </div>
        </div>
      </div>

      {/* Mock Billing & Webhook Simulator Panel */}
      <div className="bg-slate-900 text-slate-200 rounded-2xl p-6 border border-slate-800 shadow-sm space-y-4">
        <div className="flex items-center gap-2 text-indigo-400 font-semibold text-sm">
          <ShieldCheck className="h-5 w-5" />
          <span>Zero-Config Mock Billing & Webhook Lifecycle Simulator</span>
        </div>
        <p className="text-xs text-slate-400">
          Enables instantaneous automated testing and QA verification of subscription upgrades, plan switches, and webhook idempotency without live Stripe API keys.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
          {/* Mock Plan Toggles */}
          <div className="bg-slate-800/80 p-4 rounded-xl border border-slate-700 space-y-3">
            <div className="text-xs font-bold text-slate-300">Instant Plan Switch (Zero-Delay)</div>
            <div className="grid grid-cols-3 gap-2">
              <button
                onClick={() => handleMockUpgrade('free')}
                disabled={mockLoading}
                className="py-1.5 px-2 text-xs font-semibold rounded bg-slate-700 hover:bg-slate-600 text-white"
              >
                Free (5 pgs)
              </button>
              <button
                onClick={() => handleMockUpgrade('starter')}
                disabled={mockLoading}
                className="py-1.5 px-2 text-xs font-semibold rounded bg-blue-600 hover:bg-blue-500 text-white"
              >
                Starter (50 pgs)
              </button>
              <button
                onClick={() => handleMockUpgrade('pro')}
                disabled={mockLoading}
                className="py-1.5 px-2 text-xs font-semibold rounded bg-indigo-600 hover:bg-indigo-500 text-white"
              >
                Pro (500 pgs)
              </button>
            </div>
          </div>

          {/* Webhook Simulator */}
          <div className="bg-slate-800/80 p-4 rounded-xl border border-slate-700 space-y-3">
            <div className="text-xs font-bold text-slate-300">Fire Test Stripe Webhook</div>
            <div className="flex gap-2">
              <select
                value={webhookType}
                onChange={(e) => setWebhookType(e.target.value)}
                className="flex-1 px-2 py-1.5 text-xs bg-slate-900 border border-slate-600 rounded text-slate-200"
              >
                <option value="checkout.session.completed">checkout.session.completed</option>
                <option value="customer.subscription.updated">customer.subscription.updated</option>
                <option value="customer.subscription.deleted">customer.subscription.deleted</option>
                <option value="invoice.payment_succeeded">invoice.payment_succeeded</option>
                <option value="invoice.payment_failed">invoice.payment_failed</option>
              </select>
              <button
                onClick={handleTestWebhook}
                className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 rounded text-white shrink-0"
              >
                <Send className="h-3.5 w-3.5" />
                <span>Trigger</span>
              </button>
            </div>
            {webhookResult && (
              <div className="text-[11px] font-mono bg-slate-950 p-2 rounded border border-slate-700 text-emerald-400 overflow-x-auto">
                {webhookResult}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
