import { loadProfile, interpolate, escapeHtml } from './profile-config.mjs';
export const accessMessages = {
  invalid_password: 'Incorrect password. Please try again.',
  rate_limited: 'Too many attempts. Please wait before trying again.',
  forbidden: 'This address could not be verified. Open your original invitation link and try again.',
  invalid_request: 'The sign-in request could not be read. Please try again.',
  unavailable: 'Sign-in is temporarily unavailable. Please try again shortly.',
};

function roomScene(portrait = false) {
  const variant = portrait ? 'portrait' : 'landscape', width = portrait ? 360 : 640, height = portrait ? 640 : 360;
  return `<div class="scene scene-${variant}" aria-hidden="true">
    <svg class="room-art" data-breeze data-variant="${variant}" viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg">
      <defs><filter id="breeze-${variant}" filterUnits="userSpaceOnUse" x="0" y="0" width="${width}" height="${height}" color-interpolation-filters="sRGB">
        <feTurbulence type="fractalNoise" baseFrequency="0.012 0.008" numOctaves="1" seed="7" result="wind"><animate attributeName="baseFrequency" values="0.012 0.008;0.018 0.012;0.014 0.010;0.010 0.007;0.012 0.008" dur="4s" calcMode="spline" keyTimes="0;.3;.55;.8;1" keySplines=".42 0 .58 1;.42 0 .58 1;.42 0 .58 1;.42 0 .58 1" repeatCount="indefinite"/></feTurbulence>
        <feImage href="/entrance/curtains${portrait ? '-mobile' : ''}.svg" x="0" y="0" width="${width}" height="${height}" result="curtain-mask"/>
        <feComposite in="wind" in2="curtain-mask" operator="in" result="curtain-wind"/><feFlood flood-color="#808080" result="still"/>
        <feMerge result="displacement"><feMergeNode in="still"/><feMergeNode in="curtain-wind"/></feMerge>
        <feDisplacementMap in="SourceGraphic" in2="displacement" scale="20" xChannelSelector="R" yChannelSelector="G"><animate attributeName="scale" values="20;28;18;25;20" dur="4s" calcMode="spline" keyTimes="0;.3;.55;.8;1" keySplines=".42 0 .58 1;.42 0 .58 1;.42 0 .58 1;.42 0 .58 1" repeatCount="indefinite"/></feDisplacementMap>
      </filter></defs>
      <image class="room" href="/entrance/room${portrait ? '-mobile' : ''}.webp" width="${width}" height="${height}" filter="url(#breeze-${variant})"/>
    </svg>
    <div class="npc-idle ambient"></div><img class="foliage ambient" src="/entrance/foliage.svg" alt="">
    <div class="sunbeam ambient"></div><div class="dust ambient"></div>
    <div class="crt"><img class="pirate" src="/entrance/pirate.webp" alt=""><span class="crt-scanlines"></span></div>
  </div>`;
}

export function accessPage(signedIn = false, error = '') {
  const message = accessMessages[error] || '';
  const profile = loadProfile();
  const title = escapeHtml(interpolate(profile.entrance.title, profile.resume.personalInfo.name));
  const subtitle = escapeHtml(profile.entrance.subtitle);
  return `<!doctype html>
<html lang="en"><head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <meta name="robots" content="noindex,nofollow"><meta name="color-scheme" content="dark"><title>${title}</title>
  <link rel="stylesheet" href="/entrance/entrance.css"><script type="module" src="/entrance/entrance.js"></script>
</head><body>
  <main class="entrance" data-entrance data-state="ready">
    <div class="room-viewport" role="img" aria-label="A sunlit 1990s bedroom. A boy plays in an orange beanbag, curtains move in the breeze, and the CRT shows Moonwake Island, an original pirate adventure.">${roomScene()}${roomScene(true)}</div>
    <header class="welcome">
      <h1 id="entrance-title" class="welcome-lettering">${title}</h1>
      <p class="welcome-subtitle">${subtitle}</p>
    </header>
    <section class="access-panel${signedIn ? ' is-signed-in' : ''}" aria-labelledby="entrance-title">
      ${signedIn ? '<div class="signed-in-actions"><span class="access-caption">Signed in</span><a class="portfolio-link" href="/">Open portfolio</a><form method="post" action="/access/logout"><button class="start-button sign-out" type="submit">Sign out</button></form></div>' : `<form method="post" action="/access/login" data-login-form>
        <label for="password">Access password</label>
        <div class="form-row"><input id="password" name="password" type="password" autocomplete="current-password" maxlength="128" aria-describedby="access-status" required><button class="start-button" type="submit" data-submit>Enter</button></div>
      </form>`}
      <p id="access-status" class="access-status" role="status" aria-live="polite" aria-atomic="true" data-status>${message}</p>
    </section>
  </main>
</body></html>`;
}
