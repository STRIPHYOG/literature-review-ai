/**
 * API client for communicating with the FastAPI backend.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'https://literature-review-ai-d13l.onrender.com';
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'wss://literature-review-ai-d13l.onrender.com';


export interface SessionResponse {
  id: string;
  status: string;
  paper_count: number;
  created_at: string;
}

export interface SessionStatus {
  id: string;
  status: string;
  paper_count: number;
  created_at: string;
  papers: PaperSummary[];
  jobs: JobStatus[];
}

export interface PaperSummary {
  id: string;
  filename: string;
  title: string | null;
  authors: string[] | null;
  publication_year: number | null;
  abstract: string | null;
  page_count: number | null;
  processing_status: string;
  file_size_bytes: number | null;
}

export interface JobStatus {
  id: string;
  job_type: string;
  status: string;
  progress: number;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface UploadResponse {
  session_id: string;
  uploaded_files: string[];
  total_files: number;
  message: string;
}

export interface ReviewResponse {
  id: string;
  session_id: string;
  review_text: string;
  comparison_table: ComparisonRow[] | null;
  evidence_summary: Record<string, any> | null;
  research_gaps: ResearchGap[] | null;
  citations: Citation[] | null;
  generation_metadata: Record<string, any> | null;
  created_at: string;
}

export interface ComparisonRow {
  paper_id: string;
  title: string;
  authors: string[];
  publication_year: number | null;
  methodology: string;
  datasets: string[];
  evaluation_metrics: string[];
  key_results: string;
  limitations: string;
}

export interface ResearchGap {
  gap: string;
  evidence: string;
  severity: string;
  suggested_direction: string;
}

export interface Citation {
  index: number;
  paper_id: string;
  label: string;
  title: string;
  authors: string;
  year: number | null;
  formatted: string;
}

export interface EvidenceDetail {
  claim_id: string;
  claim_text: string;
  claim_type: string | null;
  source_paper_title: string | null;
  source_paper_id: string;
  evidence_chunks: EvidenceChunk[];
}

export interface EvidenceChunk {
  chunk_id: string;
  content: string;
  section_name: string | null;
  page_number: number | null;
  paper_title: string | null;
  paper_id: string;
  relationship_type: string;
  similarity_score: number | null;
}

export interface ProgressUpdate {
  session_id: string;
  stage: string;
  progress: number;
  message: string;
  details?: Record<string, any>;
}

// ─── API Functions ───

async function fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${endpoint}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `API error: ${res.status}`);
  }

  return res.json();
}

export async function createSession(): Promise<SessionResponse> {
  return fetchAPI('/api/sessions', { method: 'POST' });
}

export async function getSessionStatus(sessionId: string): Promise<SessionStatus> {
  return fetchAPI(`/api/sessions/${sessionId}`);
}

export async function uploadPapers(
  sessionId: string,
  files: File[],
  onProgress?: (progress: number) => void
): Promise<UploadResponse> {
  const formData = new FormData();
  files.forEach((file) => formData.append('files', file));

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_URL}/api/sessions/${sessionId}/papers`);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        try {
          const err = JSON.parse(xhr.responseText);
          reject(new Error(err.detail || `Upload failed: ${xhr.status}`));
        } catch {
          reject(new Error(`Upload failed: ${xhr.status}`));
        }
      }
    };

    xhr.onerror = () => reject(new Error('Upload failed: network error'));
    xhr.send(formData);
  });
}

export async function generateReview(sessionId: string): Promise<any> {
  return fetchAPI(`/api/sessions/${sessionId}/generate`, { method: 'POST' });
}

export async function getReview(sessionId: string): Promise<ReviewResponse> {
  return fetchAPI(`/api/sessions/${sessionId}/review`);
}

export async function getComparisonTable(sessionId: string): Promise<any> {
  return fetchAPI(`/api/sessions/${sessionId}/comparison`);
}

export async function getEvidenceForClaim(
  sessionId: string,
  claimId: string
): Promise<EvidenceDetail> {
  return fetchAPI(`/api/sessions/${sessionId}/evidence/${claimId}`);
}

export function getExportUrl(sessionId: string, format: 'pdf' | 'docx'): string {
  return `${API_URL}/api/sessions/${sessionId}/export/${format}`;
}

// ─── WebSocket Connection ───

export function connectProgressWS(
  sessionId: string,
  onMessage: (data: ProgressUpdate) => void,
  onError?: (err: Event) => void
): WebSocket {
  const ws = new WebSocket(`${WS_URL}/ws/sessions/${sessionId}/progress`);

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      onMessage(data);
    } catch (e) {
      console.error('WebSocket parse error:', e);
    }
  };

  ws.onerror = (err) => {
    console.error('WebSocket error:', err);
    onError?.(err);
  };

  ws.onclose = () => {
    console.log('WebSocket closed for session:', sessionId);
  };

  return ws;
}
