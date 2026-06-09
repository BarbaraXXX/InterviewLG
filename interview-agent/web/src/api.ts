const API_BASE = '/api';

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
  updated_at: string;
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
  const res = await fetch(`${API_BASE}/auth/me`, {
    credentials: 'same-origin',
  });
  if (!res.ok) return null;
  return res.json();
}

export async function logout(): Promise<void> {
  await fetch(`${API_BASE}/auth/logout`, {
    method: 'POST',
    credentials: 'same-origin',
  });
}

export async function fetchDomains(): Promise<string[]> {
  const res = await fetch(`${API_BASE}/domains`);
  const data = await res.json();
  return data.presets;
}

export async function fetchProfiles(): Promise<{key: string; company: string; position: string; source_count: number}[]> {
  const res = await fetch(`${API_BASE}/profiles`, {
    headers: authHeaders(),
    credentials: 'same-origin',
  });
  if (!res.ok) return [];
  const data = await res.json();
  return data.profiles || [];
}

export async function fetchResumes(): Promise<Resume[]> {
  const res = await fetch(`${API_BASE}/resumes`, {
    headers: authHeaders(),
    credentials: 'same-origin',
  });
  if (res.status === 401) {
    throw new Error('UNAUTHORIZED');
  }
  if (!res.ok) {
    throw new Error('Failed to fetch resumes');
  }
  const data = await res.json();
  return data.resumes || [];
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
}

export async function createSession(
  domain: string,
  difficulty: string,
  jobDescription: string = '',
  profileCompany: string = '',
  profilePosition: string = '',
  resumeId: number | null = null,
): Promise<{ sessionId: string; messages: InterviewMessage[] }> {
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
    }),
  });
  if (res.status === 401) {
    throw new Error('UNAUTHORIZED');
  }
  const data = await res.json();
  return {
    sessionId: data.session_id,
    messages: data.messages || [],
  };
}

export async function fetchInterviewSessions(limit: number = 50): Promise<InterviewSessionSummary[]> {
  const res = await fetch(`${API_BASE}/sessions?limit=${limit}`, {
    headers: authHeaders(),
    credentials: 'same-origin',
  });
  if (res.status === 401) {
    throw new Error('UNAUTHORIZED');
  }
  if (!res.ok) {
    throw new Error('Failed to fetch interview sessions');
  }
  const data = await res.json();
  return data.sessions || [];
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

export async function endInterviewSession(sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/end`, {
    method: 'POST',
    headers: authHeaders(),
    credentials: 'same-origin',
  });
  if (res.status === 401) {
    throw new Error('UNAUTHORIZED');
  }
  if (!res.ok && res.status !== 404) {
    throw new Error('Failed to end interview session');
  }
}

export async function pauseInterviewSession(sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/pause`, {
    method: 'POST',
    headers: authHeaders(),
    credentials: 'same-origin',
  });
  if (res.status === 401) {
    throw new Error('UNAUTHORIZED');
  }
  if (!res.ok) {
    throw new Error('Failed to pause interview session');
  }
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

export function streamChat(
  sessionId: string,
  message: string,
  onToken: (text: string) => void,
  onDone: () => void,
  contextMessage: string = '',
): AbortController {
  const controller = new AbortController();
  fetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    headers: authHeaders(),
    credentials: 'same-origin',
    body: JSON.stringify({ session_id: sessionId, message, context_message: contextMessage }),
    signal: controller.signal,
  }).then(async (res) => {
    if (res.status === 401) {
      onDone();
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
        }
      }
    }
  });
  return controller;
}
