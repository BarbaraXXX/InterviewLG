const API_BASE = '/api';
interface UserScopedRequest<T> {
  epoch: number;
  promise: Promise<T>;
}

interface UserScopedCache<T> {
  epoch: number;
  value: T;
  expiresAt: number;
}

let userAuthEpoch = 0;
const interviewSessionListRequests = new Map<number, UserScopedRequest<InterviewSessionSummary[]>>();
let authCheckRequest: Promise<{ username: string } | null> | null = null;
let adminAuthCheckRequest: Promise<{ username: string } | null> | null = null;
let domainsRequest: Promise<string[]> | null = null;
let profilesRequest: UserScopedRequest<ProfileSummary[]> | null = null;
let resumesRequest: UserScopedRequest<Resume[]> | null = null;
let domainsCache: { value: string[]; expiresAt: number } | null = null;
let profilesCache: UserScopedCache<ProfileSummary[]> | null = null;
let resumesCache: UserScopedCache<Resume[]> | null = null;

const DOMAIN_CACHE_TTL_MS = 5 * 60 * 1000;
const SETUP_RESOURCE_CACHE_TTL_MS = 15 * 1000;

function invalidateResumeCache(): void {
  resumesCache = null;
  resumesRequest = null;
}

export function resetUserScopedApiState(): void {
  userAuthEpoch += 1;
  interviewSessionListRequests.clear();
  profilesCache = null;
  profilesRequest = null;
  resumesCache = null;
  resumesRequest = null;
}

export interface InterviewSessionSummary {
  id: string;
  domain: string;
  difficulty: string;
  resume_title_snapshot: string;
  status: string;
  created_at: string;
  ended_at: string | null;
  message_count: number;
}

export interface InterviewMessage {
  role: 'user' | 'ai';
  content: string;
  seq: number;
  created_at: string;
}

export interface InterviewSessionDetail {
  session: Omit<InterviewSessionSummary, 'message_count'>;
  messages: InterviewMessage[];
  coding_tasks: CodingTask[];
  blueprint: InterviewBlueprint | null;
  progress: InterviewProgress | null;
}

export type QuestionTier = 'compact' | 'standard' | 'deep';
export type InterviewIntensity = 'guided' | 'standard' | 'pressure';

export interface InterviewBlueprint {
  schema_version: number;
  question_tier: QuestionTier;
  intensity: InterviewIntensity;
  focus_areas: string[];
  question_budget: number;
  include_coding: boolean;
  stage_budgets: {
    opening: number;
    project: number;
    technical: number;
    coding: number;
  };
}

export interface InterviewProgress {
  stage: string;
  stage_label: string;
  answered_questions: number;
  question_budget: number;
  remaining_questions: number;
  percent: number;
  include_coding: boolean;
  is_complete?: boolean;
}

export interface InterviewPlanState {
  blueprint: InterviewBlueprint | null;
  progress: InterviewProgress | null;
}

export interface ContextUsageSection {
  key: string;
  label: string;
  tokens: number;
  ratio: number;
}

export interface ContextUsage {
  total_tokens: number;
  input_budget_tokens: number;
  context_window_tokens: number;
  output_reserve_tokens: number;
  ratio: number;
  status: 'normal' | 'warning' | 'critical';
  tokenizer: string;
  is_estimate: boolean;
  sections: ContextUsageSection[];
}

export interface CodingTaskExample {
  input: string;
  output: string;
  explanation?: string;
}

export interface CodingTask {
  id: string;
  session_id: string;
  title: string;
  description: string;
  language: string;
  starter_code: string;
  starter_code_map: Record<string, string>;
  constraints: string[];
  examples: CodingTaskExample[];
  draft_language: string | null;
  draft_code: string | null;
  submitted_language: string | null;
  submitted_code: string | null;
  revision_instruction: string;
  revision_count: number;
  source_problem_id: string;
  source_problem_title: string;
  status: 'active' | 'submitted';
  created_at: string;
  submitted_at: string | null;
}

export interface ResumeProject {
  name: string;
  description: string;
}

export interface Resume {
  id: number;
  title: string;
  projects: ResumeProject[];
  skills: string;
  created_at: string;
  updated_at: string;
}

export interface LastInterviewConfig {
  domain: string;
  difficulty: string;
  job_description: string;
  profile_company: string;
  profile_position: string;
  resume_id: number | null;
  question_tier?: QuestionTier;
  intensity?: InterviewIntensity;
  focus_areas?: string[];
  updated_at: string;
}

export interface SpeechTranscriptionResult {
  text: string;
  duration_ms: number | null;
}

export interface QuestionRationale {
  stage: string;
  topic: string;
  question_kind: string;
  trigger: string;
  objective: string;
  expected_signal: string[];
  next_question_summary: string;
}

export interface ProfileSummary {
  key: string;
  company: string;
  position: string;
  source_count: number;
}

export interface AdminOverview {
  online_users: number;
  recent_users: number;
  active_sessions: number;
  paused_sessions: number;
  today: Record<string, number>;
}

export interface AdminPresenceUser {
  user_id: number;
  username: string;
  current_view: string;
  active_session_id: string;
  last_seen_at: string;
  updated_at: string;
  status: 'online' | 'recent';
}

export interface AdminDailyUsage {
  date: string;
  metrics: Record<string, number>;
}

function authHeaders(): Record<string, string> {
  return { 'Content-Type': 'application/json' };
}

export async function register(username: string, password: string, inviteCode: string): Promise<{ username: string }> {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify({ username, password, invite_code: inviteCode }),
  });
  if (!res.ok) {
    const data = await res.json();
    throw new Error(data.detail || 'Registration failed');
  }
  return res.json();
}

export async function login(username: string, password: string): Promise<{ username: string }> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const data = await res.json();
    throw new Error(data.detail || 'Login failed');
  }
  return res.json();
}

export async function getMe(): Promise<{ username: string } | null> {
  if (authCheckRequest) return authCheckRequest;
  authCheckRequest = fetch(`${API_BASE}/auth/me`, {
    credentials: 'same-origin',
  }).then((res) => {
    if (res.status === 401) return null;
    if (!res.ok) throw new Error(`Auth check failed: ${res.status}`);
    return res.json();
  }).finally(() => {
    authCheckRequest = null;
  });
  return authCheckRequest;
}

export async function logout(): Promise<void> {
  const res = await fetch(`${API_BASE}/auth/logout`, {
    method: 'POST',
    credentials: 'same-origin',
  });
  if (!res.ok) {
    throw new Error(`Logout failed: ${res.status}`);
  }
}

export async function adminLogin(username: string, password: string): Promise<{ username: string }> {
  const res = await fetch(`${API_BASE}/admin/auth/login`, {
    method: 'POST',
    headers: authHeaders(),
    credentials: 'same-origin',
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || 'Admin login failed');
  }
  return res.json();
}

export async function adminLogout(): Promise<void> {
  const res = await fetch(`${API_BASE}/admin/auth/logout`, {
    method: 'POST',
    credentials: 'same-origin',
  });
  if (!res.ok) {
    throw new Error(`Admin logout failed: ${res.status}`);
  }
}

export async function getAdminMe(): Promise<{ username: string } | null> {
  if (adminAuthCheckRequest) return adminAuthCheckRequest;
  adminAuthCheckRequest = fetch(`${API_BASE}/admin/auth/me`, {
    credentials: 'same-origin',
  }).then((res) => {
    if (res.status === 401 || res.status === 403) return null;
    if (!res.ok) throw new Error(`Admin auth check failed: ${res.status}`);
    return res.json();
  }).finally(() => {
    adminAuthCheckRequest = null;
  });
  return adminAuthCheckRequest;
}

export async function sendPresenceHeartbeat(currentView: string, activeSessionId: string = ''): Promise<void> {
  const res = await fetch(`${API_BASE}/presence/heartbeat`, {
    method: 'POST',
    headers: authHeaders(),
    credentials: 'same-origin',
    body: JSON.stringify({ current_view: currentView, active_session_id: activeSessionId }),
  });
  if (res.status === 401) throw new Error('UNAUTHORIZED');
  if (!res.ok) throw new Error(`Presence heartbeat failed: ${res.status}`);
}

export async function fetchAdminOverview(): Promise<AdminOverview> {
  const res = await fetch(`${API_BASE}/admin/metrics/overview`, {
    credentials: 'same-origin',
  });
  if (res.status === 401 || res.status === 403) throw new Error('ADMIN_UNAUTHORIZED');
  if (!res.ok) throw new Error('Failed to fetch admin overview');
  return res.json();
}

export async function fetchAdminPresence(): Promise<AdminPresenceUser[]> {
  const res = await fetch(`${API_BASE}/admin/presence`, {
    credentials: 'same-origin',
  });
  if (res.status === 401 || res.status === 403) throw new Error('ADMIN_UNAUTHORIZED');
  if (!res.ok) throw new Error('Failed to fetch admin presence');
  const data = await res.json();
  return data.users || [];
}

export async function fetchAdminDailyUsage(days: number = 7): Promise<AdminDailyUsage[]> {
  const res = await fetch(`${API_BASE}/admin/usage/daily?days=${days}`, {
    credentials: 'same-origin',
  });
  if (res.status === 401 || res.status === 403) throw new Error('ADMIN_UNAUTHORIZED');
  if (!res.ok) throw new Error('Failed to fetch admin usage');
  const data = await res.json();
  return data.days || [];
}

export async function fetchDomains(): Promise<string[]> {
  if (domainsCache && domainsCache.expiresAt > Date.now()) return domainsCache.value;
  if (domainsRequest) return domainsRequest;
  domainsRequest = fetch(`${API_BASE}/domains`)
    .then(async (res) => {
      if (!res.ok) throw new Error(`Failed to fetch domains: ${res.status}`);
      const data = await res.json();
      const value = data.presets || [];
      domainsCache = { value, expiresAt: Date.now() + DOMAIN_CACHE_TTL_MS };
      return value;
    })
    .finally(() => {
      domainsRequest = null;
    });
  return domainsRequest;
}

export async function fetchProfiles(): Promise<ProfileSummary[]> {
  const requestEpoch = userAuthEpoch;
  if (profilesCache && profilesCache.epoch === requestEpoch && profilesCache.expiresAt > Date.now()) {
    return profilesCache.value;
  }
  if (profilesRequest?.epoch === requestEpoch) return profilesRequest.promise;
  const promise = fetch(`${API_BASE}/profiles`, {
    headers: authHeaders(),
    credentials: 'same-origin',
  })
    .then(async (res) => {
      if (res.status === 401) throw new Error('UNAUTHORIZED');
      if (!res.ok) throw new Error(`Failed to fetch profiles: ${res.status}`);
      const data = await res.json();
      const value = data.profiles || [];
      if (requestEpoch === userAuthEpoch) {
        profilesCache = { epoch: requestEpoch, value, expiresAt: Date.now() + SETUP_RESOURCE_CACHE_TTL_MS };
      }
      return value;
    })
    .finally(() => {
      if (profilesRequest?.epoch === requestEpoch) {
        profilesRequest = null;
      }
    });
  profilesRequest = { epoch: requestEpoch, promise };
  return promise;
}

export async function fetchResumes(): Promise<Resume[]> {
  const requestEpoch = userAuthEpoch;
  if (resumesCache && resumesCache.epoch === requestEpoch && resumesCache.expiresAt > Date.now()) {
    return resumesCache.value;
  }
  if (resumesRequest?.epoch === requestEpoch) return resumesRequest.promise;
  const promise = fetch(`${API_BASE}/resumes`, {
    headers: authHeaders(),
    credentials: 'same-origin',
  })
    .then(async (res) => {
      if (res.status === 401) {
        throw new Error('UNAUTHORIZED');
      }
      if (!res.ok) {
        throw new Error(`Failed to fetch resumes: ${res.status}`);
      }
      const data = await res.json();
      const value = data.resumes || [];
      if (requestEpoch === userAuthEpoch) {
        resumesCache = { epoch: requestEpoch, value, expiresAt: Date.now() + SETUP_RESOURCE_CACHE_TTL_MS };
      }
      return value;
    })
    .finally(() => {
      if (resumesRequest?.epoch === requestEpoch) {
        resumesRequest = null;
      }
    });
  resumesRequest = { epoch: requestEpoch, promise };
  return promise;
}

export async function fetchLastInterviewConfig(): Promise<LastInterviewConfig | null> {
  const res = await fetch(`${API_BASE}/interview-config/last`, {
    headers: authHeaders(),
    credentials: 'same-origin',
  });
  if (res.status === 401) {
    throw new Error('UNAUTHORIZED');
  }
  if (!res.ok) {
    throw new Error('Failed to fetch last interview config');
  }
  const data = await res.json();
  return data.config || null;
}

export async function createResume(title: string, projects: ResumeProject[], skills: string): Promise<Resume> {
  const res = await fetch(`${API_BASE}/resumes`, {
    method: 'POST',
    headers: authHeaders(),
    credentials: 'same-origin',
    body: JSON.stringify({ title, projects, skills }),
  });
  if (res.status === 401) {
    throw new Error('UNAUTHORIZED');
  }
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || 'Failed to create resume');
  }
  invalidateResumeCache();
  return data.resume;
}

export async function updateResume(resumeId: number, title: string, projects: ResumeProject[], skills: string): Promise<Resume> {
  const res = await fetch(`${API_BASE}/resumes/${resumeId}`, {
    method: 'PUT',
    headers: authHeaders(),
    credentials: 'same-origin',
    body: JSON.stringify({ title, projects, skills }),
  });
  if (res.status === 401) {
    throw new Error('UNAUTHORIZED');
  }
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || 'Failed to update resume');
  }
  invalidateResumeCache();
  return data.resume;
}

export async function deleteResume(resumeId: number): Promise<void> {
  const res = await fetch(`${API_BASE}/resumes/${resumeId}`, {
    method: 'DELETE',
    headers: authHeaders(),
    credentials: 'same-origin',
  });
  if (res.status === 401) {
    throw new Error('UNAUTHORIZED');
  }
  if (!res.ok) {
    throw new Error('Failed to delete resume');
  }
  invalidateResumeCache();
}

export async function createSession(
  domain: string,
  difficulty: string,
  jobDescription: string = '',
  profileCompany: string = '',
  profilePosition: string = '',
  resumeId: number | null = null,
  questionTier: QuestionTier = 'standard',
  intensity: InterviewIntensity = 'standard',
  focusAreas: string[] = [],
): Promise<{
  sessionId: string;
  messages: InterviewMessage[];
  blueprint: InterviewBlueprint;
  progress: InterviewProgress;
}> {
  const res = await fetch(`${API_BASE}/sessions`, {
    method: 'POST',
    headers: authHeaders(),
    credentials: 'same-origin',
    body: JSON.stringify({
      domain,
      difficulty,
      job_description: jobDescription,
      profile_company: profileCompany,
      profile_position: profilePosition,
      resume_id: resumeId,
      question_tier: questionTier,
      intensity,
      focus_areas: focusAreas,
    }),
  });
  if (res.status === 401) {
    throw new Error('UNAUTHORIZED');
  }
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || 'Failed to create interview session');
  }
  return {
    sessionId: data.session_id,
    messages: data.messages || [],
    blueprint: data.blueprint,
    progress: data.progress,
  };
}

export async function fetchInterviewSessions(limit: number = 50): Promise<InterviewSessionSummary[]> {
  const requestEpoch = userAuthEpoch;
  const existingRequest = interviewSessionListRequests.get(limit);
  if (existingRequest?.epoch === requestEpoch) return existingRequest.promise;

  const request = fetch(`${API_BASE}/sessions?limit=${limit}`, {
    headers: authHeaders(),
    credentials: 'same-origin',
  })
    .then(async (res) => {
      if (res.status === 401) {
        throw new Error('UNAUTHORIZED');
      }
      if (!res.ok) {
        throw new Error('Failed to fetch interview sessions');
      }
      const data = await res.json();
      return data.sessions || [];
    })
    .finally(() => {
      if (interviewSessionListRequests.get(limit)?.epoch === requestEpoch) {
        interviewSessionListRequests.delete(limit);
      }
    });

  interviewSessionListRequests.set(limit, { epoch: requestEpoch, promise: request });
  return request;
}

export async function fetchInterviewSessionDetail(sessionId: string): Promise<InterviewSessionDetail> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}`, {
    headers: authHeaders(),
    credentials: 'same-origin',
  });
  if (res.status === 401) {
    throw new Error('UNAUTHORIZED');
  }
  if (!res.ok) {
    throw new Error('Failed to fetch interview session');
  }
  return res.json();
}

export async function fetchInterviewProgress(sessionId: string): Promise<InterviewPlanState> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/progress`, {
    headers: authHeaders(),
    credentials: 'same-origin',
  });
  if (res.status === 401) {
    throw new Error('UNAUTHORIZED');
  }
  if (!res.ok) {
    throw new Error('Failed to fetch interview progress');
  }
  return res.json();
}

export async function fetchContextUsage(sessionId: string): Promise<ContextUsage> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/context-usage`, {
    headers: authHeaders(),
    credentials: 'same-origin',
  });
  if (res.status === 401) {
    throw new Error('UNAUTHORIZED');
  }
  if (!res.ok) {
    throw new Error('Failed to fetch context usage');
  }
  return res.json();
}

export async function fetchActiveCodingTask(sessionId: string): Promise<CodingTask | null> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/coding-task/active`, {
    headers: authHeaders(),
    credentials: 'same-origin',
  });
  if (res.status === 401) {
    throw new Error('UNAUTHORIZED');
  }
  if (!res.ok) {
    throw new Error('Failed to fetch coding task');
  }
  const data = await res.json();
  return data.task || null;
}

export async function submitCodingTask(taskId: string, language: string, code: string): Promise<{ task: CodingTask; contextMessage: string }> {
  const res = await fetch(`${API_BASE}/coding-tasks/${taskId}/submit`, {
    method: 'POST',
    headers: authHeaders(),
    credentials: 'same-origin',
    body: JSON.stringify({ language, code }),
  });
  if (res.status === 401) {
    throw new Error('UNAUTHORIZED');
  }
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || 'Failed to submit coding task');
  }
  return { task: data.task, contextMessage: data.context_message };
}

export async function saveCodingTaskDraft(taskId: string, language: string, code: string): Promise<CodingTask> {
  const res = await fetch(`${API_BASE}/coding-tasks/${taskId}/draft`, {
    method: 'PUT',
    headers: authHeaders(),
    credentials: 'same-origin',
    body: JSON.stringify({ language, code }),
  });
  if (res.status === 401) {
    throw new Error('UNAUTHORIZED');
  }
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || 'Failed to save coding task draft');
  }
  return data.task;
}

const SESSION_ACTION_RETRY_DELAYS_MS = [75, 200];

async function postSessionAction(
  path: string,
  { allowNotFound = false }: { allowNotFound?: boolean } = {},
): Promise<void> {
  for (let attempt = 0; ; attempt += 1) {
    const res = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: authHeaders(),
      credentials: 'same-origin',
    });
    if (res.status === 401) {
      throw new Error('UNAUTHORIZED');
    }
    if (res.status === 409 && attempt < SESSION_ACTION_RETRY_DELAYS_MS.length) {
      await new Promise((resolve) => globalThis.setTimeout(resolve, SESSION_ACTION_RETRY_DELAYS_MS[attempt]));
      continue;
    }
    if (res.ok || (allowNotFound && res.status === 404)) {
      return;
    }
    throw new Error(`Session action failed: ${res.status}`);
  }
}

export async function endInterviewSession(sessionId: string): Promise<void> {
  await postSessionAction(`/sessions/${sessionId}/end`, { allowNotFound: true });
}

export async function pauseInterviewSession(sessionId: string): Promise<void> {
  await postSessionAction(`/sessions/${sessionId}/pause`);
}

export async function resumeInterviewSession(sessionId: string): Promise<InterviewSessionDetail> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/resume`, {
    method: 'POST',
    headers: authHeaders(),
    credentials: 'same-origin',
  });
  if (res.status === 401) {
    throw new Error('UNAUTHORIZED');
  }
  if (!res.ok) {
    throw new Error('Failed to resume interview session');
  }
  return res.json();
}

export async function deleteInterviewSession(sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}`, {
    method: 'DELETE',
    headers: authHeaders(),
    credentials: 'same-origin',
  });
  if (res.status === 401) {
    throw new Error('UNAUTHORIZED');
  }
  if (!res.ok) {
    throw new Error('Failed to delete interview session');
  }
}

export async function deleteInterviewSessions(sessionIds: string[]): Promise<number> {
  const res = await fetch(`${API_BASE}/sessions`, {
    method: 'DELETE',
    headers: authHeaders(),
    credentials: 'same-origin',
    body: JSON.stringify({ session_ids: sessionIds }),
  });
  if (res.status === 401) {
    throw new Error('UNAUTHORIZED');
  }
  if (!res.ok) {
    throw new Error('Failed to delete interview sessions');
  }
  const data = await res.json();
  return data.deleted || 0;
}

export async function transcribeSpeech(audio: Blob, durationMs: number): Promise<SpeechTranscriptionResult> {
  const form = new FormData();
  const extension = audio.type.includes('mp4') ? 'm4a' : 'webm';
  form.append('audio', audio, `speech.${extension}`);
  form.append('duration_ms', String(Math.max(0, Math.round(durationMs))));

  const res = await fetch(`${API_BASE}/speech/transcribe`, {
    method: 'POST',
    credentials: 'same-origin',
    body: form,
  });
  if (res.status === 401) {
    throw new Error('UNAUTHORIZED');
  }
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail || 'Speech transcription failed');
  }
  return res.json();
}

export function streamChat(
  sessionId: string,
  message: string,
  onToken: (text: string) => void,
  onDone: () => void,
  contextMessage: string = '',
  onError?: (err: Error) => void,
  debugRationale: boolean = false,
  onQuestionRationale?: (rationale: QuestionRationale) => void,
): AbortController {
  const controller = new AbortController();
  fetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    headers: authHeaders(),
    credentials: 'same-origin',
    body: JSON.stringify({
      session_id: sessionId,
      message,
      context_message: contextMessage,
      debug_rationale: debugRationale,
    }),
    signal: controller.signal,
  }).then(async (res) => {
    if (res.status === 401) {
      onError?.(new Error('UNAUTHORIZED'));
      return;
    }
    if (!res.ok || !res.body) {
      onError?.(new Error(`Chat stream failed: ${res.status}`));
      return;
    }
    const reader = res.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const event = JSON.parse(line.slice(6));
          if (event.type === 'token') onToken(event.content);
          else if (event.type === 'done') onDone();
          else if (event.type === 'question_rationale') onQuestionRationale?.(event.content);
        }
      }
    }
  }).catch((err) => {
    if (err instanceof Error && err.name === 'AbortError') return;
    onError?.(err instanceof Error ? err : new Error('Chat stream failed'));
  });
  return controller;
}
