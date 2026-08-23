import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createSession,
  endInterviewSession,
  fetchDomains,
  fetchInterviewProgress,
  fetchInterviewSessions,
  fetchProfiles,
  fetchResumes,
  getAdminMe,
  getMe,
  logout,
  pauseInterviewSession,
  resetUserScopedApiState,
  sendPresenceHeartbeat,
  streamChat,
} from './api.ts';

test('retries pause and end actions while a cancelled stream releases its turn lock', async () => {
  const originalFetch = globalThis.fetch;
  const attempts = new Map<string, number>();
  globalThis.fetch = (async (input) => {
    const url = String(input);
    const count = (attempts.get(url) || 0) + 1;
    attempts.set(url, count);
    return new Response(count === 1 ? 'busy' : '{}', {
      status: count === 1 ? 409 : 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }) as typeof fetch;

  try {
    await pauseInterviewSession('session-1');
    await endInterviewSession('session-1');
    assert.equal(attempts.get('/api/sessions/session-1/pause'), 2);
    assert.equal(attempts.get('/api/sessions/session-1/end'), 2);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('creates a session with the selected interview blueprint options', async () => {
  const originalFetch = globalThis.fetch;
  let requestUrl = '';
  let requestBody: Record<string, unknown> = {};
  const blueprint = {
    schema_version: 1,
    question_tier: 'standard',
    intensity: 'pressure',
    focus_areas: ['project_depth', 'system_design'],
    question_budget: 10,
    include_coding: true,
    stage_budgets: { opening: 1, project: 3, technical: 4, coding: 2 },
  };
  const progress = {
    stage: 'opening',
    stage_label: '开场',
    answered_questions: 0,
    question_budget: 10,
    remaining_questions: 10,
    percent: 0,
    include_coding: true,
  };

  globalThis.fetch = (async (input, init) => {
    requestUrl = String(input);
    requestBody = JSON.parse(String(init?.body || '{}'));
    return new Response(JSON.stringify({
      session_id: 'session-1',
      messages: [{ role: 'ai', content: '你好', seq: 1, created_at: '2026-08-23T00:00:00Z' }],
      blueprint,
      progress,
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }) as typeof fetch;

  try {
    const result = await createSession(
      'backend',
      'campus_fulltime',
      'JD',
      'A',
      'B',
      7,
      'standard',
      'pressure',
      ['project_depth', 'system_design'],
    );

    assert.equal(requestUrl, '/api/sessions');
    assert.equal(requestBody.question_tier, 'standard');
    assert.equal(requestBody.intensity, 'pressure');
    assert.deepEqual(requestBody.focus_areas, ['project_depth', 'system_design']);
    assert.equal(result.sessionId, 'session-1');
    assert.deepEqual(result.blueprint, blueprint);
    assert.deepEqual(result.progress, progress);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('fetches the latest interview blueprint and progress', async () => {
  const originalFetch = globalThis.fetch;
  let requestUrl = '';
  const response = {
    blueprint: {
      schema_version: 1,
      question_tier: 'compact',
      intensity: 'guided',
      focus_areas: [],
      question_budget: 6,
      include_coding: false,
      stage_budgets: { opening: 1, project: 2, technical: 3, coding: 0 },
    },
    progress: {
      stage: 'technical',
      stage_label: '技术基础',
      answered_questions: 3,
      question_budget: 6,
      remaining_questions: 3,
      percent: 50,
      include_coding: false,
    },
  };

  globalThis.fetch = (async (input) => {
    requestUrl = String(input);
    return new Response(JSON.stringify(response), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    });
  }) as typeof fetch;

  try {
    const result = await fetchInterviewProgress('session-1');
    assert.equal(requestUrl, '/api/sessions/session-1/progress');
    assert.deepEqual(result, response);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('coalesces concurrent interview session list requests by limit', async () => {
  const originalFetch = globalThis.fetch;
  const resolveResponses: Array<(value: Response) => void> = [];
  let fetchCount = 0;

  globalThis.fetch = (() => {
    fetchCount += 1;
    return new Promise<Response>((resolve) => {
      resolveResponses.push(resolve);
    });
  }) as typeof fetch;

  try {
    const first = fetchInterviewSessions(100);
    const second = fetchInterviewSessions(100);

    for (const resolve of resolveResponses) {
      resolve(
        new Response(JSON.stringify({ sessions: [{ id: 'session-1', message_count: 2 }] }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    }

    const [firstResult, secondResult] = await Promise.all([first, second]);

    assert.equal(fetchCount, 1);
    assert.equal(firstResult[0].id, 'session-1');
    assert.deepEqual(secondResult, firstResult);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('does not treat rate-limited auth check as logged out', async () => {
  const originalFetch = globalThis.fetch;

  globalThis.fetch = (async () => new Response('Too Many Requests', { status: 429 })) as typeof fetch;

  try {
    await assert.rejects(
      () => getMe(),
      /Auth check failed/,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('does not report logout success when the server fails to clear the session', async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async () => new Response('Service Unavailable', { status: 503 })) as typeof fetch;

  try {
    await assert.rejects(() => logout(), /Logout failed: 503/);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('coalesces concurrent auth check requests', async () => {
  const originalFetch = globalThis.fetch;
  const resolveResponses: Array<(value: Response) => void> = [];
  let fetchCount = 0;

  globalThis.fetch = (() => {
    fetchCount += 1;
    return new Promise<Response>((resolve) => {
      resolveResponses.push(resolve);
    });
  }) as typeof fetch;

  try {
    const first = getMe();
    const second = getMe();

    for (const resolve of resolveResponses) {
      resolve(
        new Response(JSON.stringify({ username: 'barbara' }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    }

    const [firstResult, secondResult] = await Promise.all([first, second]);

    assert.equal(fetchCount, 1);
    assert.deepEqual(firstResult, { username: 'barbara' });
    assert.deepEqual(secondResult, firstResult);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('does not treat rate-limited admin auth check as logged out', async () => {
  const originalFetch = globalThis.fetch;

  globalThis.fetch = (async () => new Response('Too Many Requests', { status: 429 })) as typeof fetch;

  try {
    await assert.rejects(
      () => getAdminMe(),
      /Admin auth check failed/,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('reports heartbeat authorization and rate limit failures', async () => {
  const originalFetch = globalThis.fetch;

  globalThis.fetch = (async () => new Response('Unauthorized', { status: 401 })) as typeof fetch;

  try {
    await assert.rejects(
      () => sendPresenceHeartbeat('dashboard'),
      /UNAUTHORIZED/,
    );

    globalThis.fetch = (async () => new Response('Too Many Requests', { status: 429 })) as typeof fetch;

    await assert.rejects(
      () => sendPresenceHeartbeat('dashboard'),
      /Presence heartbeat failed: 429/,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('reports unauthorized chat stream through error callback', async () => {
  const originalFetch = globalThis.fetch;
  let reportedError = '';

  globalThis.fetch = (async () => new Response('Unauthorized', { status: 401 })) as typeof fetch;

  try {
    streamChat(
      'session-1',
      'hello',
      () => undefined,
      () => undefined,
      '',
      (err) => {
        reportedError = err.message;
      },
    );
    await new Promise((resolve) => setTimeout(resolve, 0));
    assert.equal(reportedError, 'UNAUTHORIZED');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('sends chat rationale debug flag and emits rationale events', async () => {
  const originalFetch = globalThis.fetch;
  let requestBody: Record<string, unknown> = {};
  const receivedRationales: Array<{ stage?: string; topic?: string }> = [];

  globalThis.fetch = (async (_input, init) => {
    requestBody = JSON.parse(String(init?.body || '{}'));
    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(
          `data: ${JSON.stringify({
            type: 'question_rationale',
            content: {
              stage: 'technical',
              topic: 'LangGraph',
              question_kind: 'followup',
              objective: '验证状态流转理解',
            },
          })}\n\n`,
        ));
        controller.enqueue(encoder.encode(`data: ${JSON.stringify({ type: 'done' })}\n\n`));
        controller.close();
      },
    });
    return new Response(stream, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    });
  }) as typeof fetch;

  try {
    streamChat(
      'session-1',
      'hello',
      () => undefined,
      () => undefined,
      '',
      () => undefined,
      true,
      (rationale) => {
        receivedRationales.push(rationale);
      },
    );
    await new Promise((resolve) => setTimeout(resolve, 0));
    await new Promise((resolve) => setTimeout(resolve, 0));

    assert.equal(requestBody.debug_rationale, true);
    assert.equal(receivedRationales[0]?.stage, 'technical');
    assert.equal(receivedRationales[0]?.topic, 'LangGraph');
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('coalesces common setup resource requests', async () => {
  const originalFetch = globalThis.fetch;
  const requestUrls: string[] = [];

  globalThis.fetch = (async (input) => {
    const url = String(input);
    requestUrls.push(url);
    if (url.endsWith('/domains')) {
      return new Response(JSON.stringify({ presets: ['backend'] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (url.endsWith('/profiles')) {
      return new Response(JSON.stringify({ profiles: [{ key: 'p1', company: 'A', position: 'B', source_count: 1 }] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (url.endsWith('/resumes')) {
      return new Response(JSON.stringify({ resumes: [] }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    return new Response('{}', { status: 404 });
  }) as typeof fetch;

  try {
    const [domainsA, domainsB] = await Promise.all([fetchDomains(), fetchDomains()]);
    const [profilesA, profilesB] = await Promise.all([fetchProfiles(), fetchProfiles()]);
    const [resumesA, resumesB] = await Promise.all([fetchResumes(), fetchResumes()]);

    assert.deepEqual(domainsA, ['backend']);
    assert.deepEqual(domainsB, domainsA);
    assert.deepEqual(profilesB, profilesA);
    assert.deepEqual(resumesB, resumesA);
    assert.equal(requestUrls.filter((url) => url.endsWith('/domains')).length, 1);
    assert.equal(requestUrls.filter((url) => url.endsWith('/profiles')).length, 1);
    assert.equal(requestUrls.filter((url) => url.endsWith('/resumes')).length, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('keeps user-scoped resume caches isolated across authentication epochs', async () => {
  const originalFetch = globalThis.fetch;
  const resolveResponses: Array<(value: Response) => void> = [];
  let fetchCount = 0;
  resetUserScopedApiState();

  globalThis.fetch = (() => {
    fetchCount += 1;
    return new Promise<Response>((resolve) => {
      resolveResponses.push(resolve);
    });
  }) as typeof fetch;

  try {
    const firstUserRequest = fetchResumes();
    resetUserScopedApiState();
    const secondUserRequest = fetchResumes();

    assert.equal(fetchCount, 2);
    resolveResponses[1](new Response(JSON.stringify({ resumes: [{ id: 2, title: 'B' }] }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));
    assert.equal((await secondUserRequest)[0].id, 2);

    resolveResponses[0](new Response(JSON.stringify({ resumes: [{ id: 1, title: 'A' }] }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));
    assert.equal((await firstUserRequest)[0].id, 1);

    const currentUserCachedResult = await fetchResumes();
    assert.equal(currentUserCachedResult[0].id, 2);
    assert.equal(fetchCount, 2);
  } finally {
    resetUserScopedApiState();
    globalThis.fetch = originalFetch;
  }
});

test('does not reuse an in-flight session list request after the authenticated user changes', async () => {
  const originalFetch = globalThis.fetch;
  const resolveResponses: Array<(value: Response) => void> = [];
  let fetchCount = 0;
  resetUserScopedApiState();

  globalThis.fetch = (() => {
    fetchCount += 1;
    return new Promise<Response>((resolve) => {
      resolveResponses.push(resolve);
    });
  }) as typeof fetch;

  try {
    const firstUserRequest = fetchInterviewSessions(100);
    resetUserScopedApiState();
    const secondUserRequest = fetchInterviewSessions(100);

    assert.equal(fetchCount, 2);
    resolveResponses[1](new Response(JSON.stringify({ sessions: [{ id: 'session-b' }] }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));
    resolveResponses[0](new Response(JSON.stringify({ sessions: [{ id: 'session-a' }] }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }));

    assert.equal((await secondUserRequest)[0].id, 'session-b');
    assert.equal((await firstUserRequest)[0].id, 'session-a');
  } finally {
    resetUserScopedApiState();
    globalThis.fetch = originalFetch;
  }
});
