/* Orionfold Arena — demo-mode bootstrap (classic, render-blocking).
 *
 * Loaded as `<script is:inline src=".../arena-demo/boot.js">` in <head> of the
 * ARENA_DEMO bundle. Being a classic blocking script it runs DURING parse,
 * BEFORE any body island module OR the TelemetryRail `is:inline` script — so
 * window.fetch / window.EventSource are already shimmed when those run, and
 * window.__ARENA_DEMO__ is set so the inline scripts skip their "public mirror
 * → offline" short-circuit.
 *
 * It makes the cockpit fully interactive with NO sidecar: chat/compare replay
 * curated real DGX Spark runs (token cadence synthesized from measured tok/s),
 * telemetry plays a synthetic trace overlaid with the live tok/s during a
 * replay, and the read-only endpoints (lanes, benches, activity…) are served
 * from sanitized stubs. 100% static. See `fieldkit arena record`.
 */
(function () {
  'use strict';
  if (typeof window === 'undefined' || window.__ARENA_DEMO_BOOTED__) return;
  window.__ARENA_DEMO_BOOTED__ = true;
  window.__ARENA_DEMO__ = true; // inline scripts read this to skip offline

  // ----- resolve fixtures URL from this script's own location ---------------
  var self = document.currentScript && document.currentScript.src;
  var FIXTURE_URL = self
    ? self.replace(/boot\.js(\?.*)?$/, 'fixtures.json')
    : '/arena/demo/arena-demo/fixtures.json';

  var fixtures = { chat: [], compare: [], telemetry: null, stubs: {} };
  var bus = { inflight: false, tokPerS: null, laneId: null, until: 0 };
  // Knowledge pane (Orionfold Cortex) replay state. The pane polls /api/knowledge
  // every 5s, so a "rebuild" is a before→after flip: clicking it backfills
  // provenance + scores recall, and the next poll renders the green state.
  var kb = { rebuilt: false };

  // ----- helpers ------------------------------------------------------------
  function pathOf(url) {
    try { return (new URL(url, location.origin).pathname || '/').replace(/\/+$/, '') || '/'; }
    catch (e) { return String(url); }
  }
  function norm(s) { return (s || '').trim().toLowerCase().replace(/\s+/g, ' '); }

  function bestMatch(list, prompt) {
    if (!list || !list.length) return null;
    var p = norm(prompt);
    if (!p) return list[0];
    var hit = list.find(function (f) { return norm(f.prompt) === p; });
    if (hit) return hit;
    hit = list.find(function (f) { return norm(f.prompt).indexOf(p) >= 0 || p.indexOf(norm(f.prompt)) >= 0; });
    if (hit) return hit;
    var pt = p.split(' '), best = null, bestScore = 0;
    list.forEach(function (f) {
      var ft = norm(f.prompt).split(' '), o = 0;
      pt.forEach(function (w) { if (ft.indexOf(w) >= 0) o++; });
      if (o > bestScore) { bestScore = o; best = f; }
    });
    return best || list[0];
  }

  function fallbackChatEvents() {
    var text = 'This is a recorded demo of Orionfold Arena, replaying real sessions ' +
      'captured on a DGX Spark. Pick one of the suggested prompts to watch a real ' +
      'run stream back — or run the cockpit live on your own Spark with ' +
      '`pip install fieldkit[arena]` then `fieldkit arena up`.';
    var ev = [{ t: 0, event: 'start', data: { session_id: 'demo', model: 'Orionfold Arena (demo)', base_url: 'demo', lane_id: 'demo', context_length: 0 } }];
    var t = 180, units = text.match(/\s+|\S+/g) || [];
    units.forEach(function (u) { ev.push({ t: t, event: 'token', data: { channel: 'content', text: u } }); t += 24; });
    ev.push({ t: t + 30, event: 'done', data: { ttft_ms: 180, tok_per_s: 42, tokens_out: 64, turn_id: -1, finish_reason: 'stop' } });
    return ev;
  }

  // Build a streaming Response that emits SSE frames on the recorded schedule.
  function sseResponse(events, signal) {
    var enc = new TextEncoder();
    var doneEv = null;
    for (var k = events.length - 1; k >= 0; k--) { if (/^done/.test(events[k].event)) { doneEv = events[k]; break; } }
    var rep = (doneEv && doneEv.data && doneEv.data.tok_per_s) || 60;
    var ttft = (doneEv && doneEv.data && doneEv.data.ttft_ms) || null;
    var laneId = (events[0] && events[0].data && events[0].data.lane_id) || null;

    var stream = new ReadableStream({
      start: function (controller) {
        var i = 0, timer = null, t0 = performance.now();
        bus.inflight = true; bus.tokPerS = rep; bus.ttftMs = ttft; bus.laneId = laneId;
        function finish() { bus.inflight = false; bus.until = performance.now() + 2500; try { controller.close(); } catch (e) {} }
        function onAbort() { if (timer) clearTimeout(timer); bus.inflight = false; try { controller.error(new DOMException('Aborted', 'AbortError')); } catch (e) {} }
        if (signal) { if (signal.aborted) return onAbort(); signal.addEventListener('abort', onAbort, { once: true }); }
        function step() {
          if (i >= events.length) return finish();
          var ev = events[i++];
          var wait = Math.max(0, ev.t - (performance.now() - t0));
          timer = setTimeout(function () {
            if (signal && signal.aborted) return;
            try { controller.enqueue(enc.encode('event: ' + ev.event + '\ndata: ' + JSON.stringify(ev.data) + '\n\n')); }
            catch (e) { return; }
            step();
          }, wait);
        }
        step();
      }
    });
    return new Response(stream, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
  }

  function jsonResponse(obj, status) {
    return new Response(JSON.stringify(obj == null ? {} : obj), {
      status: status || 200,
      headers: { 'Content-Type': 'application/json' }
    });
  }

  // ----- knowledge (Cortex) replay helpers ----------------------------------
  function knowledgeState() {
    var k = fixtures.knowledge;
    if (!k) return {};                         // no fixtures → pane shows degraded
    return kb.rebuilt ? (k.after || {}) : (k.before || k.after || {});
  }
  function knowledgeQuery(body) {
    var k = fixtures.knowledge || {};
    var qlist = k.queries || [];
    if (!qlist.length) return { query: (body && body.query) || '', provenance: null, hits: [] };
    // reuse the chat/compare prompt matcher by exposing each query as `.prompt`
    var chosen = bestMatch(qlist.map(function (x) {
      return { prompt: x.query, query: x.query, hits: x.hits || [], provenance: x.provenance || null };
    }), body && body.query) || { query: qlist[0].query, hits: qlist[0].hits || [] };
    return {
      query: (body && body.query) || chosen.query,
      provenance: (body && body.provenance) || null,
      hits: chosen.hits || []
    };
  }

  // ----- fetch shim ---------------------------------------------------------
  var realFetch = window.fetch ? window.fetch.bind(window) : null;
  window.fetch = function (input, init) {
    init = init || {};
    var url = typeof input === 'string' ? input : (input && input.url) || '';
    var path = pathOf(url);
    var method = (init.method || (input && input.method) || 'GET').toUpperCase();

    if (/\/api\/chat\/stream$/.test(path)) {
      var body = {}; try { body = init.body ? JSON.parse(init.body) : {}; } catch (e) {}
      var fc = bestMatch(fixtures.chat, body.prompt);
      return Promise.resolve(sseResponse(fc ? fc.events : fallbackChatEvents(), init.signal));
    }
    if (/\/api\/compare\/stream$/.test(path)) {
      var cbody = {}; try { cbody = init.body ? JSON.parse(init.body) : {}; } catch (e) {}
      var cc = bestMatch(fixtures.compare, cbody.prompt);
      return Promise.resolve(sseResponse(cc ? cc.events : fallbackChatEvents(), init.signal));
    }

    // knowledge pane (Cortex) — poll-driven before→after + query replay
    if (/\/api\/knowledge\/reindex$/.test(path)) {
      kb.rebuilt = false;                       // restart the before→after transition
      setTimeout(function () { kb.rebuilt = true; }, 2600); // next poll renders green
      return Promise.resolve(jsonResponse({ ok: true, job_id: 'demo-reindex', status: 'queued', demo: true }));
    }
    if (/\/api\/knowledge\/rag-eval$/.test(path)) {
      kb.rebuilt = true;                         // scoring implies a stamped, evaluated index
      return Promise.resolve(jsonResponse({ ok: true, job_id: 'demo-rageval', status: 'queued', demo: true }));
    }
    if (/\/api\/knowledge\/query$/.test(path)) {
      var qb = {}; try { qb = init.body ? JSON.parse(init.body) : {}; } catch (e) {}
      return Promise.resolve(jsonResponse(knowledgeQuery(qb)));
    }
    if (/\/api\/knowledge$/.test(path)) {
      return Promise.resolve(jsonResponse(knowledgeState()));
    }

    // canned read-only stubs (exact path)
    var stubs = fixtures.stubs || {};
    if (stubs[path] !== undefined) return Promise.resolve(jsonResponse(stubs[path]));

    // known endpoint families → benign defaults so islands don't error
    if (/^\/healthz$/.test(path)) return Promise.resolve(jsonResponse(stubs['/healthz'] || { ok: true }));
    if (/\/api\/(activity)$/.test(path)) return Promise.resolve(jsonResponse({ events: [] }));
    if (/\/api\/(chat\/sessions|lab\/notes)$/.test(path)) return Promise.resolve(jsonResponse(path.indexOf('notes') >= 0 ? { notes: [] } : { sessions: [] }));
    if (/\/api\/rubrics$/.test(path)) return Promise.resolve(jsonResponse(stubs['/api/rubrics'] || { rubrics: [] }));
    if (/\/api\/eval\/benches/.test(path)) return Promise.resolve(jsonResponse(stubs['/api/eval/benches'] || { benches: [] }));
    if (/\/api\/lanes$/.test(path)) return Promise.resolve(jsonResponse(stubs['/api/lanes'] || {}));
    if (/\/api\/compare\/options$/.test(path)) return Promise.resolve(jsonResponse(stubs['/api/compare/options'] || {}));
    if (/\/api\//.test(path)) {
      // POSTs (score, local/load, prefs, lab note create, …) → benign OK
      return Promise.resolve(jsonResponse(method === 'GET' ? {} : { ok: true, demo: true }));
    }
    // everything else (static assets, fixtures.json itself) → real network
    return realFetch ? realFetch(input, init) : Promise.reject(new Error('no fetch'));
  };

  // ----- EventSource shim (telemetry) --------------------------------------
  var RealES = window.EventSource;
  function DemoES(url) {
    if (!/\/api\/telemetry\/stream/.test(String(url)) && RealES) return new RealES(url);
    this.url = String(url); this.readyState = 1; this._l = {}; this._timer = null;
    var self = this, i = 0;
    function tick() {
      var tel = fixtures.telemetry || { samples: [], inflight_profile: {} };
      var prof = tel.inflight_profile || {};
      var samples = tel.samples || [];
      var base = samples.length ? Object.assign({}, samples[i % samples.length].data) : {};
      var active = bus.inflight || performance.now() < bus.until;
      if (active) {
        var g = prof.gpu_util || [88, 99], tp = prof.gpu_temp_c || [68, 79], wob = (i % 6) / 6;
        base.gpu_util = Math.round((g[0] + (g[1] - g[0]) * (0.4 + 0.6 * wob)) * 10) / 10;
        base.gpu_temp_c = Math.round((tp[0] + (tp[1] - tp[0]) * wob) * 10) / 10;
        if (typeof base.unified_used_gb === 'number') base.unified_used_gb = Math.round((base.unified_used_gb + (prof.mem_bump_gb || 2)) * 100) / 100;
        base.inflight = bus.inflight; base.tok_per_s = bus.tokPerS; base.ttft_ms = bus.ttftMs; base.lane_id = bus.laneId;
      }
      base.ts = new Date().toISOString();
      self._emit('telemetry', base);
      i++;
    }
    tick();
    this._timer = setInterval(tick, 500);
  }
  DemoES.prototype.addEventListener = function (t, cb) { (this._l[t] = this._l[t] || []).push(cb); };
  DemoES.prototype.removeEventListener = function (t, cb) { this._l[t] = (this._l[t] || []).filter(function (f) { return f !== cb; }); };
  DemoES.prototype._emit = function (t, obj) {
    var ev = { data: JSON.stringify(obj) };
    (this._l[t] || []).forEach(function (cb) { try { cb(ev); } catch (e) {} });
    if (t === 'message' && typeof this.onmessage === 'function') this.onmessage(ev);
  };
  DemoES.prototype.close = function () { this.readyState = 2; if (this._timer) clearInterval(this._timer); };
  window.EventSource = DemoES;

  // ----- DEMO ribbon --------------------------------------------------------
  function ribbon() {
    if (document.getElementById('arena-demo-ribbon')) return;
    var s = document.createElement('style');
    s.textContent = '#arena-demo-ribbon{position:fixed;bottom:0;left:0;right:0;z-index:9999;' +
      'font:500 12px/1.4 var(--font-mono,monospace);background:var(--color-primary-dim,#3b4a86);' +
      'color:#fff;padding:6px 14px;text-align:center;box-shadow:0 -2px 12px rgba(0,0,0,.35)}' +
      '#arena-demo-ribbon strong{letter-spacing:.12em;margin-right:.5em}' +
      '#arena-demo-ribbon code{background:rgba(255,255,255,.16);padding:1px 5px;border-radius:4px}';
    var el = document.createElement('div');
    el.id = 'arena-demo-ribbon'; el.setAttribute('role', 'note');
    el.innerHTML = '<strong>DEMO</strong> recorded on a DGX Spark — chat &amp; compare replay real sessions. ' +
      'Run it live: <code>pip install fieldkit[arena]</code>' +
      ' &nbsp;·&nbsp; <a href="https://orionfold.com" target="_blank" rel="noopener" style="color:#fff;text-decoration:underline">Sponsor this project on Orionfold &#8599;</a>';
    document.head.appendChild(s);
    (document.body || document.documentElement).appendChild(el);
  }
  // ----- demo coach: a Discord-style pulse on the next interactive target ---
  // The sidecar-less demo is self-guiding: a blurple "ping" ring pulses on the
  // element to click next (rebuild → query on Cortex; a suggested prompt on
  // chat/compare) and clears the moment the visitor interacts with it.
  function coachFind(sel, txt) {
    var t = (txt || '').toLowerCase();
    var els = [].slice.call(document.querySelectorAll(sel));
    for (var k = 0; k < els.length; k++) {
      if (!t || (els[k].textContent || '').trim().toLowerCase().indexOf(t) >= 0) return els[k];
    }
    return null;
  }
  function demoCoach() {
    if (!document.getElementById('arena-demo-coach-style')) {
      var s = document.createElement('style');
      s.id = 'arena-demo-coach-style';
      s.textContent =
        '@keyframes arena-coach-ping{' +
        '0%{box-shadow:0 0 0 0 rgba(124,140,255,.55),0 0 0 2px rgba(124,140,255,.95)}' +
        '70%{box-shadow:0 0 0 12px rgba(124,140,255,0),0 0 0 2px rgba(124,140,255,.95)}' +
        '100%{box-shadow:0 0 0 0 rgba(124,140,255,0),0 0 0 2px rgba(124,140,255,.95)}}' +
        '.arena-demo-coach{animation:arena-coach-ping 1.5s ease-out infinite;border-radius:8px;position:relative;z-index:2}' +
        '@media (prefers-reduced-motion:reduce){.arena-demo-coach{animation:none;outline:2px solid rgba(124,140,255,.9);outline-offset:2px}}';
      document.head.appendChild(s);
    }
    // Ordered steps per screen: find the target, the event that completes it,
    // and a settle delay before pulsing the next one (lets async state land).
    var plans = {
      cortex: [
        { get: function () { return coachFind('button.kp__go', 'rebuild'); }, done: 'click', settle: 3400 },
        { get: function () { return document.querySelector('.kp__input'); },  done: 'focus', settle: 0 }
      ],
      chat:    [{ get: function () { return document.querySelector('.chat-prompt-chip'); }, done: 'click', settle: 0 }],
      compare: [{ get: function () { return document.querySelector('.chat-prompt-chip'); }, done: 'click', settle: 0 }]
    };
    var page = location.pathname.replace(/\/+$/, '');
    var key = null, ks = Object.keys(plans);
    for (var n = 0; n < ks.length; n++) { if (page.slice(-(ks[n].length + 1)) === '/' + ks[n]) { key = ks[n]; break; } }
    if (!key) return;
    var steps = plans[key], i = 0, cur = null;
    function clear() { if (cur) { cur.el.classList.remove('arena-demo-coach'); try { cur.el.removeEventListener(cur.ev, cur.fn); } catch (e) {} cur = null; } }
    function run() {
      clear();
      if (i >= steps.length) return;
      var step = steps[i];
      if (!step._deadline) step._deadline = performance.now() + 9000;
      var el = step.get();
      if (!el || el.disabled) { if (performance.now() < step._deadline) setTimeout(run, 350); return; }
      el.classList.add('arena-demo-coach');
      var fn = function () { el.classList.remove('arena-demo-coach'); try { el.removeEventListener(step.done, fn); } catch (e) {} cur = null; i++; setTimeout(run, step.settle || 300); };
      el.addEventListener(step.done, fn, { once: true });
      cur = { el: el, ev: step.done, fn: fn };
    }
    setTimeout(run, 900); // let the Preact islands hydrate first
  }

  function onReady() { ribbon(); demoCoach(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', onReady, { once: true });
  else onReady();

  // ----- load fixtures (async; shims read the mutable ref) ------------------
  (realFetch || fetch)(FIXTURE_URL)
    .then(function (r) { return r && r.ok ? r.json() : null; })
    .then(function (d) { if (d) { fixtures = d; window.__ARENA_DEMO_FIXTURES__ = d; } })
    .catch(function (e) { try { console.warn('[arena demo] fixtures load failed', e); } catch (x) {} });
})();
