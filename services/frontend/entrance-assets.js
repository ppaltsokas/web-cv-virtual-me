// Exact public files, independent of Vite's private portfolio chunks.
export const entranceAssets = new Set([
  '/entrance/entrance.css',
  '/entrance/entrance.js',
  '/entrance/state.js',
  '/entrance/room.webp',
  '/entrance/room-mobile.webp',
  '/entrance/npc-idle.webp',
  '/entrance/npc-mobile-idle.webp',
  '/entrance/foliage.svg',
  '/entrance/curtains.svg',
  '/entrance/curtains-mobile.svg',
  '/entrance/pirate.webp',
  '/entrance/command-panel.svg',
  '/entrance/command-panel-mobile.svg',
]);

export const entranceCsp = "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; font-src 'self'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'; object-src 'none'";
