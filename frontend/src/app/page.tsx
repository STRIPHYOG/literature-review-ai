'use client';

import React, { useState, useCallback, useRef, useEffect } from 'react';
import {
  createSession,
  uploadPapers,
  generateReview,
  getSessionStatus,
  getReview,
  getExportUrl,
  connectProgressWS,
  type SessionStatus,
  type ReviewResponse,
  type ProgressUpdate,
  type PaperSummary,
} from '@/lib/api';

// ─── Icon Components (inline to avoid dependency issues) ───

const UploadIcon = () => (
  <svg className="w-12 h-12" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
  </svg>
);

const FileIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
  </svg>
);

const XIcon = () => (
  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
  </svg>
);

const CheckIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
  </svg>
);

const DownloadIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
  </svg>
);

const SparkleIcon = () => (
  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 001.423 1.423l1.183.394-1.183.394a2.25 2.25 0 00-1.423 1.423z" />
  </svg>
);

// ─── Types ───

type AppStage = 'upload' | 'processing' | 'results';

// ─── Processing Stage Descriptions ───

const STAGE_INFO: Record<string, { label: string; icon: string }> = {
  pdf_extraction: { label: 'Extracting text from PDFs', icon: '📄' },
  metadata_extraction: { label: 'Analyzing scientific metadata', icon: '🔬' },
  chunking: { label: 'Segmenting documents', icon: '✂️' },
  embedding: { label: 'Generating vector embeddings', icon: '🧮' },
  claim_extraction: { label: 'Extracting scientific claims', icon: '🔍' },
  evidence_mapping: { label: 'Mapping evidence across papers', icon: '🔗' },
  review_generation: { label: 'Writing literature review', icon: '✍️' },
  verification: { label: 'Verifying citations', icon: '✅' },
  completed: { label: 'Complete!', icon: '🎉' },
  error: { label: 'Processing failed', icon: '❌' },
};

export default function Home() {
  // ─── State ───
  const [stage, setStage] = useState<AppStage>('upload');
  const [files, setFiles] = useState<File[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isUploading, setIsUploading] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [processingProgress, setProcessingProgress] = useState<ProgressUpdate | null>(null);
  const [review, setReview] = useState<ReviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [papers, setPapers] = useState<PaperSummary[]>([]);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [stepProgress, setStepProgress] = useState<Record<string, number>>({});
  const [isDragActive, setIsDragActive] = useState(false);
  const [activeTab, setActiveTab] = useState<'review' | 'comparison' | 'gaps' | 'evidence'>('review');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    let timer: NodeJS.Timeout;
    if (stage === 'processing') {
      timer = setInterval(() => {
        setElapsedSeconds((prev) => prev + 1);
      }, 1000);
    }
    return () => {
      if (timer) clearInterval(timer);
    };
  }, [stage]);

  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  };


  // ─── File Handling ───

  const handleFiles = useCallback((newFiles: FileList | File[]) => {
    const validFiles: File[] = [];
    const fileArray = Array.from(newFiles);

    for (const file of fileArray) {
      if (file.type !== 'application/pdf') {
        setError(`"${file.name}" is not a PDF file`);
        continue;
      }
      if (file.size > 50 * 1024 * 1024) {
        setError(`"${file.name}" exceeds 50MB limit`);
        continue;
      }
      validFiles.push(file);
    }

    const total = files.length + validFiles.length;
    if (total > 10) {
      setError('Maximum 10 PDFs per session');
      validFiles.splice(10 - files.length);
    }

    if (validFiles.length > 0) {
      setFiles((prev) => [...prev, ...validFiles]);
      setError(null);
    }
  }, [files]);

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  // ─── Drag & Drop ───

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragActive(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragActive(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragActive(false);
    if (e.dataTransfer.files) {
      handleFiles(e.dataTransfer.files);
    }
  }, [handleFiles]);

  // ─── Upload & Generate ───

  const handleGenerate = async () => {
    if (files.length === 0) {
      setError('Please upload at least 1 PDF');
      return;
    }

    setIsUploading(true);
    setError(null);

    try {
      // 1. Create session
      const session = await createSession();
      setSessionId(session.id);

      // 2. Upload files
      setUploadProgress(0);
      const uploadResult = await uploadPapers(
        session.id,
        files,
        (progress) => setUploadProgress(progress)
      );

      setUploadProgress(100);
      setIsUploading(false);
      setIsGenerating(true);
      setStage('processing');
      setProcessingProgress({
        session_id: session.id,
        stage: 'pdf_extraction',
        progress: 0.15,
        message: 'Extracting text and structure from research PDFs...',
      });

      // 3. Trigger generation
      await generateReview(session.id);

      // Start live polling immediately
      startPolling(session.id);

      // 4. Connect WebSocket for progress if available
      try {
        const ws = connectProgressWS(
          session.id,
          (data) => {
            setProcessingProgress(data);
            if (data.stage && data.progress !== undefined) {
              setStepProgress((prev) => ({
                ...prev,
                [data.stage]: data.progress,
              }));
            }
            if (data.stage === 'completed') {
              if (pollRef.current) clearInterval(pollRef.current);
              fetchReview(session.id);
            } else if (data.stage === 'error') {
              if (pollRef.current) clearInterval(pollRef.current);
              setError(data.message);
              setIsGenerating(false);
            }
          },
          () => {
            // WebSocket fallback handled by startPolling
          }
        );
        wsRef.current = ws;
      } catch {
        // Handled by polling
      }

    } catch (err: any) {
      setError(err.message || 'Something went wrong');
      setIsUploading(false);
      setIsGenerating(false);
    }
  };

  const startPolling = (sid: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const status = await getSessionStatus(sid);
        if (status.status === 'completed') {
          if (pollRef.current) clearInterval(pollRef.current);
          setProcessingProgress({
            session_id: sid,
            stage: 'completed',
            progress: 1.0,
            message: 'Literature review generation complete!',
          });
          setTimeout(() => fetchReview(sid), 800);
        } else if (status.status === 'failed') {
          if (pollRef.current) clearInterval(pollRef.current);
          setError('Processing failed. Please try again.');
          setIsGenerating(false);
        } else {
          setPapers(status.papers);
          if (status.jobs && status.jobs.length > 0) {
            const stages = Object.keys(STAGE_INFO).filter(k => k !== 'error' && k !== 'completed');
            const runningJob = status.jobs.find(j => j.status === 'running');
            const completedJobs = status.jobs.filter(j => j.status === 'completed');
            const latestJob = runningJob || status.jobs[status.jobs.length - 1];

            const jobProgressMap: Record<string, number> = {};
            status.jobs.forEach(j => {
              jobProgressMap[j.job_type] = j.status === 'completed' ? 1.0 : (j.progress !== null && j.progress !== undefined ? j.progress : 0.4);
            });
            setStepProgress(jobProgressMap);

            const calculatedProgress = Math.max(0.15, Math.min(0.96, (completedJobs.length + (runningJob?.progress || 0.4)) / stages.length));

            setProcessingProgress({
              session_id: sid,
              stage: latestJob.job_type,
              progress: calculatedProgress,
              message: STAGE_INFO[latestJob.job_type]?.label || `Processing: ${latestJob.job_type.replace(/_/g, ' ')}...`,
            });
          }

        }
      } catch {
        // Ignore polling network glitches
      }
    }, 1500);
  };


  const fetchReview = async (sid: string) => {
    try {
      const reviewData = await getReview(sid);
      setReview(reviewData);
      setStage('results');
      setIsGenerating(false);

      // Also get session for papers
      const status = await getSessionStatus(sid);
      setPapers(status.papers);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch review');
      setIsGenerating(false);
    }
  };

  // ─── Cleanup ───

  useEffect(() => {
    return () => {
      wsRef.current?.close();
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  // ─── Format Helpers ───

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  // ─── Render ───

  return (
    <div className="min-h-screen bg-surface-950 relative overflow-hidden">
      {/* Background gradient orbs */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-[-20%] left-[-10%] w-[500px] h-[500px] bg-brand-600/10 rounded-full blur-[120px] animate-pulse-slow" />
        <div className="absolute bottom-[-20%] right-[-10%] w-[600px] h-[600px] bg-purple-600/8 rounded-full blur-[140px] animate-pulse-slow" />
        <div className="absolute top-[40%] right-[20%] w-[300px] h-[300px] bg-indigo-500/5 rounded-full blur-[100px]" />
      </div>

      {/* Header */}
      <header className="relative z-10 border-b border-surface-800/50 bg-surface-950/80 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-500 to-purple-600 flex items-center justify-center">
              <SparkleIcon />
            </div>
            <div>
              <h1 className="text-lg font-bold font-display text-white">
                Research Assistant
              </h1>
              <p className="text-xs text-surface-400">Evidence-Aware Literature Analysis</p>
            </div>
          </div>

          {stage === 'results' && sessionId && (
            <div className="flex items-center gap-3">
              <a
                href={getExportUrl(sessionId, 'pdf')}
                className="btn-secondary text-sm gap-2"
                download
              >
                <DownloadIcon /> PDF
              </a>
              <a
                href={getExportUrl(sessionId, 'docx')}
                className="btn-secondary text-sm gap-2"
                download
              >
                <DownloadIcon /> DOCX
              </a>
            </div>
          )}
        </div>
      </header>

      {/* Main Content */}
      <main className="relative z-10 max-w-7xl mx-auto px-6 py-8">
        {/* ─── Upload Stage ─── */}
        {stage === 'upload' && (
          <div className="animate-fade-in space-y-8">
            {/* Hero */}
            <div className="text-center space-y-4 py-8">
              <h2 className="text-4xl md:text-5xl font-bold font-display gradient-text leading-tight">
                Transform Research Papers<br />Into Literature Reviews
              </h2>
              <p className="text-lg text-surface-400 max-w-2xl mx-auto">
                Upload up to 10 scientific PDFs and automatically generate a comprehensive,
                evidence-grounded literature review with verifiable citations.
              </p>
            </div>

            {/* Upload Zone */}
            <div className="max-w-3xl mx-auto">
              <div
                className={`upload-zone ${isDragActive ? 'active' : ''}`}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,application/pdf"
                  multiple
                  className="hidden"
                  onChange={(e) => e.target.files && handleFiles(e.target.files)}
                />

                <div className={`text-surface-400 transition-colors duration-300 ${isDragActive ? 'text-brand-400' : ''}`}>
                  <UploadIcon />
                </div>
                <p className="mt-4 text-lg font-medium text-surface-200">
                  {isDragActive ? 'Drop PDFs here' : 'Drag & drop PDFs here'}
                </p>
                <p className="mt-1 text-sm text-surface-500">
                  or <span className="text-brand-400 underline">browse files</span> · Max 10 files · 50MB each
                </p>
              </div>
            </div>

            {/* File List */}
            {files.length > 0 && (
              <div className="max-w-3xl mx-auto space-y-3 animate-slide-up">
                <div className="flex items-center justify-between px-1">
                  <p className="text-sm font-medium text-surface-300">
                    {files.length} file{files.length > 1 ? 's' : ''} selected
                  </p>
                  <button
                    onClick={() => setFiles([])}
                    className="text-xs text-surface-500 hover:text-red-400 transition-colors"
                  >
                    Clear all
                  </button>
                </div>

                {files.map((file, index) => (
                  <div
                    key={`${file.name}-${index}`}
                    className="glass-card px-4 py-3 flex items-center gap-3 animate-scale-in"
                  >
                    <div className="text-brand-400">
                      <FileIcon />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-surface-200 truncate">
                        {file.name}
                      </p>
                      <p className="text-xs text-surface-500">{formatFileSize(file.size)}</p>
                    </div>
                    <button
                      onClick={() => removeFile(index)}
                      className="p-1 text-surface-500 hover:text-red-400 transition-colors rounded-lg hover:bg-red-500/10"
                    >
                      <XIcon />
                    </button>
                  </div>
                ))}

                {/* Upload progress */}
                {isUploading && (
                  <div className="glass-card p-4 animate-slide-up">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-sm font-medium text-surface-300">Uploading...</span>
                      <span className="text-sm font-mono text-brand-400">{uploadProgress}%</span>
                    </div>
                    <div className="progress-bar">
                      <div
                        className="progress-bar-fill"
                        style={{ width: `${uploadProgress}%` }}
                      />
                    </div>
                  </div>
                )}

                {/* Generate Button */}
                <button
                  onClick={handleGenerate}
                  disabled={isUploading || files.length === 0}
                  className="btn-primary w-full text-lg py-4 gap-3"
                >
                  <SparkleIcon />
                  Generate Literature Review
                </button>
              </div>
            )}

            {/* Error */}
            {error && (
              <div className="max-w-3xl mx-auto glass-card border-red-500/30 bg-red-500/5 p-4 animate-slide-down">
                <p className="text-red-400 text-sm">{error}</p>
              </div>
            )}
          </div>
        )}

        {/* ─── Processing Stage ─── */}
        {stage === 'processing' && (() => {
          const totalFiles = files.length > 0 ? files.length : (papers.length > 0 ? papers.length : 1);
          const currentStageKey = processingProgress?.stage || 'pdf_extraction';
          const stages = Object.keys(STAGE_INFO).filter(k => k !== 'error');
          const currentIdx = stages.indexOf(currentStageKey);
          
          const rawStepProgress = stepProgress[currentStageKey];
          const activeStepRatio = rawStepProgress !== undefined ? rawStepProgress : 0.35;
          
          const isSynthesisStage = ['review_generation', 'verification', 'completed'].includes(currentStageKey);
          const currentFileIndex = isSynthesisStage 
            ? totalFiles 
            : Math.min(totalFiles, Math.max(1, Math.ceil(activeStepRatio * totalFiles)));
          const remainingFilesCount = Math.max(0, totalFiles - currentFileIndex);
          const currentFileName = isSynthesisStage
            ? `All ${totalFiles} papers processed · Synthesizing literature review`
            : (files[currentFileIndex - 1]?.name || papers[currentFileIndex - 1]?.filename || `Paper ${currentFileIndex} of ${totalFiles}`);

          const overallPct = Math.round((processingProgress?.progress || 0.15) * 100);
          const estTotalSeconds = elapsedSeconds > 3 && overallPct > 5 
            ? Math.round(elapsedSeconds / (overallPct / 100))
            : Math.max(35, totalFiles * 12);
          const estimatedRemainingSeconds = Math.max(3, estTotalSeconds - elapsedSeconds);

          return (
            <div className="animate-fade-in max-w-2xl mx-auto py-12 space-y-6">
              <div className="text-center space-y-2">
                <h2 className="text-3xl font-bold font-display text-white">
                  Analyzing Your Papers
                </h2>
                <p className="text-surface-400 text-sm">
                  Processing {totalFiles} scientific paper{totalFiles > 1 ? 's' : ''} through the evidence-aware pipeline
                </p>
              </div>

              {/* ─── Live File Tracker & Timer Status Card ─── */}
              <div className="glass-card p-4 grid grid-cols-1 sm:grid-cols-2 gap-4 border border-surface-700/60 bg-surface-900/70 backdrop-blur-xl shadow-xl">
                {/* File-level Activity Counter */}
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center text-emerald-400 text-lg shrink-0 shadow-inner">
                    📄
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-emerald-400 uppercase tracking-wider">
                        File {currentFileIndex} of {totalFiles}
                      </span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded font-medium bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
                        {remainingFilesCount} remaining
                      </span>
                    </div>
                    <p className="text-xs text-white truncate font-medium mt-0.5" title={currentFileName}>
                      {currentFileName}
                    </p>
                  </div>
                </div>

                {/* Live Elapsed & Estimated Timer */}
                <div className="flex items-center gap-3 sm:border-l sm:border-surface-800/80 sm:pl-4">
                  <div className="w-10 h-10 rounded-xl bg-purple-500/15 border border-purple-500/30 flex items-center justify-center text-purple-400 text-lg shrink-0 shadow-inner">
                    ⏱️
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-xs text-surface-400 flex items-center gap-1.5">
                      <span>Elapsed:</span>
                      <strong className="text-surface-200 font-mono font-medium">{formatTime(elapsedSeconds)}</strong>
                    </div>
                    <div className="text-xs text-surface-300 mt-0.5 flex items-center gap-1.5">
                      <span>Est. Remaining:</span>
                      <strong className="text-emerald-400 font-mono font-semibold">
                        ~{formatTime(estimatedRemainingSeconds)}
                      </strong>
                    </div>
                  </div>
                </div>
              </div>

              {/* ─── Pipeline Steps with Green Specific Progress Bars ─── */}
              <div className="glass-card p-6 space-y-4 border border-surface-800/80 shadow-2xl">
                <div className="space-y-3">
                  {Object.entries(STAGE_INFO).map(([key, info]) => {
                    if (key === 'error') return null;
                    const thisIdx = stages.indexOf(key);

                    let status: 'pending' | 'active' | 'done' = 'pending';
                    if (thisIdx < currentIdx || currentStageKey === 'completed') status = 'done';
                    else if (thisIdx === currentIdx) status = 'active';

                    // Compute specific step percentage
                    const explicitPct = stepProgress[key] !== undefined ? Math.round(stepProgress[key] * 100) : null;
                    const stepPercent = status === 'done' 
                      ? 100 
                      : status === 'active' 
                        ? (explicitPct !== null ? Math.max(10, Math.min(99, explicitPct)) : Math.max(15, Math.min(95, Math.round(activeStepRatio * 100))))
                        : 0;

                    return (
                      <div 
                        key={key} 
                        className={`p-3 rounded-xl transition-all duration-300 border ${
                          status === 'active' 
                            ? 'bg-surface-800/60 border-emerald-500/30 shadow-lg shadow-emerald-500/5' 
                            : status === 'done'
                              ? 'bg-surface-900/30 border-surface-800/40'
                              : 'bg-transparent border-transparent opacity-60'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="flex items-center gap-3 min-w-0">
                            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm shrink-0 transition-all duration-500 ${
                              status === 'done' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40' :
                              status === 'active' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/50 shadow-[0_0_12px_rgba(16,185,129,0.3)] animate-pulse' :
                              'bg-surface-800 text-surface-500 border border-surface-700/50'
                            }`}>
                              {status === 'done' ? <CheckIcon /> : info.icon}
                            </div>
                            <div className="min-w-0">
                              <p className={`text-sm font-semibold transition-colors duration-300 truncate ${
                                status === 'done' ? 'text-surface-300' :
                                status === 'active' ? 'text-white' :
                                'text-surface-500'
                              }`}>
                                {info.label}
                              </p>
                              {status === 'active' && (
                                <p className="text-xs text-emerald-400/90 font-medium mt-0.5 truncate animate-fade-in">
                                  {processingProgress?.message || `Processing ${currentFileName}...`}
                                </p>
                              )}
                            </div>
                          </div>

                          {/* Step Percentage Badge */}
                          <div className="shrink-0 text-right">
                            {status === 'done' && (
                              <span className="text-[11px] font-mono font-semibold px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                                100% Done
                              </span>
                            )}
                            {status === 'active' && (
                              <span className="text-[11px] font-mono font-bold px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-[0_0_10px_rgba(16,185,129,0.25)] animate-pulse">
                                {stepPercent}%
                              </span>
                            )}
                            {status === 'pending' && (
                              <span className="text-[11px] text-surface-600 font-medium">
                                Waiting
                              </span>
                            )}
                          </div>
                        </div>

                        {/* ─── Specific Step Progress Bar (Vibrant Green) ─── */}
                        {status === 'active' && (
                          <div className="mt-2.5 pt-1 space-y-1 animate-fade-in">
                            <div className="w-full bg-surface-950/80 h-2.5 rounded-full overflow-hidden border border-emerald-500/30 p-0.5 shadow-inner">
                              <div
                                className="h-full bg-gradient-to-r from-emerald-500 via-emerald-400 to-teal-300 rounded-full transition-all duration-500 shadow-[0_0_12px_rgba(16,185,129,0.5)]"
                                style={{ width: `${stepPercent}%` }}
                              />
                            </div>
                            <div className="flex justify-between items-center text-[10px] text-emerald-400/75 px-0.5">
                              <span>Step Progress: {stepPercent}%</span>
                              <span>{totalFiles - remainingFilesCount} of {totalFiles} papers processed</span>
                            </div>
                          </div>
                        )}

                        {/* Completed Step Indicator */}
                        {status === 'done' && (
                          <div className="mt-1.5 w-full bg-surface-950/40 h-1 rounded-full overflow-hidden">
                            <div className="h-full bg-emerald-500/40 rounded-full w-full" />
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>

                {/* ─── Overall Pipeline Progress Bar ─── */}
                <div className="pt-4 mt-2 border-t border-surface-800/80 space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-brand-300 flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-brand-400 animate-ping inline-block"></span>
                      Overall Pipeline Progress
                    </span>
                    <span className="font-mono text-brand-400 font-bold text-sm">
                      {overallPct}%
                    </span>
                  </div>
                  <div className="w-full bg-surface-950/90 h-3 rounded-full overflow-hidden border border-surface-700/50 p-0.5 shadow-inner">
                    <div
                      className="h-full bg-gradient-to-r from-brand-500 via-purple-500 to-indigo-500 transition-all duration-700 rounded-full shadow-lg shadow-brand-500/30"
                      style={{ width: `${Math.max(8, overallPct)}%` }}
                    />
                  </div>
                </div>

              </div>

              {error && (
                <div className="glass-card border-red-500/30 bg-red-500/5 p-4">
                  <p className="text-red-400 text-sm">{error}</p>
                </div>
              )}
            </div>
          );
        })()}

        {/* ─── Results Stage ─── */}
        {stage === 'results' && review && (
          <div className="animate-fade-in space-y-6">
            {/* Tab Navigation */}
            <div className="glass-card p-1.5 inline-flex gap-1">
              {[
                { key: 'review' as const, label: 'Literature Review', icon: '📝' },
                { key: 'comparison' as const, label: 'Comparison Table', icon: '📊' },
                { key: 'gaps' as const, label: 'Research Gaps', icon: '🔬' },
                { key: 'evidence' as const, label: 'Evidence Summary', icon: '🔗' },
              ].map(tab => (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  className={`px-4 py-2 rounded-xl text-sm font-medium transition-all duration-200 ${
                    activeTab === tab.key
                      ? 'bg-brand-600/20 text-brand-300 border border-brand-500/30'
                      : 'text-surface-400 hover:text-surface-200 hover:bg-surface-800/50'
                  }`}
                >
                  <span className="mr-1.5">{tab.icon}</span>
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Review Tab */}
            {activeTab === 'review' && (
              <div className="glass-card p-8 animate-slide-up">
                <div className="review-content prose prose-invert max-w-none">
                  <ReviewRenderer text={review.review_text} citations={review.citations} />
                </div>
              </div>
            )}

            {/* Comparison Table Tab */}
            {activeTab === 'comparison' && review.comparison_table && (
              <div className="glass-card p-6 overflow-x-auto animate-slide-up">
                <h3 className="text-xl font-semibold font-display text-white mb-4">
                  Paper Comparison Table
                </h3>
                <table className="w-full text-sm border-collapse">
                  <thead>
                    <tr className="border-b border-surface-700/50">
                      {['Title', 'Authors', 'Year', 'Methodology', 'Datasets', 'Metrics', 'Key Results', 'Limitations'].map(h => (
                        <th key={h} className="text-left p-3 text-brand-300 font-semibold text-xs uppercase tracking-wider">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {review.comparison_table.map((row, i) => (
                      <tr key={i} className="border-b border-surface-800/50 hover:bg-surface-800/30 transition-colors">
                        <td className="p-3 font-medium text-surface-200 max-w-[200px] truncate">{row.title}</td>
                        <td className="p-3 text-surface-400 max-w-[150px] truncate">
                          {Array.isArray(row.authors) ? row.authors.join(', ') : row.authors}
                        </td>
                        <td className="p-3 text-surface-400">{row.publication_year || 'N/A'}</td>
                        <td className="p-3 text-surface-400 max-w-[200px]">{truncate(row.methodology, 100)}</td>
                        <td className="p-3 text-surface-400 max-w-[150px]">
                          {Array.isArray(row.datasets) ? row.datasets.join(', ') : row.datasets}
                        </td>
                        <td className="p-3 text-surface-400 max-w-[150px]">
                          {Array.isArray(row.evaluation_metrics) ? row.evaluation_metrics.join(', ') : '—'}
                        </td>
                        <td className="p-3 text-surface-400 max-w-[200px]">{truncate(row.key_results, 100)}</td>
                        <td className="p-3 text-surface-400 max-w-[200px]">{truncate(row.limitations, 100)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Research Gaps Tab */}
            {activeTab === 'gaps' && review.research_gaps && (
              <div className="space-y-4 animate-slide-up">
                <h3 className="text-xl font-semibold font-display text-white">
                  Identified Research Gaps
                </h3>
                {review.research_gaps.map((gap, i) => (
                  <div key={i} className="glass-card-hover p-5 space-y-2">
                    <div className="flex items-start gap-3">
                      <span className={`badge ${
                        gap.severity === 'high' ? 'badge-error' :
                        gap.severity === 'medium' ? 'badge-warning' : 'badge-info'
                      }`}>
                        {gap.severity}
                      </span>
                      <div className="flex-1">
                        <p className="text-surface-200 font-medium">{gap.gap}</p>
                        <p className="text-sm text-surface-400 mt-1">{gap.evidence}</p>
                        {gap.suggested_direction && (
                          <div className="mt-3 pl-3 border-l-2 border-brand-500/30">
                            <p className="text-sm text-brand-300">
                              <strong>Suggested Direction:</strong> {gap.suggested_direction}
                            </p>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Evidence Summary Tab */}
            {activeTab === 'evidence' && review.evidence_summary && (
              <div className="space-y-6 animate-slide-up">
                <h3 className="text-xl font-semibold font-display text-white">
                  Evidence Relationship Summary
                </h3>

                {/* Stats */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  {[
                    { label: 'Total Links', value: review.evidence_summary.total_links || 0, color: 'text-white' },
                    { label: 'Supporting', value: review.evidence_summary.supporting || 0, color: 'text-emerald-400' },
                    { label: 'Contradicting', value: review.evidence_summary.contradicting || 0, color: 'text-red-400' },
                    { label: 'Extending', value: review.evidence_summary.extending || 0, color: 'text-amber-400' },
                  ].map(stat => (
                    <div key={stat.label} className="glass-card p-4 text-center">
                      <p className={`text-3xl font-bold font-display ${stat.color}`}>{stat.value}</p>
                      <p className="text-xs text-surface-400 mt-1">{stat.label}</p>
                    </div>
                  ))}
                </div>

                {/* Verification Results */}
                {review.generation_metadata?.verification && (
                  <div className="glass-card p-6 space-y-4">
                    <h4 className="text-lg font-semibold text-white">Citation Verification</h4>
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                      {Object.entries(review.generation_metadata.verification.summary || {}).map(([key, val]) => (
                        <div key={key} className="text-center p-3 rounded-xl bg-surface-800/50">
                          <p className="text-2xl font-bold text-white">{val as number}</p>
                          <p className="text-xs text-surface-400 capitalize mt-1">{key.replace('_', ' ')}</p>
                        </div>
                      ))}
                    </div>

                    <div className="flex items-center gap-4 pt-2">
                      <div className="flex-1">
                        <div className="flex justify-between text-xs mb-1">
                          <span className="text-surface-400">Verification Rate</span>
                          <span className="text-emerald-400 font-mono">
                            {Math.round((review.generation_metadata.verification.verification_rate || 0) * 100)}%
                          </span>
                        </div>
                        <div className="progress-bar">
                          <div
                            className="h-full bg-emerald-500 rounded-full transition-all"
                            style={{ width: `${(review.generation_metadata.verification.verification_rate || 0) * 100}%` }}
                          />
                        </div>
                      </div>
                      <div className="flex-1">
                        <div className="flex justify-between text-xs mb-1">
                          <span className="text-surface-400">Hallucination Rate</span>
                          <span className="text-red-400 font-mono">
                            {Math.round((review.generation_metadata.verification.hallucination_rate || 0) * 100)}%
                          </span>
                        </div>
                        <div className="progress-bar">
                          <div
                            className="h-full bg-red-500 rounded-full transition-all"
                            style={{ width: `${(review.generation_metadata.verification.hallucination_rate || 0) * 100}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* References */}
            {review.citations && review.citations.length > 0 && (
              <div className="glass-card p-6 animate-slide-up">
                <h3 className="text-lg font-semibold font-display text-white mb-4">References</h3>
                <div className="space-y-2">
                  {review.citations.map((cite) => (
                    <p key={cite.index} className="text-sm text-surface-400 pl-6 -indent-6">
                      {cite.formatted}
                    </p>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="relative z-10 border-t border-surface-800/50 mt-16 py-6">
        <p className="text-center text-xs text-surface-600">
          Evidence-Aware AI Research Assistant · Powered by Hugging Face (Llama 3.3 70B), FastAPI & Next.js
        </p>
      </footer>
    </div>
  );
}

// ─── Sub-Components ───

function ReviewRenderer({ text, citations }: { text: string; citations: any[] | null }) {
  // Process the review text to render markdown-style content with citations
  const lines = text.split('\n');

  return (
    <div>
      {lines.map((line, i) => {
        const trimmed = line.trim();
        if (!trimmed) return <br key={i} />;

        if (trimmed.startsWith('## ')) {
          return <h2 key={i}>{trimmed.slice(3)}</h2>;
        }
        if (trimmed.startsWith('# ')) {
          return <h1 key={i}>{trimmed.slice(2)}</h1>;
        }
        if (trimmed.startsWith('### ')) {
          return <h3 key={i}>{trimmed.slice(4)}</h3>;
        }
        if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
          return <li key={i} className="ml-4">{renderCitations(trimmed.slice(2), citations)}</li>;
        }

        return <p key={i}>{renderCitations(trimmed, citations)}</p>;
      })}
    </div>
  );
}

function renderCitations(text: string, citations: any[] | null): React.ReactNode {
  // Replace [Paper N] with styled citation links
  const parts = text.split(/(\[Paper \d+(?:\s*,\s*\d+)*\])/g);

  return parts.map((part, i) => {
    const match = part.match(/\[Paper (\d+(?:\s*,\s*\d+)*)\]/);
    if (match) {
      return (
        <span
          key={i}
          className="citation-link"
          title={getCitationTooltip(match[1], citations)}
        >
          {part}
        </span>
      );
    }
    return <React.Fragment key={i}>{part}</React.Fragment>;
  });
}

function getCitationTooltip(indices: string, citations: any[] | null): string {
  if (!citations) return '';
  const nums = indices.split(',').map(s => parseInt(s.trim()));
  return nums
    .map(n => {
      const cite = citations.find(c => c.index === n);
      return cite ? cite.formatted : `[Paper ${n}]`;
    })
    .join('\n');
}

function truncate(text: string | null | undefined, max: number): string {
  if (!text) return '—';
  return text.length > max ? text.slice(0, max) + '...' : text;
}
