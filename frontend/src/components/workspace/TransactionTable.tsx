import React, { useState, useMemo } from 'react';
import { TransactionRecord, TransactionType, AnomalyType } from '../../types';
import {
  Plus,
  Trash2,
  Search,
  Filter,
  AlertTriangle,
  ArrowUpDown,
  Save,
  Check,
  RotateCcw,
  Sparkles,
} from 'lucide-react';

interface TransactionTableProps {
  transactions: TransactionRecord[];
  onTransactionsChange: (updated: TransactionRecord[]) => void;
  onSave: () => void;
  isSaving: boolean;
  onSelectRow?: (rowId: string) => void;
  selectedRowId?: string | null;
}

const CATEGORY_OPTIONS = [
  'Revenue',
  'Income / Payroll',
  'Software & Subscriptions',
  'Office Supplies',
  'Travel & Meals',
  'Utilities',
  'Banking & Fees',
  'Taxes',
  'Miscellaneous',
];

export const TransactionTable: React.FC<TransactionTableProps> = ({
  transactions,
  onTransactionsChange,
  onSave,
  isSaving,
  onSelectRow,
  selectedRowId,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('ALL');
  const [typeFilter, setTypeFilter] = useState<'ALL' | 'debit' | 'credit'>('ALL');
  const [anomalyOnly, setAnomalyOnly] = useState(false);

  // Filtered transactions
  const filteredTransactions = useMemo(() => {
    return transactions.filter((tx) => {
      // Search
      const q = searchQuery.toLowerCase().trim();
      const matchesSearch =
        !q ||
        tx.payee.toLowerCase().includes(q) ||
        tx.category.toLowerCase().includes(q) ||
        tx.amount.includes(q) ||
        tx.date.includes(q);

      // Category
      const matchesCategory = categoryFilter === 'ALL' || tx.category === categoryFilter;

      // Type
      const matchesType = typeFilter === 'ALL' || tx.type === typeFilter;

      // Anomaly
      const matchesAnomaly = !anomalyOnly || Boolean(tx.has_anomaly);

      return matchesSearch && matchesCategory && matchesType && matchesAnomaly;
    });
  }, [transactions, searchQuery, categoryFilter, typeFilter, anomalyOnly]);

  // Update a single cell
  const handleCellChange = (id: string, field: keyof TransactionRecord, val: any) => {
    const updated = transactions.map((t) => {
      if (t.id === id) {
        return { ...t, [field]: val };
      }
      return t;
    });
    onTransactionsChange(updated);
  };

  // Quick-fix sign inversion
  const handleFixSignInversion = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const updated = transactions.map((t) => {
      if (t.id === id) {
        const flippedType: TransactionType = t.type === 'credit' ? 'debit' : 'credit';
        return {
          ...t,
          type: flippedType,
          has_anomaly: false,
          anomaly_type: null,
        };
      }
      return t;
    });
    onTransactionsChange(updated);
  };

  // Add new row
  const handleAddRow = () => {
    const newId = `tx_manual_${Date.now()}`;
    const today = new Date().toISOString().split('T')[0];
    const newTx: TransactionRecord = {
      id: newId,
      date: today,
      payee: 'New Payee',
      type: 'debit',
      amount: '0.00',
      category: 'Miscellaneous',
      running_balance: '0.00',
      has_anomaly: false,
      anomaly_type: null,
    };
    onTransactionsChange([newTx, ...transactions]);
    if (onSelectRow) onSelectRow(newId);
  };

  // Delete row
  const handleDeleteRow = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const updated = transactions.filter((t) => t.id !== id);
    onTransactionsChange(updated);
  };

  const getAnomalyBadge = (tx: TransactionRecord) => {
    if (!tx.has_anomaly) return null;

    let label = 'Anomaly';
    let quickFixText: string | null = null;
    let onQuickFix: ((e: React.MouseEvent) => void) | null = null;

    switch (tx.anomaly_type) {
      case 'SIGN_INVERSION':
        label = 'Sign Inversion';
        quickFixText = `Flip to ${tx.type === 'credit' ? 'Debit' : 'Credit'}`;
        onQuickFix = (e) => handleFixSignInversion(tx.id, e);
        break;
      case 'MISSING_GAP':
        label = 'Balance Break';
        break;
      case 'OUT_OF_ORDER_DATE':
        label = 'Out-of-Order Date';
        break;
      case 'TRANSPOSITION':
        label = 'Transposition Error';
        break;
      default:
        label = 'Flagged';
        break;
    }

    return (
      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold bg-amber-100 text-amber-900 border border-amber-300">
          <AlertTriangle className="h-3 w-3 text-amber-600" />
          {label}
        </span>
        {quickFixText && onQuickFix && (
          <button
            onClick={onQuickFix}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-indigo-50 text-indigo-700 hover:bg-indigo-100 border border-indigo-200 transition-colors shadow-2xs"
            title="Auto-apply algorithmic fix"
          >
            <Sparkles className="h-3 w-3 text-indigo-600" />
            <span>{quickFixText}</span>
          </button>
        )}
      </div>
    );
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-xs flex flex-col h-full overflow-hidden">
      {/* Grid Toolbar */}
      <div className="p-4 border-b border-slate-200 space-y-3 bg-slate-50/50">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          {/* Search Input */}
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none h-5 w-5 text-slate-400" />
            <input
              type="text"
              placeholder="Search payee, category, amount..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 text-xs bg-white border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
            />
          </div>

          {/* Action Buttons */}
          <div className="flex items-center space-x-2 shrink-0">
            <button
              onClick={handleAddRow}
              className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 border border-slate-300 shadow-2xs transition-colors"
            >
              <Plus className="h-3.5 w-3.5 text-slate-600" />
              <span>Add Row</span>
            </button>

            <button
              onClick={onSave}
              disabled={isSaving}
              className="inline-flex items-center space-x-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 shadow-xs transition-colors disabled:opacity-50"
            >
              {isSaving ? (
                <span>Saving...</span>
              ) : (
                <>
                  <Save className="h-3.5 w-3.5" />
                  <span>Save Changes</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Filter Pills */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          {/* Type Filter */}
          <div className="flex items-center bg-white border border-slate-200 rounded-lg p-0.5 shadow-2xs">
            <button
              onClick={() => setTypeFilter('ALL')}
              className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                typeFilter === 'ALL' ? 'bg-slate-900 text-white font-semibold' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              All Types
            </button>
            <button
              onClick={() => setTypeFilter('debit')}
              className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                typeFilter === 'debit' ? 'bg-rose-600 text-white font-semibold' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Debits Only
            </button>
            <button
              onClick={() => setTypeFilter('credit')}
              className={`px-2.5 py-1 rounded text-xs font-medium transition-colors ${
                typeFilter === 'credit' ? 'bg-emerald-600 text-white font-semibold' : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              Credits Only
            </button>
          </div>

          {/* Category Filter */}
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="px-2.5 py-1.5 bg-white border border-slate-300 rounded-lg text-xs text-slate-700 focus:ring-1 focus:ring-indigo-500"
          >
            <option value="ALL">All Categories</option>
            {CATEGORY_OPTIONS.map((cat) => (
              <option key={cat} value={cat}>
                {cat}
              </option>
            ))}
          </select>

          {/* Anomaly Toggle */}
          <button
            onClick={() => setAnomalyOnly(!anomalyOnly)}
            className={`px-2.5 py-1.5 rounded-lg border text-xs font-medium transition-colors flex items-center gap-1.5 ${
              anomalyOnly
                ? 'bg-amber-100 border-amber-300 text-amber-900 font-bold'
                : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}
          >
            <AlertTriangle className="h-3.5 w-3.5 text-amber-600" />
            <span>Show Flagged Only</span>
          </button>

          <span className="ml-auto text-slate-500 font-mono">
            {filteredTransactions.length} of {transactions.length} rows
          </span>
        </div>
      </div>

      {/* Table */}
      <div className="flex-1 overflow-auto">
        <table className="w-full text-left text-xs border-collapse">
          <thead className="bg-slate-100 text-slate-600 uppercase font-semibold sticky top-0 z-10 border-b border-slate-200">
            <tr>
              <th className="py-2.5 px-3 w-10 text-center">#</th>
              <th className="py-2.5 px-3 w-28">Date</th>
              <th className="py-2.5 px-3">Description / Payee</th>
              <th className="py-2.5 px-3 w-24">Type</th>
              <th className="py-2.5 px-3 w-28 text-right">Amount</th>
              <th className="py-2.5 px-3 w-36">Category</th>
              <th className="py-2.5 px-3 w-28 text-right">Running Bal</th>
              <th className="py-2.5 px-3 w-36">Anomaly / Fix</th>
              <th className="py-2.5 px-2 w-10 text-center">Del</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filteredTransactions.map((tx, idx) => {
              const isSelected = selectedRowId === tx.id;
              const hasAnomaly = tx.has_anomaly;

              return (
                <tr
                  key={tx.id}
                  onClick={() => onSelectRow && onSelectRow(tx.id)}
                  className={`transition-colors cursor-pointer ${
                    isSelected
                      ? 'bg-indigo-50/70 border-l-4 border-indigo-600'
                      : hasAnomaly
                      ? 'bg-amber-50/40 hover:bg-amber-50/70'
                      : 'hover:bg-slate-50'
                  }`}
                >
                  {/* Row Index */}
                  <td className="py-2 px-3 text-center text-slate-400 font-mono text-[11px]">
                    {idx + 1}
                  </td>

                  {/* Date Input */}
                  <td className="py-1 px-2">
                    <input
                      type="date"
                      value={tx.date}
                      onChange={(e) => handleCellChange(tx.id, 'date', e.target.value)}
                      className="w-full px-1.5 py-1 bg-transparent hover:bg-white focus:bg-white border border-transparent hover:border-slate-300 focus:border-indigo-500 rounded text-xs font-mono"
                    />
                  </td>

                  {/* Payee Input */}
                  <td className="py-1 px-2">
                    <input
                      type="text"
                      value={tx.payee}
                      onChange={(e) => handleCellChange(tx.id, 'payee', e.target.value)}
                      className="w-full px-1.5 py-1 bg-transparent hover:bg-white focus:bg-white border border-transparent hover:border-slate-300 focus:border-indigo-500 rounded text-xs font-medium text-slate-900"
                    />
                  </td>

                  {/* Type Pill Toggle */}
                  <td className="py-1 px-2">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleCellChange(tx.id, 'type', tx.type === 'credit' ? 'debit' : 'credit');
                      }}
                      className={`w-full text-center px-2 py-0.5 rounded-full font-bold text-[11px] uppercase tracking-wider transition-colors ${
                        tx.type === 'credit'
                          ? 'bg-emerald-100 text-emerald-800 border border-emerald-300 hover:bg-emerald-200'
                          : 'bg-rose-100 text-rose-800 border border-rose-300 hover:bg-rose-200'
                      }`}
                    >
                      {tx.type}
                    </button>
                  </td>

                  {/* Amount Input */}
                  <td className="py-1 px-2 text-right">
                    <input
                      type="text"
                      value={tx.amount}
                      onChange={(e) => handleCellChange(tx.id, 'amount', e.target.value)}
                      className="w-full text-right px-1.5 py-1 bg-transparent hover:bg-white focus:bg-white border border-transparent hover:border-slate-300 focus:border-indigo-500 rounded text-xs font-mono font-bold text-slate-900"
                    />
                  </td>

                  {/* Category Dropdown */}
                  <td className="py-1 px-2">
                    <select
                      value={tx.category}
                      onChange={(e) => handleCellChange(tx.id, 'category', e.target.value)}
                      className="w-full px-1.5 py-1 bg-transparent hover:bg-white focus:bg-white border border-transparent hover:border-slate-300 focus:border-indigo-500 rounded text-xs text-slate-700"
                    >
                      {CATEGORY_OPTIONS.map((cat) => (
                        <option key={cat} value={cat}>
                          {cat}
                        </option>
                      ))}
                    </select>
                  </td>

                  {/* Running Balance */}
                  <td className="py-2 px-3 text-right font-mono text-slate-600">
                    ${tx.running_balance}
                  </td>

                  {/* Anomaly Badge / Fix */}
                  <td className="py-1 px-2">{getAnomalyBadge(tx)}</td>

                  {/* Delete Button */}
                  <td className="py-1 px-2 text-center">
                    <button
                      onClick={(e) => handleDeleteRow(tx.id, e)}
                      title="Delete row"
                      className="p-1 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded transition-colors"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
