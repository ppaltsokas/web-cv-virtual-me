// Authentication only. Ambient NPC motion is independent of login results.
export function createEntranceState() {
  let state = { phase: 'loading', message: '', attempt: 0 };
  return {
    get snapshot() { return { ...state }; },
    send(event) {
      if (event.type === 'BOOT' && state.phase === 'loading') state = { ...state, phase: 'ready', message: event.message || '' };
      else if (event.type === 'SUBMIT' && ['ready', 'rejected', 'service-error'].includes(state.phase)) state = { ...state, phase: 'submitting', message: 'Signing in...', attempt: state.attempt + 1 };
      else if (event.type === 'RESULT' && state.phase === 'submitting' && event.attempt === state.attempt) state = { ...state, phase: event.outcome === 'success' ? 'navigating' : event.outcome === 'rejected' ? 'rejected' : 'service-error', message: event.outcome === 'success' ? 'Signed in.' : event.message };
      return this.snapshot;
    },
  };
}

export function classifyLogin(status, data, retryAfter) {
  if (status === 200 && data?.authenticated === true && data?.redirect === '/') return { outcome: 'success' };
  if (status === 401 && data?.error === 'invalid_password') return { outcome: 'rejected', message: 'Incorrect password. Please try again.' };
  if (status === 429) {
    const seconds = Number(retryAfter);
    const wait = Number.isFinite(seconds) && seconds > 0 ? ` Try again in about ${Math.ceil(seconds / 60)} minute${seconds > 60 ? 's' : ''}.` : ' Please wait and try again.';
    return { outcome: 'error', message: `Too many attempts.${wait}` };
  }
  if (status === 403) return { outcome: 'error', message: 'This address could not be verified. Open your original invitation link and try again.' };
  if (status === 413 || status === 415) return { outcome: 'error', message: 'The sign-in request could not be read. Reload this page and try again.' };
  return { outcome: 'error', message: 'Sign-in is temporarily unavailable. Please try again shortly.' };
}
