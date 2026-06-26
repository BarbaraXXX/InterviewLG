import assert from 'node:assert/strict';
import test from 'node:test';

import { fetchInterviewSessions, getMe } from './api.ts';

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
