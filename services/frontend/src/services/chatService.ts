import { API_URL } from '../constants';
export interface ChatSession {
  sendMessageStream: (params: { message: string; sessionId?: string }) => AsyncGenerator<{ text: string; images?: string[] }, void, unknown>;
}
export const createChatSession = (): ChatSession => ({
  sendMessageStream: async function* ({ message, sessionId = 'default' }) {
    try {
      const response = await fetch(`${API_URL}/chat`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, session_id: sessionId }), signal: AbortSignal.timeout(180_000),
      });
      if (response.status === 401) { window.location.assign('/access'); return; }
      if (!response.ok || !response.body) {
        yield { text: response.status === 429 ? 'Please wait a moment before sending more messages.'
          : response.status === 409 ? 'Please wait for the previous reply.'
          : 'Chat is temporarily unavailable. Please try again shortly.' };
        return;
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const text = decoder.decode(value, { stream: true });
          if (text) yield { text };
        }
        const tail = decoder.decode();
        if (tail) yield { text: tail };
      } finally { reader.releaseLock(); }
    } catch {
      yield { text: 'The connection to chat was interrupted. Please try again.' };
    }
  },
});
