/* =====================================================================
   FORMS (join.html, sponsor.html)
   Each <form data-form="..."> posts to the SASi website backend, a Google
   Apps Script web app owned by SASI@umn.edu. Its source and the setup
   steps are in backend/.

   Paste the web app's /exec URL into BACKEND_URL. While it is empty the
   forms stay hidden and the pages keep their Google Form and email links
   (the elements marked data-when-live), so nothing on the site breaks.
   ===================================================================== */
(function(){
  'use strict';
  const BACKEND_URL = 'https://script.google.com/macros/s/AKfycbwyjNVdpCxf8THGkcGcT9pDd5KQZETqRKsSfA--9-DJe35cJndweCn2_77zLsMxr7HnhA/exec';   // "SASi website backend" in SASI@umn.edu

  const forms = Array.from(document.querySelectorAll('form[data-form]'));
  if (!forms.length) return;
  const live = /^https:\/\/script\.google\.com\/macros\/s\/[\w-]+\/exec$/.test(BACKEND_URL);
  const opened = Date.now();

  document.querySelectorAll('[data-when-live]').forEach(el => {
    if (live){ el.hidden = el.dataset.whenLive === 'hide'; }
  });
  document.querySelectorAll('[data-live-href]').forEach(a => {
    if (live){ a.href = a.dataset.liveHref; if (a.dataset.liveLabel) a.firstChild.textContent = a.dataset.liveLabel + ' '; }
  });
  if (!live) return;

  forms.forEach(form => {
    form.hidden = false;
    const status = form.querySelector('.form-status');
    const button = form.querySelector('button[type="submit"]');
    const fallback = form.dataset.fallback || 'mailto:SASI@umn.edu';

    form.addEventListener('input', e => clearError(e.target.closest('.field')));
    form.addEventListener('change', e => clearError(e.target.closest('.field')));

    form.addEventListener('submit', async e => {
      e.preventDefault();
      if (!checkFields(form)) return;
      const body = collect(form);
      body.form = form.dataset.form;
      body.elapsed = Date.now() - opened;

      setBusy(true);
      say('Sending…');
      try {
        // text/plain keeps this a "simple" request, so there is no CORS preflight,
        // which Apps Script can't answer.
        const res = await fetch(BACKEND_URL, {
          method: 'POST', body: JSON.stringify(body), redirect: 'follow',
          headers: {'Content-Type': 'text/plain;charset=utf-8'}
        });
        const out = await res.json();
        if (out.ok) return done(form);
        Object.entries(out.fields || {}).forEach(([k, msg]) => showError(form.querySelector('[name="' + k + '"]'), msg));
        say(out.error || 'Something went wrong.', true);
      } catch (err){
        console.warn('[SASi forms]', err);
        sayWithLink('Couldn’t reach the server.', fallback);
      }
      setBusy(false);
    });

    function setBusy(on){ button.disabled = on; form.setAttribute('aria-busy', on ? 'true' : 'false'); }
    function say(msg, bad){ status.textContent = msg; status.classList.toggle('bad', !!bad); }
    function sayWithLink(msg, href){
      status.textContent = msg + ' ';
      const a = document.createElement('a');
      a.className = 'link'; a.href = href;
      a.textContent = href.startsWith('mailto:') ? 'Email us instead' : 'Use the backup form';
      status.appendChild(a);
      status.classList.add('bad');
    }
  });

  /* ---- fields ---- */
  function collect(form){
    const out = {};
    new FormData(form).forEach((v, k) => {
      if (form.querySelectorAll('[name="' + k + '"][type="checkbox"]').length){
        (out[k] = out[k] || []).push(String(v));
      } else {
        out[k] = String(v).trim();
      }
    });
    return out;
  }

  function checkFields(form){
    let first = null;
    form.querySelectorAll('input, textarea').forEach(input => {
      if (input.type === 'checkbox' || input.type === 'radio' || input.classList.contains('hp-input')) return;
      if (input.value && input.value.trim() !== input.value) input.value = input.value.trim();
      if (input.validity.valid) return;
      let msg = 'Check this field.';
      if (input.validity.valueMissing) msg = 'Required.';
      else if (input.validity.patternMismatch && input.dataset.patternMessage) msg = input.dataset.patternMessage;
      else if (input.validity.typeMismatch) msg = 'Enter an email address.';
      else if (input.validity.tooLong) msg = 'That’s too long.';
      showError(input, msg);
      first = first || input;
    });
    if (first){ first.focus(); return false; }
    return true;
  }

  function showError(input, msg){
    if (!input) return;
    const field = input.closest('.field');
    if (!field) return;
    let err = field.querySelector('.err');
    if (!err){
      err = document.createElement('span');
      err.className = 'err';
      err.id = (input.id || input.name) + '-err';
      field.appendChild(err);
    }
    err.textContent = msg;
    field.classList.add('bad');
    input.setAttribute('aria-invalid', 'true');
    input.setAttribute('aria-describedby', err.id);
  }

  function clearError(field){
    if (!field || !field.classList.contains('bad')) return;
    field.classList.remove('bad');
    const err = field.querySelector('.err');
    if (err) err.textContent = '';
    field.querySelectorAll('[aria-invalid]').forEach(i => i.removeAttribute('aria-invalid'));
  }

  function done(form){
    const panel = document.createElement('div');
    panel.className = 'form-done';
    panel.tabIndex = -1;
    const h = document.createElement('h3');
    h.textContent = form.dataset.doneTitle || 'Thanks. Got it.';
    const p = document.createElement('p');
    p.textContent = form.dataset.doneText || '';
    panel.append(h, p);
    form.replaceWith(panel);
    panel.focus();
  }
})();
