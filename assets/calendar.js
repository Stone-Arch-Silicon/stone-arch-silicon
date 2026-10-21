/* ================================================================
   CALENDAR
   Reads events from the public SASI@umn.edu Google Calendar through the
   Google Calendar API and draws them in the site's own month grid and
   list. All dates are shown in Central time regardless of the visitor's
   own timezone.

   SETUP (one time):
   1. Make the calendar public. Signed in as SASI@umn.edu: Settings ->
      Settings for my calendars -> the SASi calendar -> Access permissions
      for events -> "Make available to public" + "See all event details".
   2. In Google Cloud Console (any Google account works, since the
      calendar is public): create a project, enable "Google Calendar API",
      then Credentials -> Create credentials -> API key.
   3. Restrict the key. Application restrictions -> Websites -> add your
      site, e.g. https://stone-arch-silicon.github.io/* (and
      http://localhost/* if you test locally). API restrictions -> Google
      Calendar API only.
   4. Paste the key into API_KEY below.

   The key is visible in the page source. That's normal for this setup:
   it can only read public calendars and only works from your domain.

   With API_KEY empty the section shows sample events and says so.
   ================================================================ */
(function(){
  const gridEl = document.getElementById('calGrid');
  if (!gridEl) return;

  const CAL_ID   = 'SASI@umn.edu';
  const API_KEY  = 'AIzaSyBONqZ7hYFtmgfZVL_rUCti1yGHF6-Iw68';                 // <- paste the restricted key here
  const TZ       = 'America/Chicago';
  const UPCOMING = 8;                  // events in the default list

  const el = {
    month: document.getElementById('calMonth'),
    list:  document.getElementById('calList'),
    head:  document.getElementById('calSideHead'),
    reset: document.getElementById('calReset'),
    status:document.getElementById('calStatus')
  };

  /* ---- date helpers. Day keys are "YYYY-MM-DD" in Central time. ---- */
  const keyFmt   = new Intl.DateTimeFormat('en-CA', {timeZone:TZ, year:'numeric', month:'2-digit', day:'2-digit'});
  const timeFmt  = new Intl.DateTimeFormat('en-US', {timeZone:TZ, hour:'numeric', minute:'2-digit'});
  const monthFmt = new Intl.DateTimeFormat('en-US', {timeZone:'UTC', month:'long', year:'numeric'});
  const dayFmt   = new Intl.DateTimeFormat('en-US', {timeZone:'UTC', weekday:'short', month:'short', day:'numeric'});
  const monFmt   = new Intl.DateTimeFormat('en-US', {timeZone:'UTC', month:'short'});
  const partsFmt = new Intl.DateTimeFormat('en-US', {timeZone:TZ, hourCycle:'h23', year:'numeric', month:'numeric', day:'numeric', hour:'numeric', minute:'numeric'});

  const keyOf   = d => keyFmt.format(d);
  const toUTC   = k => new Date(Date.UTC(+k.slice(0,4), +k.slice(5,7)-1, +k.slice(8,10)));
  const addDays = (k, n) => { const t = toUTC(k); t.setUTCDate(t.getUTCDate() + n); return t.toISOString().slice(0,10); };
  const short   = d => timeFmt.format(d).replace(':00','').replace(' AM','a').replace(' PM','p');

  // the instant whose Central wall-clock time is key h:m (used for sample data)
  function atCentral(k, h, m){
    const g = Date.UTC(+k.slice(0,4), +k.slice(5,7)-1, +k.slice(8,10), h, m);
    const p = {}; partsFmt.formatToParts(new Date(g)).forEach(x => p[x.type] = x.value);
    const wall = Date.UTC(+p.year, +p.month-1, +p.day, +p.hour % 24, +p.minute);
    return new Date(g - (wall - g));
  }

  const todayKey = keyOf(new Date());
  let viewY = +todayKey.slice(0,4), viewM = +todayKey.slice(5,7) - 1;
  let selected = null;   // selected day key, or null for the upcoming list
  let openId = null;     // expanded event in the list

  const byId = new Map();
  const loaded = new Set();
  let upcoming = [];

  /* ---- normalise a Google event ---- */
  function norm(e){
    const allDay = !!e.start.date;
    let start, end, startKey, endKey;
    if (allDay){
      startKey = e.start.date;
      endKey = addDays((e.end && e.end.date) || e.start.date, -1);   // Google's end date is exclusive
      if (endKey < startKey) endKey = startKey;
      start = toUTC(startKey); end = toUTC(endKey);
    } else {
      start = new Date(e.start.dateTime);
      end = new Date((e.end && e.end.dateTime) || e.start.dateTime);
      startKey = keyOf(start);
      endKey = keyOf(new Date(Math.max(+start, +end - 1)));
    }
    return {
      id:e.id, title:e.summary || 'Untitled event', desc:e.description || '',
      loc:e.location || '', link:e.htmlLink || '',
      allDay, start, end, startKey, endKey
    };
  }
  const cmp = (a, b) =>
    a.startKey !== b.startKey ? (a.startKey < b.startKey ? -1 : 1)
    : a.allDay !== b.allDay ? (a.allDay ? -1 : 1)
    : a.start - b.start;

  function eventsOn(k){
    const out = [];
    byId.forEach(ev => { if (ev.startKey <= k && k <= ev.endKey) out.push(ev); });
    return out.sort(cmp);
  }

  function timeLabel(ev){
    if (ev.allDay) return ev.startKey === ev.endKey ? 'All day' : 'Until ' + dayFmt.format(toUTC(ev.endKey));
    if (ev.startKey !== ev.endKey) return timeFmt.format(ev.start) + ' to ' + dayFmt.format(toUTC(ev.endKey));
    return timeFmt.format(ev.start) + ' – ' + timeFmt.format(ev.end);
  }

  // Google descriptions can hold HTML. Parse it inert and keep only the text.
  function plain(html){
    const t = document.createElement('template');
    t.innerHTML = html.replace(/<br\s*\/?>/gi, '\n').replace(/<\/p>/gi, '\n');
    return t.content.textContent.trim();
  }

  /* ---- data source: the API, or sample events when there's no key ---- */
  async function api(params){
    const q = new URLSearchParams(Object.assign({
      key:API_KEY, singleEvents:'true', orderBy:'startTime', maxResults:'250', timeZone:TZ
    }, params));
    const res = await fetch('https://www.googleapis.com/calendar/v3/calendars/' + encodeURIComponent(CAL_ID) + '/events?' + q);
    if (!res.ok){
      let msg = 'HTTP ' + res.status;
      try { const j = await res.json(); if (j.error) msg += ': ' + j.error.message; } catch(_){}
      throw new Error(msg);
    }
    const j = await res.json();
    return (j.items || []).filter(e => e.status !== 'cancelled' && e.start).map(norm);
  }

  const SAMPLE = API_KEY ? [] : (function(){
    const out = []; let n = 0;
    const timed = (k, title, h1, m1, h2, m2, loc, desc) => out.push({
      id:'sample' + (n++), summary:title, location:loc, description:desc,
      start:{dateTime:atCentral(k, h1, m1).toISOString()}, end:{dateTime:atCentral(k, h2, m2).toISOString()}
    });
    const allDay = (k, title, desc) => out.push({
      id:'sample' + (n++), summary:title, description:desc, start:{date:k}, end:{date:addDays(k, 1)}
    });
    for (let i = -60; i <= 150; i++){
      const k = addDays(todayKey, i), dow = toUTC(k).getUTCDay(), wk = Math.floor((i + 700) / 7);
      if (dow === 2) timed(k, 'General meeting', 18, 0, 19, 30, 'Keller Hall', 'Weekly session. Bring a laptop.');
      if (dow === 4 && wk % 2 === 0) timed(k, 'Design review', 17, 0, 18, 0, 'Keller Hall', 'Bring whatever block you are working on.');
      if (dow === 5 && wk % 2 === 1) timed(k, 'ASIC Network call', 12, 0, 13, 0, 'Online', 'Biweekly call with the other chapters.');
    }
    timed(addDays(todayKey, 5), 'Place-and-route workshop', 13, 0, 16, 0, 'Keller Hall', 'Hands-on. You need a cluster account.');
    timed(addDays(todayKey, 12), 'Industry speaker', 18, 0, 19, 0, 'Keller Hall', '');
    allDay(addDays(todayKey, 26), 'Shuttle submission deadline', '');
    return out.map(norm);
  })();

  async function source(params){
    if (API_KEY) return api(params);
    const min = +new Date(params.timeMin);
    const max = params.timeMax ? +new Date(params.timeMax) : Infinity;
    return SAMPLE.filter(ev => +ev.end >= min && +ev.start < max);
  }

  async function loadMonth(y, m){
    const tag = y + '-' + m;
    if (loaded.has(tag)) return;
    loaded.add(tag);
    try {
      const first = new Date(Date.UTC(y, m, 1));
      const from = new Date(first); from.setUTCDate(1 - first.getUTCDay() - 1);
      const to = new Date(from); to.setUTCDate(to.getUTCDate() + 45);
      (await source({timeMin:from.toISOString(), timeMax:to.toISOString()})).forEach(ev => byId.set(ev.id, ev));
    } catch (err){
      loaded.delete(tag);   // let the next visit to this month retry
      throw err;
    }
  }

  async function loadUpcoming(){
    const evs = await source({timeMin:new Date().toISOString(), maxResults:String(UPCOMING)});
    evs.forEach(ev => byId.set(ev.id, ev));
    upcoming = evs.sort(cmp).slice(0, UPCOMING);
  }

  /* ---- rendering ---- */
  const monthTag = () => viewY + '-' + String(viewM + 1).padStart(2, '0');

  function renderGrid(){
    const first = new Date(Date.UTC(viewY, viewM, 1));
    el.month.textContent = monthFmt.format(first);
    let k = addDays(first.toISOString().slice(0,10), -first.getUTCDay());
    const frag = document.createDocumentFragment();

    for (let i = 0; i < 42; i++){
      const evs = eventsOn(k);
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'cal-cell';
      b.dataset.key = k;
      if (k.slice(0,7) !== monthTag()) b.classList.add('out');
      if (k === todayKey) b.classList.add('today');
      if (k === selected) b.classList.add('sel');
      if (evs.length) b.classList.add('has');
      b.setAttribute('aria-pressed', String(k === selected));
      b.setAttribute('aria-label', dayFmt.format(toUTC(k)) + (evs.length ? ', ' + evs.length + (evs.length > 1 ? ' events' : ' event') : ''));

      const num = document.createElement('span');
      num.className = 'cal-num';
      num.textContent = +k.slice(8);
      b.appendChild(num);

      evs.slice(0, 2).forEach(ev => {
        const c = document.createElement('span');
        c.className = 'cal-chip';
        if (!ev.allDay && ev.startKey === k){
          const t = document.createElement('span');
          t.className = 't';
          t.textContent = short(ev.start);
          c.appendChild(t);
        }
        c.appendChild(document.createTextNode(ev.title));
        b.appendChild(c);
      });
      if (evs.length > 2){
        const more = document.createElement('span');
        more.className = 'cal-more';
        more.textContent = '+' + (evs.length - 2) + ' more';
        b.appendChild(more);
      }
      if (evs.length){
        const dots = document.createElement('span');
        dots.className = 'cal-dots';
        for (let d = 0; d < Math.min(evs.length, 3); d++) dots.appendChild(document.createElement('i'));
        b.appendChild(dots);
      }

      frag.appendChild(b);
      k = addDays(k, 1);
    }
    gridEl.replaceChildren(frag);
  }

  function renderList(){
    const evs = selected ? eventsOn(selected) : upcoming;
    el.head.textContent = selected ? dayFmt.format(toUTC(selected)) : 'Upcoming';
    el.reset.hidden = !selected;

    const frag = document.createDocumentFragment();
    if (!evs.length){
      const li = document.createElement('li');
      li.className = 'cal-empty';
      li.textContent = selected ? 'Nothing on this day.' : 'Nothing scheduled yet.';
      frag.appendChild(li);
    }
    evs.forEach(ev => frag.appendChild(listItem(ev)));
    el.list.replaceChildren(frag);
  }

  function listItem(ev){
    const open = ev.id === openId;
    const li = document.createElement('li');

    const head = document.createElement('button');
    head.type = 'button';
    head.className = 'ev-head';
    head.dataset.id = ev.id;
    head.setAttribute('aria-expanded', String(open));

    const date = document.createElement('span'); date.className = 'ev-date';
    const dNum = document.createElement('b');     dNum.textContent = toUTC(ev.startKey).getUTCDate();
    const dMon = document.createElement('small'); dMon.textContent = monFmt.format(toUTC(ev.startKey));
    date.append(dNum, dMon);

    const main = document.createElement('span'); main.className = 'ev-main';
    const title = document.createElement('span'); title.className = 'ev-title'; title.textContent = ev.title;
    const meta = document.createElement('span');  meta.className = 'ev-meta';  meta.textContent = timeLabel(ev);
    main.append(title, meta);

    head.append(date, main);
    head.addEventListener('click', () => {
      openId = open ? null : ev.id;
      renderList();
      const again = el.list.querySelector('[data-id="' + CSS.escape(ev.id) + '"]');
      if (again) again.focus({preventScroll:true});
    });
    li.appendChild(head);

    if (open){
      const more = document.createElement('div');
      more.className = 'ev-more';
      if (ev.loc){
        const p = document.createElement('p'); p.className = 'ev-loc'; p.textContent = ev.loc; more.appendChild(p);
      }
      if (ev.desc){
        const p = document.createElement('p'); p.textContent = plain(ev.desc); more.appendChild(p);
      }
      if (ev.link){
        const a = document.createElement('a');
        a.href = ev.link; a.target = '_blank'; a.rel = 'noopener';
        a.textContent = 'Open in Google Calendar ↗';
        more.appendChild(a);
      }
      if (!more.childNodes.length){
        const p = document.createElement('p'); p.textContent = 'No details yet.'; more.appendChild(p);
      }
      li.appendChild(more);
    }
    return li;
  }

  function render(){ renderGrid(); renderList(); }

  function setStatus(msg){ el.status.textContent = msg; }
  const idleStatus = () => API_KEY ? '' : 'Showing sample events. Add an API key in the calendar script to load the real calendar.';

  async function showMonth(){
    render();
    if (!loaded.has(viewY + '-' + viewM)) setStatus('Loading…');
    try {
      await loadMonth(viewY, viewM);
      setStatus(idleStatus());
    } catch (err){
      console.warn('[SASi calendar]', err.message);
      setStatus('Couldn’t load events. Use the Google Calendar link above.');
    }
    render();
  }

  /* ---- controls ---- */
  function step(delta){
    viewM += delta;
    if (viewM < 0){ viewM = 11; viewY--; }
    if (viewM > 11){ viewM = 0; viewY++; }
    selected = null; openId = null;
    showMonth();
  }
  document.getElementById('calPrev').addEventListener('click', () => step(-1));
  document.getElementById('calNext').addEventListener('click', () => step(1));
  document.getElementById('calToday').addEventListener('click', () => {
    viewY = +todayKey.slice(0,4); viewM = +todayKey.slice(5,7) - 1;
    selected = null; openId = null;
    showMonth();
  });
  el.reset.addEventListener('click', () => { selected = null; openId = null; renderGrid(); renderList(); });

  gridEl.addEventListener('click', e => {
    const b = e.target.closest('.cal-cell');
    if (!b) return;
    const k = b.dataset.key;
    selected = selected === k ? null : k;
    openId = null;
    if (k.slice(0,7) !== monthTag()){
      // clicked a spill-over day from the next or previous month: go there
      viewY = +k.slice(0,4); viewM = +k.slice(5,7) - 1;
      showMonth();
    } else {
      render();
    }
    const again = gridEl.querySelector('[data-key="' + k + '"]');
    if (again) again.focus({preventScroll:true});
  });

  /* ---- first load ---- */
  (async function(){
    render();
    setStatus('Loading…');
    try {
      await Promise.all([loadUpcoming(), loadMonth(viewY, viewM)]);
      setStatus(idleStatus());
    } catch (err){
      console.warn('[SASi calendar]', err.message);
      setStatus('Couldn’t load events. Use the Google Calendar link above.');
    }
    render();
  })();
})();
