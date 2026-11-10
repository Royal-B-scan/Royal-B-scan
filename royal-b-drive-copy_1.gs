const BASE = 'https://raw.githubusercontent.com/Royal-B-scan/Royal-B-scan/results/';
const FILES = ['data.json', 'scan.json', 'comeback.json'];
const FOLDER = 'Royal B data';
const NTFY = 'https://ntfy.sh/royalb-ryeb9g460y';

function copyResults() {
  const props = PropertiesService.getScriptProperties();
  const st = JSON.parse(UrlFetchApp.fetch(BASE + 'status.json?t=' + Date.now()).getContentText());
  const stamp = String(st.updated || '');
  if (stamp && stamp === props.getProperty('lastUpdated')) { Logger.log('No new screen since ' + stamp); return; }
  const folder = getFolder_();
  let scan = null;
  FILES.forEach(function (name) {
    const res = UrlFetchApp.fetch(BASE + name + '?t=' + Date.now(), { muteHttpExceptions: true });
    if (res.getResponseCode() !== 200) throw new Error(name + ': GitHub answered ' + res.getResponseCode());
    if (name === 'scan.json') scan = JSON.parse(res.getContentText());
    const text = Utilities.base64Encode(Utilities.gzip(res.getBlob()).getBytes());
    const fname = name + '.gz.b64';
    const it = folder.getFilesByName(fname);
    const file = it.hasNext() ? it.next() : folder.createFile(fname, '', MimeType.PLAIN_TEXT);
    file.setContent(text);
  });
  props.setProperty('lastUpdated', stamp);
  Logger.log('Copied the screen from ' + stamp);
  try { sendBullish_(st); } catch (e) { Logger.log('Bullish alert failed: ' + e); }
  try { sendSummary_(st, scan); } catch (e) { Logger.log('Summary failed: ' + e); }
}

function sendTestSummary() {
  const st = JSON.parse(UrlFetchApp.fetch(BASE + 'status.json?t=' + Date.now()).getContentText());
  const scan = JSON.parse(UrlFetchApp.fetch(BASE + 'scan.json?t=' + Date.now()).getContentText());
  sendSummary_(st, scan);
}

/* Nov 9 (Taylor): a Comeback Turn (the ROP move) is the number-one alert. Its own push, urgent priority, sent before the daily summary. */
function sendBullish_(st) {
  const T = st.comeback_turn || [];
  if (!T.length) return;
  const day = Utilities.formatDate(new Date(String(st.last_bar || st.date) + 'T12:00:00Z'), 'America/Vancouver', 'EEE MMM d');
  const lines = T.map(function (x) {
    return x.ticker + ' ' + x.close + (x.currency === 'CAD' ? ' CAD' : '') + ' · stop ~' + x.stop + (x.quality === false ? ' · failed the business check' : '');
  });
  const body = lines.join('\n') + '\nFirst close back above the 20-day after an oversold low (the ROP move). Starter size, wait 15-30 min after the open, hold winners to the 50-day exit.';
  UrlFetchApp.fetch(NTFY, { method: 'post', payload: body,
    headers: { Title: 'BULLISH TURN ' + day + ': ' + T.map(function (x) { return x.ticker; }).join(', '), Priority: 'urgent', Tags: 'rotating_light,chart_with_upwards_trend' },
    muteHttpExceptions: true });
}

function sendTestBullish() {
  sendBullish_({ date: Utilities.formatDate(new Date(), 'America/Vancouver', 'yyyy-MM-dd'),
    comeback_turn: [{ ticker: 'TEST', close: 100, stop: 92, quality: true, currency: 'USD' }] });
}

function sendSummary_(st, scan) {
  const c = st.counts || {};
  const day = Utilities.formatDate(new Date(String(st.last_bar || st.date) + 'T12:00:00Z'), 'America/Vancouver', 'EEE MMM d');
  const notEtf = function (s) { return s.kind !== 'ETF'; };
  const er = function (s) { const e = s.earnings; return e && e.days != null && e.days >= 0 && e.days <= 21 ? ' · earnings ' + (e.days === 0 ? 'today' : 'in ' + e.days + 'd') : ''; };
  const line = function (s) { return s.ticker + ' (' + s.name + ')' + er(s); };
  const top5 = ((scan.top5 || {}).rows || []);
  const turns = st.comeback_turn || [];
  const crossed = (scan.stocks || []).filter(notEtf).filter(function (s) { return /^TRIGGER/.test(s.status || '') && !s.obv_skip; });
  const almost = (scan.stocks || []).filter(notEtf).filter(function (s) { return s.status === 'HEADS-UP'; });
  const moved = st.comeback_moved_up || [];
  const probs = Object.keys(st.problems || {});
  const body = [
    'Royal B · screen for ' + day, '',
    turns.length ? 'BULLISH TURN (number one): ' + turns.map(function (x) { return x.ticker + ' ' + x.close + ' (stop ~' + x.stop + ')'; }).join(', ') : '',
    turns.length ? '' : '',
    'Top 5 (calmest first, every screener):'
  ].concat(top5.length ? top5.map(function (x, i) { return '  ' + (i + 1) + '. ' + x.ticker + ' (' + x.name + ') · ' + (x.source_names || []).join(' + ') + (x['new'] ? ' · new' : ''); }) : ['  none today'])
   .concat(['',
    'Early Turn: ' + (c.early_breakout || 0) + ' breakouts · ' + (c.early_pullback || 0) + ' pullbacks',
    'Trend Cross: ' + crossed.length + ' crossed' + (crossed.length ? ' (' + crossed.slice(0, 5).map(function (s) { return s.ticker; }).join(', ') + ')' : '') +
      (c.obv_skip ? ' · ' + c.obv_skip + ' skipped (flat OBV)' : '') +
      ' · ' + almost.length + ' almost' + (almost.length ? ' (' + almost.slice(0, 5).map(function (s) { return s.ticker; }).join(', ') + ')' : ''),
    moved.length ? 'Comebacks moved up a stage: ' + moved.join(', ') : 'No Comebacks moved up today.',
    probs.length ? 'Problem in the screen: ' + probs.join(', ') + '. Open the page for details.' : '',
    '', 'Check InvestorLine’s live quote before buying.'
  ]).filter(function (x, i, a) { return x !== '' || (i > 0 && a[i - 1] !== ''); }).join('\n');
  const subject = 'Royal B ' + day + ': ' + (turns.length ? 'BULLISH TURN ' + turns.map(function (x) { return x.ticker; }).join(', ') + ' · ' : '') +
    'Top 5 ' + (top5.length ? top5.map(function (x) { return x.ticker; }).join(', ') : 'none');
  MailApp.sendEmail(Session.getEffectiveUser().getEmail(), subject, body);
  const push = (top5.length ? 'Top 5: ' + top5.map(function (x) { return x.ticker; }).join(', ') + '. ' : 'No Top 5 today. ') +
    crossed.length + ' crossed, ' + almost.length + ' almost.' +
    (moved.length ? ' Comebacks up: ' + moved.join(', ') + '.' : '') + (probs.length ? ' Screen problem: open the page.' : '');
  UrlFetchApp.fetch(NTFY, { method: 'post', payload: push, headers: { Title: 'Royal B ' + day, Tags: 'crown' }, muteHttpExceptions: true });
}

function setupHourly() {
  ScriptApp.getProjectTriggers().forEach(function (t) { ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger('copyResults').timeBased().everyHours(1).create();
}

function getFolder_() {
  const it = DriveApp.getFoldersByName(FOLDER);
  return it.hasNext() ? it.next() : DriveApp.createFolder(FOLDER);
}
