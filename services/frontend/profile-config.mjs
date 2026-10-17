import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
export const escapeHtml = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const interpolate = (text, name) => String(text).replaceAll('{name}', name);

function safeUrl(value, local = false) {
  if (typeof value !== 'string' || !value) return false;
  if (local && /^\/(?!\/)[A-Za-z0-9_./-]+$/.test(value) && !value.split('/').includes('..')) return true;
  try { const url = new URL(value); return url.protocol === 'https:' && !url.username && !url.password; } catch { return false; }
}

export function loadProfile(env = process.env) {
  const local = path.join(repoRoot, 'config/profile.local.json');
  const filename = env.PORTFOLIO_PROFILE ? path.resolve(repoRoot, env.PORTFOLIO_PROFILE)
    : fs.existsSync(local) ? local : path.join(repoRoot, 'config/profile.example.json');
  const profile = JSON.parse(fs.readFileSync(filename, 'utf8').replace(/^\uFEFF/, ''));
  const { resume, chat, entrance, site, timezone } = profile;
  if (!resume?.personalInfo?.name || !resume.personalInfo.title || !chat?.name || !entrance?.title || !site?.title) throw new Error('Incomplete profile. Run python scripts/manage.py check.');
  for (const key of ['experience', 'education', 'projects', 'skills']) {
    if (!Array.isArray(resume[key])) throw new Error(`resume.${key} must be an array`);
  }
  new Intl.DateTimeFormat('en', { timeZone: timezone }).format();
  for (const url of Object.values(resume.personalInfo.socials || {})) if (url && !safeUrl(url)) throw new Error('Social links must be absolute HTTPS URLs.');
  if (chat.avatar && !safeUrl(chat.avatar, true)) throw new Error('Invalid avatar URL');
  if (site.url && !safeUrl(site.url)) throw new Error('Site URL must use HTTPS');
  for (const project of [...(resume.projects || []), ...(resume.latestProjects || [])]) {
    if (project.link && !safeUrl(project.link)) throw new Error('Project links must use HTTPS');
  }
  return profile;
}

// Serialize only display fields. Private birth facts, documents and server keys
// never enter the Vite bundle, even if a future owner adds private config fields.
export function publicProfile(profile, env = process.env) {
  const r = profile.resume;
  const fields = (object, names) => Object.fromEntries(names.filter(key => object[key] !== undefined).map(key => [key, object[key]]));
  const localManifest = path.join(repoRoot, 'config/content.local.json');
  const manifestPath = env.CONTENT_MANIFEST ? path.resolve(repoRoot, env.CONTENT_MANIFEST)
    : fs.existsSync(localManifest) ? localManifest : path.join(repoRoot, 'config/content.example.json');
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8').replace(/^\uFEFF/, ''));
  const published = (manifest.documents || []).filter(row => row.public && row.path?.toLowerCase().endsWith('.pdf'));
  const projects = rows => rows.map(row => ({
    ...fields(row, ['id', 'title', 'description', 'link', 'technologies']),
    ...(row.pdfPath && published.some(item => item.id === row.pdfPath) ? { pdfPath: row.pdfPath } : {}),
  }));
  return {
    resume: {
      personalInfo: { ...fields(r.personalInfo, ['name', 'title', 'bio', 'email', 'location']), socials: fields(r.personalInfo.socials || {}, ['github', 'linkedin', 'twitter']) },
      experience: r.experience.map(row => fields(row, ['id', 'role', 'company', 'period', 'description', 'technologies'])),
      education: r.education.map(row => fields(row, ['id', 'degree', 'school', 'year', 'grade'])),
      certifications: (r.certifications || []).map(row => fields(row, ['id', 'title', 'issuer', 'year', 'icon', 'credentialUrl'])),
      latestProjects: projects(r.latestProjects || []),
      projects: projects(r.projects),
      skills: r.skills.map(row => fields(row, ['name', 'skills'])),
    },
    chat: fields(profile.chat, ['name', 'greeting', 'placeholder', 'avatar']),
    cvAvailable: published.some(row => row.kind === 'cv'),
  };
}
