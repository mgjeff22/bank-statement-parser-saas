import React, { useState } from 'react';
import {
  ZoomIn,
  ZoomOut,
  Maximize2,
  RotateCw,
  ChevronLeft,
  ChevronRight,
  FileText,
  Search,
  Layers,
} from 'lucide-react';

interface DocumentViewerProps {
  filename: string;
  pageCount?: number;
  highlightedRowId?: string | null;
}

export const DocumentViewer: React.FC<DocumentViewerProps> = ({
  filename,
  pageCount = 1,
  highlightedRowId,
}) => {
  const [currentPage, setCurrentPage] = useState(1);
  const [zoom, setZoom] = useState(100);
  const [rotation, setRotation] = useState(0);

  const totalPages = Math.max(1, pageCount);

  const handleZoomIn = () => setZoom((z) => Math.min(200, z + 25));
  const handleZoomOut = () => setZoom((z) => Math.max(50, z - 25));
  const handleFitWidth = () => setZoom(100);
  const handleRotate = () => setRotation((r) => (r + 90) % 360);

  const handlePrevPage = () => setCurrentPage((p) => Math.max(1, p - 1));
  const handleNextPage = () => setCurrentPage((p) => Math.min(totalPages, p + 1));

  return (
    <div className="flex flex-col h-full bg-slate-900 rounded-xl overflow-hidden border border-slate-700 shadow-sm text-slate-200">
      {/* Document Controls Toolbar */}
      <div className="bg-slate-800/90 px-4 py-2.5 border-b border-slate-700 flex flex-wrap items-center justify-between gap-2 shrink-0">
        <div className="flex items-center space-x-2 text-xs font-medium text-slate-300">
          <FileText className="h-4 w-4 text-indigo-400" />
          <span className="truncate max-w-[140px] sm:max-w-[200px]" title={filename}>
            {filename}
          </span>
        </div>

        {/* Page Nav */}
        <div className="flex items-center space-x-1.5 bg-slate-700/60 px-2 py-1 rounded-lg border border-slate-600 text-xs">
          <button
            onClick={handlePrevPage}
            disabled={currentPage <= 1}
            className="p-1 hover:bg-slate-600 rounded disabled:opacity-30 disabled:hover:bg-transparent"
            title="Previous Page"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </button>
          <span>
            Page {currentPage} of {totalPages}
          </span>
          <button
            onClick={handleNextPage}
            disabled={currentPage >= totalPages}
            className="p-1 hover:bg-slate-600 rounded disabled:opacity-30 disabled:hover:bg-transparent"
            title="Next Page"
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Zoom & View Controls */}
        <div className="flex items-center space-x-1 text-slate-300">
          <button
            onClick={handleZoomOut}
            className="p-1.5 hover:bg-slate-700 rounded-lg transition-colors"
            title="Zoom Out"
          >
            <ZoomOut className="h-4 w-4" />
          </button>
          <span className="text-xs font-mono w-11 text-center">{zoom}%</span>
          <button
            onClick={handleZoomIn}
            className="p-1.5 hover:bg-slate-700 rounded-lg transition-colors"
            title="Zoom In"
          >
            <ZoomIn className="h-4 w-4" />
          </button>
          <button
            onClick={handleFitWidth}
            className="p-1.5 hover:bg-slate-700 rounded-lg transition-colors ml-1"
            title="Fit to Width"
          >
            <Maximize2 className="h-4 w-4" />
          </button>
          <button
            onClick={handleRotate}
            className="p-1.5 hover:bg-slate-700 rounded-lg transition-colors"
            title="Rotate 90°"
          >
            <RotateCw className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Document View Canvas Area */}
      <div className="flex-1 overflow-auto p-4 flex items-center justify-center bg-slate-950/70 relative">
        <div
          className="transition-transform duration-200 shadow-2xl bg-white text-slate-900 rounded-sm relative origin-center"
          style={{
            transform: `scale(${zoom / 100}) rotate(${rotation}deg)`,
            width: '595px',
            minHeight: '842px',
          }}
        >
          {/* Simulated Bank Statement Page Visualizer */}
          <div className="p-8 space-y-6 text-[11px] leading-relaxed">
            {/* Header */}
            <div className="border-b-2 border-slate-900 pb-4 flex justify-between items-start">
              <div>
                <div className="text-lg font-black tracking-wider text-slate-900 uppercase">
                  Commercial Bank Statement
                </div>
                <div className="text-slate-500 font-medium">Page {currentPage} of {totalPages}</div>
              </div>
              <div className="text-right text-slate-600">
                <div className="font-semibold text-slate-900">Document Audit Scan</div>
                <div>300 DPI High-Resolution</div>
                <div className="text-[10px] text-indigo-600 font-mono">ONNX CPU / RapidOCR</div>
              </div>
            </div>

            {/* Highlighting badge when row selected */}
            {highlightedRowId && (
              <div className="p-2 bg-indigo-50 border border-indigo-200 rounded text-indigo-900 text-xs flex items-center gap-2 animate-bounce">
                <Layers className="h-4 w-4 text-indigo-600" />
                <span>Synchronized with active row: <strong className="font-mono">{highlightedRowId}</strong></span>
              </div>
            )}

            {/* Statement Grid Preview */}
            <div className="space-y-2">
              <div className="font-bold text-xs uppercase text-slate-700 tracking-wider">
                Transaction Activity Stream
              </div>
              <div className="border border-slate-300 rounded overflow-hidden">
                <div className="bg-slate-100 font-bold px-3 py-1.5 flex justify-between border-b border-slate-300 text-[10px] text-slate-600">
                  <span className="w-16">Date</span>
                  <span className="flex-1">Description</span>
                  <span className="w-16 text-right">Debit</span>
                  <span className="w-16 text-right">Credit</span>
                  <span className="w-20 text-right">Balance</span>
                </div>

                <div className="divide-y divide-slate-200 text-[10px] font-mono">
                  <div className="px-3 py-1.5 flex justify-between hover:bg-indigo-50/50">
                    <span className="w-16">2026-08-01</span>
                    <span className="flex-1 font-sans">STARTING BALANCE CARRIED FORWARD</span>
                    <span className="w-16 text-right">-</span>
                    <span className="w-16 text-right">-</span>
                    <span className="w-20 text-right font-bold">$1,000.00</span>
                  </div>
                  <div className="px-3 py-1.5 flex justify-between hover:bg-indigo-50/50">
                    <span className="w-16">2026-08-02</span>
                    <span className="flex-1 font-sans">CLIENT ACH INBOUND SETTLEMENT</span>
                    <span className="w-16 text-right">-</span>
                    <span className="w-16 text-right text-emerald-600 font-bold">$2,000.00</span>
                    <span className="w-20 text-right font-bold">$3,000.00</span>
                  </div>
                  <div className="px-3 py-1.5 flex justify-between hover:bg-indigo-50/50">
                    <span className="w-16">2026-08-05</span>
                    <span className="flex-1 font-sans">OFFICE SUPPLIES DIRECT DEBIT</span>
                    <span className="w-16 text-right text-rose-600 font-bold">$149.25</span>
                    <span className="w-16 text-right">-</span>
                    <span className="w-20 text-right font-bold">$2,850.75</span>
                  </div>
                  <div className="px-3 py-1.5 flex justify-between hover:bg-indigo-50/50">
                    <span className="w-16">2026-08-10</span>
                    <span className="flex-1 font-sans">CLOUD SERVER HOSTING AUTO-RENEW</span>
                    <span className="w-16 text-right text-rose-600 font-bold">$100.00</span>
                    <span className="w-16 text-right">-</span>
                    <span className="w-20 text-right font-bold">$2,750.75</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Reconciliation Footnote */}
            <div className="border-t border-slate-200 pt-4 text-[10px] text-slate-500 flex justify-between">
              <div>Bank Reference: CHK-88921-992</div>
              <div>Reported Ending Balance: Verified</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
