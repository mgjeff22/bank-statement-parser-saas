import React from 'react';
import { ReconciliationSummary } from '../../types';
import { CheckCircle2, AlertTriangle, ArrowRight, RefreshCw, Info } from 'lucide-react';

interface ReconciliationBannerProps {
  reconciliation: ReconciliationSummary;
  onAutoRecalculate?: () => void;
}

export const ReconciliationBanner: React.FC<ReconciliationBannerProps> = ({
  reconciliation,
  onAutoRecalculate,
}) => {
  const {
    starting_balance,
    total_credits,
    total_debits,
    net_cashflow,
    calculated_ending_balance,
    reported_ending_balance,
    discrepancy,
    is_reconciled,
    diagnostic_flags,
  } = reconciliation;

  return (
    <div
      className={`rounded-xl border p-5 transition-all shadow-xs ${
        is_reconciled
          ? 'bg-emerald-50/90 border-emerald-300 text-emerald-950'
          : 'bg-rose-50/90 border-rose-300 text-rose-950'
      }`}
    >
      {/* Header Status Row */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-black/10">
        <div className="flex items-center space-x-2.5">
          {is_reconciled ? (
            <div className="h-8 w-8 rounded-full bg-emerald-100 border border-emerald-300 flex items-center justify-center text-emerald-700 shrink-0">
              <CheckCircle2 className="h-5 w-5" />
            </div>
          ) : (
            <div className="h-8 w-8 rounded-full bg-rose-100 border border-rose-300 flex items-center justify-center text-rose-700 shrink-0 animate-pulse">
              <AlertTriangle className="h-5 w-5" />
            </div>
          )}

          <div>
            <div className="font-bold text-base flex items-center gap-2">
              <span>{is_reconciled ? 'Mathematical Balance Verified' : 'Reconciliation Discrepancy Flagged'}</span>
              <span
                className={`text-xs px-2 py-0.5 rounded-full font-mono font-bold uppercase tracking-wider ${
                  is_reconciled
                    ? 'bg-emerald-200 text-emerald-900 border border-emerald-300'
                    : 'bg-rose-200 text-rose-900 border border-rose-300'
                }`}
              >
                {is_reconciled ? 'Variance $0.00' : `Variance $${discrepancy}`}
              </span>
            </div>
            <p className="text-xs opacity-80">
              Formula: Starting (${starting_balance}) + Credits (${total_credits}) - Debits (${total_debits}) == Calculated (${calculated_ending_balance})
            </p>
          </div>
        </div>

        {onAutoRecalculate && (
          <button
            onClick={onAutoRecalculate}
            className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-white/80 hover:bg-white text-slate-800 border border-slate-300 shadow-2xs transition-colors shrink-0"
          >
            <RefreshCw className="h-3.5 w-3.5 text-slate-600" />
            <span>Recalculate Math</span>
          </button>
        )}
      </div>

      {/* Numerical Ledger Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 pt-3 text-xs">
        <div className="bg-white/70 p-2.5 rounded-lg border border-black/5 shadow-2xs">
          <div className="text-slate-500 font-medium">Starting Balance</div>
          <div className="text-sm font-bold text-slate-900 font-mono mt-0.5">${starting_balance}</div>
        </div>

        <div className="bg-white/70 p-2.5 rounded-lg border border-black/5 shadow-2xs">
          <div className="text-emerald-700 font-medium">(+) Total Credits</div>
          <div className="text-sm font-bold text-emerald-800 font-mono mt-0.5">+${total_credits}</div>
        </div>

        <div className="bg-white/70 p-2.5 rounded-lg border border-black/5 shadow-2xs">
          <div className="text-rose-700 font-medium">(-) Total Debits</div>
          <div className="text-sm font-bold text-rose-800 font-mono mt-0.5">-${total_debits}</div>
        </div>

        <div className="bg-white/70 p-2.5 rounded-lg border border-black/5 shadow-2xs">
          <div className="text-slate-600 font-medium">Net Cashflow</div>
          <div className="text-sm font-bold text-slate-900 font-mono mt-0.5">${net_cashflow}</div>
        </div>

        <div className="bg-white/70 p-2.5 rounded-lg border border-black/5 shadow-2xs">
          <div className="text-slate-600 font-medium">Calculated Ending</div>
          <div className="text-sm font-bold text-indigo-900 font-mono mt-0.5">${calculated_ending_balance}</div>
        </div>

        <div className="bg-white/70 p-2.5 rounded-lg border border-black/5 shadow-2xs">
          <div className="text-slate-600 font-medium">Reported Ending</div>
          <div className="text-sm font-bold text-slate-900 font-mono mt-0.5">${reported_ending_balance}</div>
        </div>
      </div>

      {/* Diagnostics Alerts */}
      {diagnostic_flags && diagnostic_flags.length > 0 && (
        <div className="mt-3 pt-3 border-t border-black/10">
          <div className="flex items-center gap-1.5 text-xs font-bold text-slate-800 mb-1.5">
            <Info className="h-3.5 w-3.5 text-amber-600" />
            <span>Anomaly Diagnostic Insights ({diagnostic_flags.length}):</span>
          </div>
          <ul className="space-y-1">
            {diagnostic_flags.map((flag, idx) => (
              <li
                key={idx}
                className="text-xs font-mono bg-white/60 px-2 py-1 rounded border border-amber-200 text-amber-900 flex items-start gap-1"
              >
                <span className="text-amber-600 font-bold">•</span>
                <span>{flag}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};
