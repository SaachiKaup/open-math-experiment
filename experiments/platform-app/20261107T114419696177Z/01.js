// Before the first paint (index.html's head): a window reloading right after a resume
// (app/resume.js) draws the recovery card it left, as view/Lock.jsx does, in the startup area as
// soon as that is parsed, and the app keeps the card until it is ready. The startup area's own
// placeholder stays hidden (styles/skeleton.css). A mark no reload followed at once is dropped.
(() => {
  const KEY = 'nucleus.resume';
  let mark;
  try {
    mark = JSON.parse(sessionStorage.getItem(KEY) || 'null');
    if (mark && (!(Date.now() - mark.at >= 0 && Date.now() - mark.at < 30000)
      || (mark.org !== undefined && mark.org !== JSON.parse(localStorage.getItem('nucleus.org') ?? 'null')))) {
      sessionStorage.removeItem(KEY); mark = null;
    }
  } catch { return; }
  if (!mark || typeof mark.title !== 'string' || !Number.isFinite(mark.drift)) return;
  const root = document.documentElement;
  root.setAttribute('data-resuming', '');
  if (mark.theme) root.dataset.theme = mark.theme;
  if (mark.motion) root.dataset.motion = mark.motion;
  const symbol = new URL('brand/symbol-gradient.svg', document.currentScript.src).href;
  const element = (tag, className, ...children) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    node.append(...children);
    return node;
  };
  const draw = (startup) => {
    const daylight = element('div', 'recovery-daylight', element('i'), element('i'), element('i'), element('i'));
    daylight.style.setProperty('--recovery-phase', `${-(mark.drift + (Date.now() - mark.at) / 1000)}s`);
    const atmosphere = element('div', 'recovery-atmosphere', daylight);
    atmosphere.setAttribute('aria-hidden', 'true');
    const image = element('img', 'recovery-symbol');
    Object.assign(image, { src: symbol, alt: 'Open Math OS', width: 96, height: 96 });
    const title = element('h1', '', mark.title);
    title.id = 'recovery-startup-title';
    const status = element('div', 'recovery-status', title);
    const fill = element('div', 'recovery-progress-fill');
    // Match app/resume.js: old marks have no progress; malformed marks cannot fill the bar.
    fill.style.width = `${Number.isFinite(mark.progress) ? Math.max(0, Math.min(98, mark.progress)) : 0}%`;
    const progress = element('div', 'recovery-progress', fill);
    progress.setAttribute('role', 'progressbar');
    progress.setAttribute('aria-labelledby', title.id);
    startup.prepend(element('section', 'workspace-recovery', atmosphere,
      element('div', 'recovery-content', element('div', 'recovery-resume', image, status, progress))));
  };
  // The parser inserts the startup area before the browser can paint it.
  new MutationObserver((records, observer) => {
    const startup = document.getElementById('startup');
    if (startup) { observer.disconnect(); draw(startup); }
  }).observe(root, { childList: true, subtree: true });
})();
