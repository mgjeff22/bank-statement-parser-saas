export type TransactionType = 'debit' | 'credit';

export type AnomalyType = 'SIGN_INVERSION' | 'MISSING_GAP' | 'OUT_OF_ORDER_DATE' | 'TRANSPOSITION';

export interface User {
  id: string;
  email: string;
  tenant_id: string;
  subscription_tier: 'free' | 'starter' | 'pro';
  created_at: string;
}

export interface QuotaStatus {
  allowed: boolean;
  tier: 'free' | 'starter' | 'pro';
  pages_used: number;
  monthly_limit: number;
  remaining_pages: number;
}

export interface StatementMetadata {
  bank_name: string;
  account_number: string;
  statement_period_start: string;
  statement_period_end: string;
  starting_balance: string;
  ending_balance: string;
  currency: string;
  page_count: number;
}

export interface TransactionRecord {
  id: string;
  date: string;
  payee: string;
  type: TransactionType;
  amount: string;
  category: string;
  running_balance: string;
  has_anomaly?: boolean;
  anomaly_type?: AnomalyType | null;
  raw_description?: string | null;
}

export interface ReconciliationSummary {
  starting_balance: string;
  total_credits: string;
  total_debits: string;
  net_cashflow: string;
  calculated_ending_balance: string;
  reported_ending_balance: string;
  discrepancy: string;
  is_reconciled: boolean;
  diagnostic_flags: string[];
}

export interface StatementHistoryItem {
  id: string;
  statement_id?: string;
  filename: string;
  file_path?: string;
  status: 'queued' | 'processing' | 'completed' | 'error';
  page_count: number;
  bank_name?: string | null;
  statement_period_start?: string | null;
  statement_period_end?: string | null;
  starting_balance?: string | null;
  ending_balance?: string | null;
  total_credits?: string | null;
  total_debits?: string | null;
  net_cashflow?: string | null;
  discrepancy?: string | null;
  is_reconciled?: boolean | null;
  error_message?: string | null;
  created_at: string;
}

export interface StatementDetails {
  statement_id: string;
  filename: string;
  starting_balance: string;
  ending_balance: string;
  reconciliation: ReconciliationSummary;
  transactions: TransactionRecord[];
}
