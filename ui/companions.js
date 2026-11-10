/* Asset preview only. Typing events stay local to the explicit demo field. */
'use strict';
const pace = document.querySelector('#pace');
const playback = document.querySelector('#playback');
const gallery = document.querySelector('#characters');
const status = document.querySelector('#load-status');
const motionPreference = matchMedia('(prefers-reduced-motion: reduce)');
let paused = motionPreference.matches;
let started = performance.now();
const characters = [];
const labels = {idle:'A quiet moment', sleep:'A little rest', quiet:'Quiet company', typing:'Busy hands', flow:'In the flow', zoom:'Tiny hands, big energy', sip:'Drink break', stretch:'Biiig stretch', music:'A little headphone groove', cheer:'Little celebration', streak:'Nice typing streak!'};
function render(force = false) {
  if (document.hidden && !force) return;
  for (const character of characters) {
    const now = performance.now();
    const state = pace.value === 'life' ? character.motion.tick(now, paused) :
      {frame: CompanionMotion.frameAt(character.manifest.animation[pace.value], paused ? 0 : now - started), activity: pace.value, wpm: 0};
    const frame = state.frame;
    character.moment.textContent = labels[state.activity] || 'A little moment';
    character.canvas.dataset.activity = state.activity;
    if (pace.value === 'life') document.querySelector('#typing-rate').textContent = `${state.wpm} WPM`;
    if (force || character.frame !== frame) {
      character.context.clearRect(0, 0, 80, 80);
      character.context.drawImage(character.image, (frame % 3) * 80, Math.floor(frame / 3) * 80, 80, 80, 0, 0, 80, 80);
      character.canvas.dataset.frame = String(frame);
      character.frame = frame;
    }
  }
}
function playbackLabel() {
  playback.textContent = paused ? 'Play' : 'Pause';
  playback.setAttribute('aria-label', paused ? 'Play animations' : 'Pause animations');
}
playback.addEventListener('click', () => { paused = !paused; started = performance.now(); playbackLabel(); render(true); });
pace.addEventListener('change', () => { started = performance.now(); render(true); });
document.querySelector('#appearance').addEventListener('change', event => gallery.classList.toggle('light', event.target.value === 'light'));
document.querySelector('#native-size').addEventListener('change', event => gallery.classList.toggle('actual-size', event.target.checked));
motionPreference.addEventListener('change', event => { if (event.matches) { paused = true; playbackLabel(); render(true); } });
playbackLabel();
document.querySelector('#typing-demo').addEventListener('input', event => {
  if (!event.inputType?.startsWith('insert')) return;
  pace.value = 'life';
  for (const character of characters) character.motion.tap(performance.now());
  render(true);
});

(async () => {
  try {
    const response = await fetch('assets/characters/index.json');
    if (!response.ok) throw new Error('Library unavailable');
    const library = await response.json();
    for (const entry of library.characters) {
      const response = await fetch(entry.manifest);
      if (!response.ok) throw new Error('Character unavailable');
      const manifest = await response.json();
      const image = new Image(); image.src = entry.atlas; await image.decode();
      const article = document.createElement('article'); article.className = 'companion';
      const stage = document.createElement('div'); stage.className = 'companion-stage';
      const canvas = document.createElement('canvas'); canvas.width = canvas.height = 80;
      canvas.setAttribute('role', 'img'); canvas.setAttribute('aria-label', `${entry.name}, animated desk companion`);
      stage.append(canvas);
      const title = document.createElement('h2'); title.textContent = entry.name;
      const description = document.createElement('p'); description.textContent = entry.description;
      const moment = document.createElement('p'); moment.className = 'companion-moment';
      const download = document.createElement('a'); download.className = 'download'; download.href = entry.download;
      download.download = ''; download.textContent = `Download ${entry.name}`;
      article.append(stage, title, description, moment, download); gallery.append(article);
      const seed = crypto.getRandomValues(new Uint32Array(1))[0];
      characters.push({ manifest, image, canvas, context: canvas.getContext('2d'), frame: -1, moment,
        motion: new CompanionMotion.Motion(manifest, seed, performance.now()) });
    }
    status.textContent = ''; render(true); setInterval(render, 40);
  } catch (error) {
    status.textContent = 'The previews could not load. Refresh to try again, or download the set above.';
  }
})();
