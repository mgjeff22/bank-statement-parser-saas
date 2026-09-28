import React, { useState, useRef } from 'react';
import { UploadCloud, File, AlertCircle, Loader2, CheckCircle2 } from 'lucide-react';
import { QuotaStatus } from '../../types';
import { api } from '../../api/client';

interface UploadZoneProps {
  quota: QuotaStatus | null;
  onUploadSuccess: (statementId: string) => void;
  onQuotaExceeded: () => void;
}

export const UploadZone: React.FC<UploadZoneProps> = ({ quota, onUploadSuccess, onQuotaExceeded }) => {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const isQuotaBlocked = quota !== null && quota.remaining_pages <= 0;

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    if (!isQuotaBlocked) setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const processFile = async (file: File) => {
    if (isQuotaBlocked) {
      onQuotaExceeded();
      return;
    }

    // Validate type
    const validTypes = ['application/pdf', 'image/png', 'image/jpeg', 'image/webp'];
    const isPdf = file.name.toLowerCase().endsWith('.pdf');
    const isImage = file.name.toLowerCase().match(/\.(png|jpg|jpeg|webp)$/);

    if (!validTypes.includes(file.type) && !isPdf && !isImage) {
      setError('Unsupported file type. Please upload a PDF, PNG, JPEG, or WebP document.');
      return;
    }

    // Pre-flight check
    if (file.size > 25 * 1024 * 1024) {
      setError('File size exceeds 25MB limit.');
      return;
    }

    setError(null);
    setIsUploading(true);
    setUploadStatus('Uploading document & running multimodal extraction...');

    try {
      const res = await api.uploadStatement(file, file.name);
      setUploadStatus('Parsed & mathematically reconciled!');
      setTimeout(() => {
        setIsUploading(false);
        setUploadStatus(null);
        if (res.statement_id) {
          onUploadSuccess(res.statement_id);
        }
      }, 700);
    } catch (err: any) {
      setIsUploading(false);
      setUploadStatus(null);
      if (err.message && err.message.includes('QUOTA_EXCEEDED')) {
        onQuotaExceeded();
      } else {
        setError(err.message || 'Failed to process statement. Please try again.');
      }
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      processFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      processFile(e.target.files[0]);
    }
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-xs p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-base font-semibold text-slate-900">Upload Bank Statement</h3>
          <p className="text-xs text-slate-500">
            Accepts digital PDFs, 300 DPI scanned documents, PNG, JPEG, or WebP statements
          </p>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-rose-50 border border-rose-200 rounded-lg flex items-center space-x-2 text-rose-800 text-sm">
          <AlertCircle className="h-4 w-4 text-rose-500 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => !isUploading && !isQuotaBlocked && fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all duration-200 ${
          isQuotaBlocked
            ? 'border-slate-200 bg-slate-50 cursor-not-allowed opacity-75'
            : isDragging
            ? 'border-indigo-500 bg-indigo-50/60 scale-[1.01]'
            : 'border-slate-300 hover:border-slate-400 bg-slate-50/50 hover:bg-slate-50'
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,.webp"
          className="hidden"
          onChange={handleFileSelect}
          disabled={isUploading || isQuotaBlocked}
        />

        {isUploading ? (
          <div className="flex flex-col items-center justify-center space-y-3 py-4">
            <Loader2 className="h-10 w-10 text-indigo-600 animate-spin" />
            <div className="text-sm font-semibold text-slate-800">{uploadStatus}</div>
            <p className="text-xs text-slate-500">Extracting tables, dates, amounts & calculating running balances</p>
          </div>
        ) : isQuotaBlocked ? (
          <div className="flex flex-col items-center justify-center space-y-2 py-4 text-amber-700">
            <AlertCircle className="h-10 w-10 text-amber-500" />
            <div className="text-sm font-semibold">Monthly Quota Exceeded</div>
            <p className="text-xs text-slate-500 max-w-sm">
              You have exhausted your allotted pages for this billing cycle. Please upgrade your subscription tier to continue uploading.
            </p>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center space-y-3 py-4">
            <div className="h-12 w-12 rounded-full bg-indigo-50 text-indigo-600 flex items-center justify-center">
              <UploadCloud className="h-6 w-6" />
            </div>
            <div>
              <span className="text-sm font-semibold text-indigo-600 hover:text-indigo-700">
                Click to upload
              </span>{' '}
              <span className="text-sm text-slate-600">or drag and drop your statement</span>
            </div>
            <p className="text-xs text-slate-400">PDF, PNG, JPG, or WebP up to 25MB</p>
          </div>
        )}
      </div>
    </div>
  );
};
