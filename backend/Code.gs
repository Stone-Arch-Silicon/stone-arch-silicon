/**
 * @OnlyCurrentDoc
 *
 * =====================================================================
 * Stone Arch Silicon website backend
 *
 * A Google Apps Script web app, owned by SASI@umn.edu and bound to the
 * "SASi website" Google Sheet. Nothing is self-hosted: GitHub Pages serves
 * the site, Google runs this script, and the Sheet stores the rows.
 *
 *   POST {form: "join" | "sponsor", ...fields}
 *        Checks the fields, adds one row to that form's tab, and emails
 *        the board. Answers {ok: true}, or {ok: false, error, fields}.
 *   GET  Answers {ok: true}, so you can check that a deployment is live.
 *
 * Visitors can only add rows. Nothing here reads the Sheet back out, so
 * the web app can't leak what other people sent. Setup steps and the
 * security notes are in backend/README.md.
 * =====================================================================
 */

const CONFIG = {
  notify: 'SASI@umn.edu',   // gets one email per submission
  minFillMs: 1500,          // a form filled faster than this is a bot
  perEmailSeconds: 600,     // one submission per address per form per 10 minutes
  perHour: 60               // all forms together; keeps spam off the mail quota
};

const FORMS = {
  join: {
    tab: 'Join',
    subject: r => 'SASi sign-up: ' + r.name,
    fields: [
      {key: 'name', label: 'Name', max: 100, required: true, noLinks: true},
      {key: 'email', label: 'UMN email', max: 100, required: true, check: 'umn'},
      {key: 'major', label: 'Major', max: 100, noLinks: true},
      {key: 'year', label: 'Year', max: 40,
        oneOf: ['First year', 'Second year', 'Third year', 'Fourth year', 'Fifth year or more', 'Graduate student']},
      {key: 'subteams', label: 'Subteams', max: 200,
        someOf: ['Physical Design', 'RTL', 'Verification', 'Analog', 'Not sure yet']},
      {key: 'path', label: 'Way in', max: 40,
        oneOf: ['Coursework', 'ASIC 101', 'Portfolio', 'A conversation', 'Not sure yet']},
      {key: 'note', label: 'Anything else', max: 2000, multiline: true}
    ]
  },
  sponsor: {
    tab: 'Sponsors',
    subject: r => 'Sponsorship inquiry: ' + r.org,
    fields: [
      {key: 'name', label: 'Name', max: 100, required: true, noLinks: true},
      {key: 'email', label: 'Email', max: 120, required: true, check: 'email'},
      {key: 'org', label: 'Organization', max: 120, required: true, noLinks: true},
      {key: 'role', label: 'Role', max: 100, noLinks: true},
      {key: 'support', label: 'Interested in', max: 300,
        someOf: ['Funding', 'EDA licenses', 'PDK access', 'Shuttle slots', 'Hardware', 'Mentors or speakers', 'Recruiting']},
      {key: 'message', label: 'Message', max: 4000, multiline: true}
    ]
  }
};

const EMAIL_RE = /^[^\s@<>()",;:]+@[^\s@<>()",;:]+\.[^\s@<>()",;:]{2,}$/;
const UMN_RE = /^[A-Za-z0-9._%+-]+@umn\.edu$/i;
const LINK_RE = /https?:|www\.|<|>/i;


/* ------------------------------------------------------------------ web */

function doGet() {
  return reply_({ok: true, forms: Object.keys(FORMS)});
}

function doPost(e) {
  let body;
  try {
    body = JSON.parse((e && e.postData && e.postData.contents) || '{}');
  } catch (err) {
    return reply_({ok: false, error: 'Could not read the form.'});
  }
  const form = FORMS[body.form];
  if (!form) return reply_({ok: false, error: 'Unknown form.'});

  // Bots: people never see the "website" field, and people take a moment.
  // Answering ok means the bot learns nothing.
  if (body.website) return reply_({ok: true});
  if (!(Number(body.elapsed) >= CONFIG.minFillMs)) {
    return reply_({ok: false, error: 'That was very fast. Please try again.'});
  }

  const checked = check_(form, body);
  if (checked.errors) {
    return reply_({ok: false, error: 'Please fix the highlighted fields.', fields: checked.errors});
  }
  const r = checked.record;

  const cache = CacheService.getScriptCache();
  const who = 'seen:' + body.form + ':' + r.email.toLowerCase();
  if (cache.get(who)) {
    return reply_({ok: false, error: 'We already have this one. If something changed, email ' + CONFIG.notify + '.'});
  }

  const lock = LockService.getScriptLock();
  if (!lock.tryLock(10000)) return reply_({ok: false, error: 'Busy right now. Please try again in a minute.'});
  try {
    const hour = 'hour:' + Utilities.formatDate(new Date(), 'UTC', 'yyyyMMddHH');
    const count = Number(cache.get(hour) || 0);
    if (count >= CONFIG.perHour) {
      return reply_({ok: false, error: 'We are getting a lot of messages. Please email ' + CONFIG.notify + ' instead.'});
    }
    cache.put(hour, String(count + 1), 3600);
    tab_(form).appendRow([new Date()].concat(form.fields.map(f => asText_(r[f.key]))));
    cache.put(who, '1', CONFIG.perEmailSeconds);
  } finally {
    lock.releaseLock();
  }

  notify_(form, r);   // the row is saved either way; a mail hiccup shouldn't fail the visitor
  return reply_({ok: true});
}


/* ------------------------------------------------------------- helpers */

function check_(form, body) {
  const record = {};
  const errors = {};
  form.fields.forEach(f => {
    let v = body[f.key];
    if (Array.isArray(v)) v = v.join(', ');
    v = v == null ? '' : String(v);
    v = f.multiline ? v.replace(/\r\n?/g, '\n').trim() : v.replace(/\s+/g, ' ').trim();
    if (f.max && v.length > f.max) errors[f.key] = 'Keep this under ' + f.max + ' characters.';
    else if (f.required && !v) errors[f.key] = 'Required.';
    else if (v && f.check === 'email' && !EMAIL_RE.test(v)) errors[f.key] = 'Enter an email address.';
    else if (v && f.check === 'umn' && !UMN_RE.test(v)) errors[f.key] = 'Use your x500@umn.edu address.';
    else if (v && f.noLinks && LINK_RE.test(v)) errors[f.key] = 'No links here, please.';
    else if (v && f.oneOf && f.oneOf.indexOf(v) < 0) errors[f.key] = 'Pick one of the options.';
    else if (v && f.someOf && v.split(/\s*,\s*/).some(x => f.someOf.indexOf(x) < 0)) errors[f.key] = 'Pick from the options.';
    record[f.key] = v;
  });
  return Object.keys(errors).length ? {errors: errors} : {record: record};
}

// A cell that starts with = + - or @ would run as a formula. The leading
// apostrophe makes Sheets keep it as plain text, and it isn't displayed.
function asText_(v) {
  v = v == null ? '' : String(v);
  return /^[=+\-@\t\r]/.test(v) ? "'" + v : v;
}

function tab_(form) {
  const book = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = book.getSheetByName(form.tab);
  if (!sheet) {
    sheet = book.insertSheet(form.tab);
    const head = ['Received'].concat(form.fields.map(f => f.label));
    sheet.getRange(1, 1, 1, head.length).setValues([head]).setFontWeight('bold');
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function notify_(form, r) {
  try {
    const lines = form.fields.map(f => f.label + ': ' + (r[f.key] || '-'));
    MailApp.sendEmail({
      to: CONFIG.notify,
      replyTo: r.email,
      subject: form.subject(r).replace(/[\r\n]+/g, ' ').slice(0, 150),
      body: lines.join('\n') + '\n\nSaved in the "' + form.tab + '" tab of ' +
        SpreadsheetApp.getActiveSpreadsheet().getUrl() + '\n'
    });
  } catch (err) {
    console.error('Notification email failed: ' + err);
  }
}

function reply_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}


/* ------------------------------------------------- run these by hand */

// Run once from the editor: makes the tabs and asks for permission.
function setup() {
  Object.keys(FORMS).forEach(k => tab_(FORMS[k]));
  const book = SpreadsheetApp.getActiveSpreadsheet();
  const blank = book.getSheetByName('Sheet1');
  if (blank && book.getSheets().length > 1 && blank.getLastRow() === 0) book.deleteSheet(blank);
  console.log('Tabs ready: ' + Object.keys(FORMS).map(k => FORMS[k].tab).join(', '));
}

// Sends one fake sign-up through the same path a visitor's would take.
// Delete the test row afterwards.
function testJoin() {
  CacheService.getScriptCache().remove('seen:join:test.student@umn.edu');
  const out = doPost({postData: {contents: JSON.stringify({
    form: 'join', name: 'Test Student', email: 'test.student@umn.edu', year: 'Second year',
    subteams: ['RTL', 'Verification'], path: 'ASIC 101', note: '=1+1 should stay text', elapsed: 5000
  })}});
  console.log(out.getContent());
}
