import {
  User,
  QuotaStatus,
  StatementHistoryItem,
  StatementDetails,
  TransactionRecord,
  ReconciliationSummary,
} from '../types';

const API_BASE = '/api';

class ApiClient {
  private token: string | null = null;

  constructor() {
    this.token = localStorage.getItem('auth_token');
  }

  setToken(token: string | null) {
    this.token = token;
    if (token) {
      localStorage.setItem('auth_token', token);
    } else {
      localStorage.removeItem('auth_token');
    }
  }

  getToken(): string | null {
    return this.token;
  }

  private async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string>),
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    if (!(options.body instanceof FormData) && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }

    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      let errMessage = 'An unexpected error occurred';
      try {
        const errorData = await response.json();
        errMessage = errorData.detail || errorData.message || JSON.stringify(errorData);
      } catch {
        errMessage = `HTTP error ${response.status}: ${response.statusText}`;
      }
      throw new Error(errMessage);
    }

    return response.json();
  }

  // ---------------- Auth ----------------
  async login(email: string, password: string): Promise<{ access_token: string; user: User }> {
    const data = await this.request<{ access_token: string; user: User }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
    this.setToken(data.access_token);
    return data;
  }

  async register(email: string, password: string, tier: string = 'free'): Promise<{ access_token: string; user: User }> {
    const data = await this.request<{ access_token: string; user: User }>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ email, password, tier }),
    });
    this.setToken(data.access_token);
    return data;
  }

  async getCurrentUser(): Promise<User> {
    return this.request<User>('/auth/me');
  }

  logout() {
    this.setToken(null);
  }

  // ---------------- Quota & Dashboard ----------------
  async getQuota(): Promise<QuotaStatus> {
    return this.request<QuotaStatus>('/dashboard/quota');
  }

  async getDashboardStats(): Promise<any> {
    return this.request<any>('/dashboard/stats');
  }

  // ---------------- Statements & Uploads ----------------
  async getStatementsHistory(): Promise<StatementHistoryItem[]> {
    return this.request<StatementHistoryItem[]>('/statements/history');
  }

  async uploadStatement(file: File, filename?: string): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);
    if (filename) {
      formData.append('filename', filename);
    }

    return this.request<any>('/statements/upload', {
      method: 'POST',
      body: formData,
    });
  }

  async deleteStatement(statementId: string): Promise<{ success: boolean }> {
    return this.request<{ success: boolean }>(`/statements/${statementId}`, {
      method: 'DELETE',
    });
  }

  // ---------------- Transactions & Workspace ----------------
  async getStatementTransactions(statementId: string): Promise<StatementDetails> {
    return this.request<StatementDetails>(`/statements/${statementId}/transactions`);
  }

  async updateTransactions(
    statementId: string,
    transactions: TransactionRecord[],
    startingBalance?: string,
    endingBalance?: string,
  ): Promise<{ success: boolean; reconciliation: ReconciliationSummary; transactions: TransactionRecord[] }> {
    return this.request<any>(`/statements/${statementId}/transactions`, {
      method: 'PUT',
      body: JSON.stringify({
        transactions,
        starting_balance: startingBalance,
        ending_balance: endingBalance,
      }),
    });
  }

  async reconcileStatement(statementId: string): Promise<ReconciliationSummary> {
    return this.request<ReconciliationSummary>(`/statements/${statementId}/reconcile`, {
      method: 'POST',
    });
  }

  async directReconcile(
    startingBalance: string,
    reportedEndingBalance: string,
    transactions: TransactionRecord[],
  ): Promise<ReconciliationSummary> {
    return this.request<ReconciliationSummary>('/statements/reconcile', {
      method: 'POST',
      body: JSON.stringify({
        starting_balance: startingBalance,
        reported_ending_balance: reportedEndingBalance,
        transactions,
      }),
    });
  }

  // ---------------- Exporter Downloads ----------------
  async downloadExport(statementId: string, format: 'csv' | 'xlsx' | 'json', filename: string = 'export') {
    const headers: Record<string, string> = {};
    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    const response = await fetch(`${API_BASE}/export/${statementId}/${format}`, {
      headers,
    });

    if (!response.ok) {
      throw new Error(`Export download failed with status ${response.status}`);
    }

    const blob = await response.blob();
    const downloadUrl = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = downloadUrl;
    a.download = `${filename}.${format}`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(downloadUrl);
    document.body.removeChild(a);
  }

  // ---------------- Billing & Stripe ----------------
  async createCheckoutSession(tier: string, interval: 'month' | 'year' = 'month'): Promise<{ checkout_url: string }> {
    return this.request<{ checkout_url: string }>('/billing/checkout', {
      method: 'POST',
      body: JSON.stringify({ tier, interval }),
    });
  }

  async getPortalUrl(): Promise<{ portal_url: string }> {
    return this.request<{ portal_url: string }>('/billing/portal', {
      method: 'POST',
    });
  }

  async mockUpgrade(tier: string): Promise<any> {
    return this.request<any>('/billing/mock/upgrade', {
      method: 'POST',
      body: JSON.stringify({ tier }),
    });
  }

  async triggerMockWebhook(eventType: string, data: any): Promise<any> {
    return this.request<any>('/billing/mock/webhook', {
      method: 'POST',
      body: JSON.stringify({ event_type: eventType, data }),
    });
  }
}

export const api = new ApiClient();
