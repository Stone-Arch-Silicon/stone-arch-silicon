/* =====================================================================
   Small UI shared by every page: year, header, menu, progress, reveal,
   motion preference. Each feature checks that its elements exist, since
   the hero film, rolling headline, and statement only live on index.html.
   ===================================================================== */
(function(){
  'use strict';
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const root = document.documentElement;

  /* storage is wrapped: private windows and locked-down browsers throw on access */
  function readPref(k){ try { return localStorage.getItem(k); } catch(e){ return null; } }
  function writePref(k, v){ try { localStorage.setItem(k, v); } catch(e){} }
  window.SASi = { readPref, writePref };

  const yearEl = $('#year');
  if (yearEl) yearEl.textContent = new Date().getFullYear();

  /* ---------- motion: OS setting by default, the hero toggle overrides ----------
     The choice is saved, so pausing on the home page carries over to every page. */
  const MOTION_KEY = 'sasi-motion';
  const reduceMQ = matchMedia('(prefers-reduced-motion: reduce)');
  const saved = readPref(MOTION_KEY);
  const listeners = [];
  const motionBtn = $('#motionBtn'), motionLabel = $('#motionLabel');
  const Motion = {
    on: saved ? saved === 'on' : !reduceMQ.matches,
    set(v, persist){
      this.on = v;
      root.classList.toggle('motion-off', !v);
      if (motionBtn) motionBtn.setAttribute('aria-pressed', String(!v));
      if (motionLabel) motionLabel.textContent = v ? 'Pause motion' : 'Play motion';
      if (persist) writePref(MOTION_KEY, v ? 'on' : 'off');
      listeners.forEach(fn => fn(v));
    },
    subscribe(fn){ listeners.push(fn); }
  };
  window.SASi.Motion = Motion;
  if (motionBtn) motionBtn.addEventListener('click', () => Motion.set(!Motion.on, true));

  /* ---------- sponsor logo belt ---------- */
  $$('.sponsor-belt').forEach(belt => {
    const track = $('.sponsor-track', belt);
    const group = $('.sponsor-group', belt);
    const button = $('.sponsor-toggle', belt);
    if (!track || !group || !button) return;
    const copy = group.cloneNode(true);
    copy.setAttribute('aria-hidden', 'true');
    copy.removeAttribute('aria-label');
    copy.setAttribute('inert', '');
    $$('a', copy).forEach(link => link.setAttribute('tabindex', '-1'));
    track.appendChild(copy);
    belt.classList.add('is-ready');
    button.hidden = false;
    button.addEventListener('click', () => {
      const paused = belt.classList.toggle('is-paused');
      button.setAttribute('aria-pressed', String(paused));
      button.textContent = paused ? 'Resume logos' : 'Pause logos';
    });
  });

  /* ---------- hero film ---------- */
  const video = $('#heroVideo');
  function syncVideo(on){
    if (!video) return;
    if (on){
      if (video.preload !== 'auto') video.preload = 'auto';
      const p = video.play();
      if (p && p.catch) p.catch(() => {});   // low-power mode etc.: the poster stays up
    } else {
      video.pause();
    }
  }
  if (video){
    video.muted = true;
    video.addEventListener('playing', () => video.classList.add('is-playing'));
    // stop decoding while the hero is off screen
    new IntersectionObserver(([e]) => {
      if (!Motion.on) return;
      if (e.isIntersecting) syncVideo(true); else video.pause();
    }, { threshold: 0 }).observe(video);
    Motion.subscribe(syncVideo);
    document.addEventListener('visibilitychange', () => { if (!document.hidden && Motion.on) syncVideo(true); });
  }

  /* ---------- rolling word in the headline ---------- */
  const roller = $('#roller');
  if (roller){
    const items = roller.children.length;          // last item duplicates the first
    let i = 0, timer = null;
    const hold = idx => (idx === 0 ? 3600 : 1500);
    function step(){
      i++;
      roller.classList.remove('no-anim');
      roller.style.transform = 'translateY(' + (-i * (100 / items)) + '%)';
      if (i === items - 1){
        // landed on the duplicate of the first word: snap back without animation
        setTimeout(() => { roller.classList.add('no-anim'); i = 0; roller.style.transform = 'translateY(0)'; }, 900);
      }
      timer = setTimeout(step, hold(i === items - 1 ? 0 : i) + 850);
    }
    function start(){ if (!timer) timer = setTimeout(step, hold(0)); }
    function stop(){ clearTimeout(timer); timer = null; roller.classList.add('no-anim'); i = 0; roller.style.transform = 'translateY(0)'; }
    Motion.subscribe(on => on ? start() : stop());
  }

  /* ---------- announcement ---------- */
  const header = $('#siteHeader');
  const ann = $('#announce');
  const ANN_KEY = 'sasi-announce-2026-fall';
  function setAnnH(){ if (ann && !ann.hidden) header.style.setProperty('--ann-h', ann.offsetHeight + 'px'); }
  if (ann){
    if (readPref(ANN_KEY) === 'x') ann.hidden = true;
    $('#announceClose').addEventListener('click', () => { ann.hidden = true; writePref(ANN_KEY, 'x'); onScroll(); });
    setAnnH(); addEventListener('resize', setAnnH);
  }

  /* ---------- nav takes the theme of the section under it ---------- */
  const nav = $('#nav');
  const themed = $$('[data-nav]');
  const progress = $('#progress');
  let ticking = false;
  function onScroll(){
    if (ticking) return; ticking = true;
    requestAnimationFrame(() => {
      ticking = false;
      const y = scrollY;
      header.classList.toggle('is-scrolled', y > 24);
      const probe = nav.getBoundingClientRect().bottom - 1;
      let theme = 'dark', inHeroTop = false;
      for (const s of themed){
        const r = s.getBoundingClientRect();
        if (r.top <= probe && r.bottom > probe){ theme = s.dataset.nav; inHeroTop = s.id === 'top' && y < 40; break; }
      }
      nav.classList.toggle('on-dark', theme === 'dark' && !inHeroTop);
      nav.classList.toggle('on-light', theme === 'light');
      const max = document.documentElement.scrollHeight - innerHeight;
      progress.style.transform = 'scaleX(' + (max > 0 ? Math.min(1, y / max) : 0) + ')';
      statementTick();
    });
  }
  addEventListener('scroll', onScroll, { passive: true });
  addEventListener('resize', onScroll);

  /* ---------- menu ---------- */
  const menu = $('#menu'), toggle = $('#menuToggle'), closeBtn = $('#menuClose');
  let lastFocus = null;
  function openMenu(){
    lastFocus = document.activeElement;
    menu.classList.add('is-open'); document.body.classList.add('menu-open');
    toggle.setAttribute('aria-expanded', 'true');
    setTimeout(() => closeBtn.focus(), 30);
  }
  function closeMenu(restore = true){
    menu.classList.remove('is-open'); document.body.classList.remove('menu-open');
    toggle.setAttribute('aria-expanded', 'false');
    if (restore && lastFocus) lastFocus.focus({ preventScroll: true });
  }
  toggle.addEventListener('click', openMenu);
  closeBtn.addEventListener('click', () => closeMenu());
  $$('[data-close]', menu).forEach(a => a.addEventListener('click', () => closeMenu(false)));
  document.addEventListener('keydown', e => {
    if (!menu.classList.contains('is-open')) return;
    if (e.key === 'Escape') closeMenu();
    if (e.key === 'Tab'){
      const f = $$('a,button', menu); const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first){ e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last){ e.preventDefault(); first.focus(); }
    }
  });

  /* ---------- statement: words fill in as you scroll ---------- */
  const statement = $('#statement');
  let words = [];
  if (statement){
    const walker = document.createTreeWalker(statement, NodeFilter.SHOW_TEXT);
    const nodes = []; while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(n => {
      const frag = document.createDocumentFragment();
      n.textContent.split(/(\s+)/).forEach(part => {
        if (!part) return;
        if (/^\s+$/.test(part)){ frag.appendChild(document.createTextNode(part)); return; }
        const s = document.createElement('span'); s.className = 'w'; s.textContent = part; frag.appendChild(s);
      });
      n.parentNode.replaceChild(frag, n);
    });
    words = $$('.w', statement);
  }
  function statementTick(){
    if (!words.length) return;
    const r = statement.getBoundingClientRect();
    const start = innerHeight * 0.9, end = innerHeight * 0.35;
    const p = Math.min(1, Math.max(0, (start - r.top) / (start - end + r.height * 0.6)));
    const n = Math.round(p * words.length);
    words.forEach((w, k) => w.classList.toggle('on', k < n));
  }

  /* ---------- reveal ---------- */
  const io = new IntersectionObserver(entries => {
    entries.forEach(e => { if (e.isIntersecting){ e.target.classList.add('in'); io.unobserve(e.target); } });
  }, { threshold: 0.12, rootMargin: '0px 0px -6% 0px' });
  $$('.reveal').forEach(el => io.observe(el));

  /* ---------- footer wordmark: fit to the container width ---------- */
  const wm = $('#wordmark');
  function fitWordmark(){
    if (!wm) return;
    const span = wm.firstElementChild;
    wm.style.fontSize = '100px';
    const w = span.getBoundingClientRect().width;
    if (w > 0) wm.style.fontSize = (100 * wm.clientWidth / w * 0.992) + 'px';
  }
  addEventListener('resize', fitWordmark);
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(fitWordmark); else fitWordmark();
  fitWordmark();

  Motion.set(Motion.on, false);
  onScroll();
})();
