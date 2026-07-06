import assert from 'node:assert/strict';
import test from 'node:test';

import {
  fetchDomains,
  fetchInterviewSessions,
  fetchProfiles,
  fetchResumes,
  getAdminMe,
  getMe,
  sendPresenceHeartbeat,
  streamChat,
} from './api.ts';

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
