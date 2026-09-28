import React, { useState, useEffect } from 'react';
import { StatementDetails, TransactionRecord, ReconciliationSummary } from '../../types';
import { api } from '../../api/client';
import { DocumentViewer } from './DocumentViewer';
import { ReconciliationBanner } from './ReconciliationBanner';
import { TransactionTable } from './TransactionTable';
import {
  ArrowLeft,
  Download,
  FileSpreadsheet,
  FileText,
  Code2,
  CheckCircle2,
  AlertCircle,
  Loader2,
} from 'lucide-react';

interface WorkspaceViewProps {
  statementId: string;
  onBackToDashboard: () => void;
}

export const WorkspaceView: React.FC<WorkspaceViewProps> = ({ statementId, onBackToDashboard }) => {
  const [details, setDetails] = useState<StatementDetails | null>(null);
  const [transactions, setTransactions] = useState<TransactionRecord[]>([]);
  const [reconciliation, setReconciliation] = useState<ReconciliationSummary | null>(null);
  const [selectedRowId, setSelectedRowId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [exportingFormat, setExportingFormat] = useState<string | null>(null);
  const [notification, setNotification] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Load statement details
  const loadStatement = async () => {
    setLoading(true);
    try {
      const data = await api.getStatementTransactions(statementId);
      setDetails(data);
      setTransactions(data.transactions || []);
      setReconciliation(data.reconciliation);
    } catch (err: any) {
      setNotification({
        type: 'error',
        message: err.message || 'Failed to load statement workspace data',
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStatement();
  }, [statementId]);

  // Client-side optimistic recalculation whenever transactions change
  const handleTransactionsChange = async (updated: TransactionRecord[]) => {
    setTransactions(updated);
    if (details) {
      try {
        const liveRec = await api.directReconcile(
          details.starting_balance,
          details.ending_balance,
          updated
        );
        setReconciliation(liveRec);
      } catch {
        // Fallback: in-memory basic arithmetic if offline
        let credits = 0;
        let debits = 0;
        updated.forEach((t) => {
          const amt = parseFloat(t.amount) || 0;
          if (t.type === 'credit') credits += amt;
          else debits += amt;
        });
        const start = parseFloat(details.starting_balance) || 0;
        const repEnd = parseFloat(details.ending_balance) || 0;
        const net = credits - debits;
        const calcEnd = start + net;
        const disc = calcEnd - repEnd;
        if (reconciliation) {
          setReconciliation({
            ...reconciliation,
            total_credits: credits.toFixed(2),
            total_debits: debits.toFixed(2),
            net_cashflow: net.toFixed(2),
            calculated_ending_balance: calcEnd.toFixed(2),
            discrepancy: disc.toFixed(2),
            is_reconciled: Math.abs(disc) < 0.005,
          });
        }
      }
    }
  };

  // Save changes to backend
  const handleSave = async () => {
    setIsSaving(true);
    setNotification(null);
    try {
      const res = await api.updateTransactions(
        statementId,
        transactions,
        details?.starting_balance,
        details?.ending_balance
      );
      setReconciliation(res.reconciliation);
      setTransactions(res.transactions);
      setNotification({
        type: 'success',
        message: 'Transactions saved and mathematical balance updated successfully!',
      });
      setTimeout(() => setNotification(null), 4000);
    } catch (err: any) {
      setNotification({
        type: 'error',
        message: err.message || 'Failed to save transaction modifications',
      });
    } finally {
      setIsSaving(false);
    }
  };

  // Trigger exporter download
  const handleExport = async (format: 'csv' | 'xlsx' | 'json') => {
    setExportingFormat(format);
    try {
      const baseFilename = details?.filename ? details.filename.replace(/\.[^/.]+$/, '') : 'statement';
      await api.downloadExport(statementId, format, `${baseFilename}_reconciled`);
      setNotification({
        type: 'success',
        message: `Successfully exported to ${format.toUpperCase()}!`,
      });
      setTimeout(() => setNotification(null), 3000);
    } catch (err: any) {
      setNotification({
        type: 'error',
        message: err.message || `Failed to export to ${format.toUpperCase()}`,
      });
    } finally {
      setExportingFormat(null);
    }
  };

  if (loading) {
    return (
      <div className="min-h-[70vh] flex flex-col items-center justify-center space-y-4">
        <Loader2 className="h-10 w-10 text-indigo-600 animate-spin" />
        <div className="text-slate-600 font-medium">Opening Interactive Workspace...</div>
      </div>
    );
  }

  return (
    <div className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-4">
      {/* Top Header & Actions Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-xs flex flex-col lg:flex-row lg:items-center justify-between gap-4">
        <div className="flex items-center space-x-3">
          <button
            onClick={onBackToDashboard}
            className="p-2 hover:bg-slate-100 rounded-lg text-slate-500 hover:text-slate-800 transition-colors"
            title="Back to Dashboard"
          >
            <ArrowLeft className="h-5 w-5" />
          </button>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold text-slate-900 tracking-tight">
                {details?.filename || 'Bank Statement Workspace'}
              </h2>
              <span className="text-xs font-mono bg-slate-100 text-slate-700 px-2 py-0.5 rounded border border-slate-200">
                {statementId}
              </span>
            </div>
            <p className="text-xs text-slate-500">
              Interactive Split-Pane inspection, anomaly resolution & multi-format exporter
            </p>
          </div>
        </div>

        {/* Exporter Toolbar */}
        <div className="flex flex-wrap items-center gap-2">
          <div className="text-xs font-semibold text-slate-500 mr-1 flex items-center gap-1">
            <Download className="h-3.5 w-3.5" />
            <span>Export As:</span>
          </div>

          <button
            onClick={() => handleExport('csv')}
            disabled={exportingFormat !== null}
            className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-300 shadow-2xs transition-colors disabled:opacity-50"
          >
            <FileText className="h-3.5 w-3.5 text-emerald-600" />
            <span>{exportingFormat === 'csv' ? 'Generating...' : 'CSV (RFC 4180)'}</span>
          </button>

          <button
            onClick={() => handleExport('xlsx')}
            disabled={exportingFormat !== null}
            className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-blue-50 hover:bg-blue-100 text-blue-800 border border-blue-300 shadow-2xs transition-colors disabled:opacity-50"
          >
            <FileSpreadsheet className="h-3.5 w-3.5 text-blue-600" />
            <span>{exportingFormat === 'xlsx' ? 'Formatting...' : 'Excel (.xlsx)'}</span>
          </button>

          <button
            onClick={() => handleExport('json')}
            disabled={exportingFormat !== null}
            className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-purple-50 hover:bg-purple-100 text-purple-800 border border-purple-300 shadow-2xs transition-colors disabled:opacity-50"
          >
            <Code2 className="h-3.5 w-3.5 text-purple-600" />
            <span>{exportingFormat === 'json' ? 'Serializing...' : 'JSON'}</span>
          </button>
        </div>
      </div>

      {/* Notifications */}
      {notification && (
        <div
          className={`p-3 rounded-lg border text-xs flex items-center space-x-2 transition-all ${
            notification.type === 'success'
              ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
              : 'bg-rose-50 border-rose-200 text-rose-800'
          }`}
        >
          {notification.type === 'success' ? (
            <CheckCircle2 className="h-4 w-4 text-emerald-500 shrink-0" />
          ) : (
            <AlertCircle className="h-4 w-4 text-rose-500 shrink-0" />
          )}
          <span>{notification.message}</span>
        </div>
      )}

      {/* Real-Time Reconciliation Banner */}
      {reconciliation && (
        <ReconciliationBanner
          reconciliation={reconciliation}
          onAutoRecalculate={() => handleTransactionsChange(transactions)}
        />
      )}

      {/* Split-Pane Container */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 h-[720px]">
        {/* Left Pane: Document Viewer (5 cols) */}
        <div className="lg:col-span-5 h-full">
          <DocumentViewer
            filename={details?.filename || 'statement.pdf'}
            pageCount={1}
            highlightedRowId={selectedRowId}
          />
        </div>

        {/* Right Pane: Editable Transaction Grid (7 cols) */}
        <div className="lg:col-span-7 h-full">
          <TransactionTable
            transactions={transactions}
            onTransactionsChange={handleTransactionsChange}
            onSave={handleSave}
            isSaving={isSaving}
            onSelectRow={(id) => setSelectedRowId(id)}
            selectedRowId={selectedRowId}
          />
        </div>
      </div>
    </div>
  );
};
