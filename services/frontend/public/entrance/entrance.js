import { createEntranceState, classifyLogin } from './state.js';

const root = document.querySelector('[data-entrance]');
if (root) {
  const form = root.querySelector('[data-login-form]');
  const input = form?.querySelector('input'), submit = form?.querySelector('[data-submit]');
  const status = root.querySelector('[data-status]'), scenes = [...root.querySelectorAll('[data-breeze]')];
  const motion = matchMedia('(prefers-reduced-motion: reduce)'), portrait = matchMedia('(max-aspect-ratio: 3/4)');
  const machine = createEntranceState();
  let disposed = false, request, requestTimeout, navigationFallback, navigating = false;
  const navigate = () => { if (!navigating && !disposed) { navigating = true; location.assign('/'); } };
  const render = state => {
    root.dataset.state = state.phase;
    if (form) {
      submit.disabled = ['submitting', 'navigating'].includes(state.phase);
      input.readOnly = submit.disabled;
      form.setAttribute('aria-busy', String(state.phase === 'submitting'));
      input.setAttribute('aria-invalid', String(state.phase === 'rejected'));
    }
    if (status.textContent !== state.message) status.textContent = state.message;
    if (state.phase === 'navigating') navigate();
  };
  const send = event => { if (!disposed) render(machine.send(event)); };
  const updateAmbient = () => {
    const paused = document.hidden || motion.matches;
    root.classList.toggle('paused', paused);
    for (const scene of scenes) {
      const inactive = scene.dataset.variant !== (portrait.matches ? 'portrait' : 'landscape');
      if (paused || inactive) scene.pauseAnimations?.();
      else scene.unpauseAnimations?.();
    }
  };
  const onVisibility = () => { updateAmbient(); if (!document.hidden && machine.snapshot.phase === 'navigating') navigate(); };
  const onSubmit = async event => {
    event.preventDefault();
    if (!['ready', 'rejected', 'service-error'].includes(machine.snapshot.phase) || !form.reportValidity()) return;
    send({ type: 'SUBMIT' });
    const attempt = machine.snapshot.attempt;
    request = new AbortController();
    requestTimeout = setTimeout(() => request?.abort(), 12000);
    try {
      const response = await fetch('/access/login', {
        method: 'POST', credentials: 'same-origin', redirect: 'error', signal: request.signal,
        headers: { Accept: 'application/json', 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams(new FormData(form)),
      });
      let data;
      try { data = await response.json(); } catch { /* Malformed responses remain service errors. */ }
      if (disposed || machine.snapshot.attempt !== attempt) return;
      const result = classifyLogin(response.status, data, response.headers.get('Retry-After'));
      if (result.outcome === 'success') { input.value = ''; navigationFallback = setTimeout(navigate, 0); }
      send({ type: 'RESULT', attempt, ...result });
      if (result.outcome === 'rejected') { input.focus(); input.select(); }
    } catch (error) {
      if (!disposed) send({ type: 'RESULT', attempt, outcome: 'error', message: error.name === 'AbortError' ? 'The connection took too long. Please try again.' : 'Connection failed. Check your connection and try again.' });
    } finally { clearTimeout(requestTimeout); request = undefined; }
  };
  const cleanup = () => {
    disposed = true;
    request?.abort(); clearTimeout(requestTimeout); clearTimeout(navigationFallback);
    form?.removeEventListener('submit', onSubmit);
    motion.removeEventListener('change', updateAmbient); portrait.removeEventListener('change', updateAmbient);
    document.removeEventListener('visibilitychange', onVisibility); window.removeEventListener('pagehide', cleanup);
    for (const scene of scenes) scene.pauseAnimations?.();
    root.classList.toggle('paused', true); root.dataset.state = 'ready';
    if (form) { submit.disabled = false; input.readOnly = false; form.setAttribute('aria-busy', 'false'); }
  };
  form?.addEventListener('submit', onSubmit);
  motion.addEventListener('change', updateAmbient); portrait.addEventListener('change', updateAmbient);
  document.addEventListener('visibilitychange', onVisibility); window.addEventListener('pagehide', cleanup);
  send({ type: 'BOOT', message: status.textContent.trim() }); updateAmbient();
}
