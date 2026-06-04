const API_BASE = '/api';

export interface InterviewSessionSummary {
  id: string;
  domain: string;
  difficulty: string;
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

export async function createSession(domain: string, difficulty: string, jobDescription: string = '', profileCompany: string = '', profilePosition: string = ''): Promise<string> {
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
    }),
  });
  if (res.status === 401) {
    throw new Error('UNAUTHORIZED');
  }
  const data = await res.json();
  return data.session_id;
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

export function streamChat(
  sessionId: string,
  message: string,
  onToken: (text: string) => void,
  onDone: () => void,
): AbortController {
  const controller = new AbortController();
  fetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    headers: authHeaders(),
    credentials: 'same-origin',
    body: JSON.stringify({ session_id: sessionId, message }),
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
