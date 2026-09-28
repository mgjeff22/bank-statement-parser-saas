import React from 'react';
import { QuotaStatus } from '../../types';
import { AlertTriangle, Zap, ArrowUpRight } from 'lucide-react';

interface QuotaMeterProps {
  quota: QuotaStatus | null;
  onUpgradeClick: () => void;
}

export const QuotaMeter: React.FC<QuotaMeterProps> = ({ quota, onUpgradeClick }) => {
  if (!quota) {
    return (
      <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-xs animate-pulse">
        <div className="h-4 bg-slate-200 rounded w-1/3 mb-4"></div>
        <div className="h-6 bg-slate-200 rounded w-full mb-2"></div>
      </div>
    );
  }

  const { pages_used, monthly_limit, remaining_pages, tier } = quota;
  const percentage = monthly_limit > 0 ? Math.min(100, Math.round((pages_used / monthly_limit) * 100)) : 100;
  const isHighUsage = percentage >= 80;
  const isExhausted = remaining_pages <= 0;

  // Determine bar color
  let barColor = 'bg-emerald-500';
  if (percentage >= 90) {
    barColor = 'bg-rose-500';
  } else if (percentage >= 75) {
    barColor = 'bg-amber-500';
  }

  return (
    <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-xs relative overflow-hidden">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-4">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-base font-semibold text-slate-900">Monthly Page Consumption</h3>
            <span className="uppercase text-xs font-bold px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 border border-slate-200">
              {tier} Plan
            </span>
            {isHighUsage && (
              <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded bg-amber-100 text-amber-800 border border-amber-200 animate-pulse">
                <AlertTriangle className="h-3 w-3 text-amber-600" />
                {isExhausted ? 'Quota Exceeded' : '80%+ Used'}
              </span>
            )}
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Track processed statement pages against your active billing cycle allotment
          </p>
        </div>

        <button
          onClick={onUpgradeClick}
          className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-indigo-700 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 transition-colors shadow-xs shrink-0"
        >
          <Zap className="h-3.5 w-3.5 text-indigo-600 fill-indigo-600" />
          <span>Upgrade Tier</span>
          <ArrowUpRight className="h-3.5 w-3.5 ml-0.5" />
        </button>
      </div>

      {/* Progress Bar */}
      <div className="space-y-2">
        <div className="w-full bg-slate-100 rounded-full h-3 overflow-hidden border border-slate-200">
          <div
            className={`h-full rounded-full transition-all duration-500 ${barColor}`}
            style={{ width: `${percentage}%` }}
          ></div>
        </div>

        <div className="flex justify-between items-center text-xs text-slate-600">
          <span className="font-medium text-slate-800">
            {pages_used} of {monthly_limit} pages processed ({percentage}%)
          </span>
          <span className={remaining_pages <= 2 ? 'font-bold text-rose-600' : 'text-slate-500'}>
            {remaining_pages} page{remaining_pages !== 1 ? 's' : ''} remaining
          </span>
        </div>
      </div>
    </div>
  );
};
