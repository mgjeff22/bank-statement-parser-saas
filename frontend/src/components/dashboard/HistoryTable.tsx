import React, { useState } from 'react';
import { StatementHistoryItem } from '../../types';
import {
  FileText,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Trash2,
  ExternalLink,
  ChevronRight,
  Calendar,
  Building,
} from 'lucide-react';

interface HistoryTableProps {
  statements: StatementHistoryItem[];
  loading: boolean;
  onOpenWorkspace: (statementId: string) => void;
  onDeleteStatement: (statementId: string) => void;
}

export const HistoryTable: React.FC<HistoryTableProps> = ({
  statements,
  loading,
  onOpenWorkspace,
  onDeleteStatement,
}) => {
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'completed':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle2 className="h-3 w-3 text-emerald-500" />
            Completed
          </span>
        );
      case 'processing':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200 animate-pulse">
            <Clock className="h-3 w-3 text-blue-500" />
            Processing
          </span>
        );
      case 'error':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-50 text-rose-700 border border-rose-200">
            <AlertTriangle className="h-3 w-3 text-rose-500" />
            Error
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-50 text-slate-700 border border-slate-200">
            Queued
          </span>
        );
    }
  };

  const getReconciliationBadge = (item: StatementHistoryItem) => {
    if (item.status !== 'completed') return null;

    if (item.is_reconciled) {
      return (
        <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 border border-emerald-200">
          <CheckCircle2 className="h-3 w-3 text-emerald-600" />
          Balanced ($0.00)
        </span>
      );
    } else if (item.discrepancy) {
      return (
        <span className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded bg-rose-100 text-rose-800 border border-rose-200">
          <AlertTriangle className="h-3 w-3 text-rose-600" />
          Discrepancy: ${item.discrepancy}
        </span>
      );
    }
    return null;
  };

  const handleDelete = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (window.confirm('Are you sure you want to delete this statement and its extracted data?')) {
      setDeletingId(id);
      onDeleteStatement(id);
    }
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
      <div className="p-6 border-b border-slate-200 flex justify-between items-center">
        <div>
          <h3 className="text-base font-semibold text-slate-900">Statement Processing History</h3>
          <p className="text-xs text-slate-500">
            Review parsed statement batches, reconciliation states, and launch workspace inspection
          </p>
        </div>
        <span className="text-xs text-slate-500 bg-slate-100 px-2.5 py-1 rounded-full font-medium">
          {statements.length} document{statements.length !== 1 ? 's' : ''}
        </span>
      </div>

      {loading ? (
        <div className="p-8 text-center text-slate-400">Loading statement history...</div>
      ) : statements.length === 0 ? (
        <div className="p-12 text-center">
          <FileText className="h-12 w-12 text-slate-300 mx-auto mb-3" />
          <p className="text-sm font-medium text-slate-700">No statements uploaded yet</p>
          <p className="text-xs text-slate-400 mt-1">
            Upload your first bank statement using the drag-and-drop zone above
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-600">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500 font-semibold border-b border-slate-200">
              <tr>
                <th className="py-3.5 px-4">Statement File</th>
                <th className="py-3.5 px-4">Bank & Period</th>
                <th className="py-3.5 px-4">Pages</th>
                <th className="py-3.5 px-4">Reconciliation</th>
                <th className="py-3.5 px-4">Status</th>
                <th className="py-3.5 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {statements.map((stmt) => {
                const sId = stmt.id || stmt.statement_id || '';
                return (
                  <tr
                    key={sId}
                    onClick={() => onOpenWorkspace(sId)}
                    className="hover:bg-slate-50/80 transition-colors cursor-pointer group"
                  >
                    {/* Filename & Upload Date */}
                    <td className="py-4 px-4 font-medium text-slate-900">
                      <div className="flex items-center space-x-3">
                        <div className="h-9 w-9 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                          <FileText className="h-5 w-5" />
                        </div>
                        <div>
                          <div className="font-semibold text-slate-900 group-hover:text-indigo-600 transition-colors">
                            {stmt.filename}
                          </div>
                          <div className="text-xs text-slate-400">
                            {new Date(stmt.created_at).toLocaleDateString()} at{' '}
                            {new Date(stmt.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </div>
                        </div>
                      </div>
                    </td>

                    {/* Bank & Period */}
                    <td className="py-4 px-4 text-xs">
                      {stmt.bank_name ? (
                        <div className="space-y-0.5">
                          <div className="font-medium text-slate-800 flex items-center gap-1">
                            <Building className="h-3 w-3 text-slate-400" />
                            {stmt.bank_name}
                          </div>
                          {stmt.statement_period_start && stmt.statement_period_end && (
                            <div className="text-slate-500 flex items-center gap-1">
                              <Calendar className="h-3 w-3 text-slate-400" />
                              {stmt.statement_period_start} → {stmt.statement_period_end}
                            </div>
                          )}
                        </div>
                      ) : (
                        <span className="text-slate-400 italic">Processing metadata...</span>
                      )}
                    </td>

                    {/* Page Count */}
                    <td className="py-4 px-4 text-xs font-medium text-slate-700">
                      {stmt.page_count} pg{stmt.page_count !== 1 ? 's' : ''}
                    </td>

                    {/* Reconciliation */}
                    <td className="py-4 px-4">{getReconciliationBadge(stmt)}</td>

                    {/* Status */}
                    <td className="py-4 px-4">{getStatusBadge(stmt.status)}</td>

                    {/* Actions */}
                    <td className="py-4 px-4 text-right">
                      <div className="flex items-center justify-end space-x-2">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onOpenWorkspace(sId);
                          }}
                          className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold rounded-lg bg-indigo-50 text-indigo-700 hover:bg-indigo-100 transition-colors"
                        >
                          <span>Workspace</span>
                          <ChevronRight className="h-3.5 w-3.5" />
                        </button>

                        <button
                          onClick={(e) => handleDelete(sId, e)}
                          title="Delete statement"
                          className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
