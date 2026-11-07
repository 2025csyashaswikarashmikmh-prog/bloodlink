/* RaktaSetu frontend — vanilla JS single-page app (no build step). */
(() => {
  'use strict';

  // ------------------------------------------------------------------ state
  const mem = {};
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch { return mem[k] ?? null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { mem[k] = v; } },
    del(k) { try { localStorage.removeItem(k); } catch { delete mem[k]; } },
  };
  const S = {
    lang: store.get('rs_lang'),
    token: store.get('rs_token'),
    user: JSON.parse(store.get('rs_user') || 'null'),
    voiceOn: store.get('rs_voice') !== 'off',
    handsFree: store.get('rs_handsfree') === 'on',
    sid: null, chat: [], chips: [], slots: {}, step: null, inputHint: 'text', demoOtp: null,
    meta: null, coords: null, sockets: [], timers: [], charts: [], map: null,
  };

  const rawBase = window.__API_BASE__ || '';
  const API = rawBase.startsWith('__PORT_') ? '' : rawBase.replace(/\/$/, '');
  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const T = (k) => window.tr(k, S.lang || 'en');
  const fmtTime = (iso) => iso ? new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '';
  const fmtDT = (iso) => iso ? new Date(iso).toLocaleString([], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '';

  const ICON = {
    mic: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 17v5M8 22h8"/></svg>',
    stop: '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="2"/></svg>',
    drop: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C9 7 5 10.5 5 15a7 7 0 0 0 14 0c0-4.5-4-8-7-13z"/></svg>',
    speaker: '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M11 5 6 9H3v6h3l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13"/></svg>',
    hospital: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 21V5a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v16M9 21v-4h6v4M12 7v6M9 10h6"/></svg>',
    clock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
    hash: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 9h16M4 15h16M10 3 8 21M16 3l-2 18"/></svg>',
    user: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>',
    pin: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s7-6.5 7-12a7 7 0 0 0-14 0c0 5.5 7 12 7 12z"/><circle cx="12" cy="10" r="2.5"/></svg>',
  };

  // ------------------------------------------------------------------ api
  async function api(path, { method = 'GET', body, auth = true } = {}) {
    const headers = { 'Content-Type': 'application/json' };
    if (auth && S.token) headers.Authorization = `Bearer ${S.token}`;
    const res = await fetch(`${API}${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401 && S.token && path !== '/api/auth/verify-otp') { setSession(null, null); }
    if (!res.ok) throw new Error(data.detail ? (typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)) : `HTTP ${res.status}`);
    return data;
  }

  function wsUrl(params) {
    const u = new URL(`${API}/ws`, location.href);
    u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:';
    Object.entries(params).forEach(([k, v]) => u.searchParams.set(k, v));
    return u.toString();
  }

  function subscribe(channels, onMessage) {
    let ws, closed = false, ping, connected = false;
    const open = () => {
      try { ws = new WebSocket(wsUrl({ channels: channels.join(','), token: S.token || '' })); } catch { ws = null; return; }
      ws.onmessage = (e) => { try { onMessage(JSON.parse(e.data)); } catch { /* ignore */ } };
      ws.onopen = () => { connected = true; ping = setInterval(() => ws.readyState === 1 && ws.send('ping'), 25000); };
      ws.onclose = () => { connected = false; clearInterval(ping); if (!closed) setTimeout(open, 3000); };
    };
    open();
    // Fallback: if WebSockets are blocked (proxies, campus Wi-Fi), poll every 5 s instead.
    const fallback = setInterval(() => {
      if (!connected && !closed) onMessage({ type: channels[0].startsWith('request:') ? 'event' : 'poll' });
    }, 5000);
    const handle = { close() { closed = true; clearInterval(ping); clearInterval(fallback); ws && ws.close(); } };
    S.sockets.push(handle);
    return handle;
  }

  function toast(msg, ms = 2600) {
    const el = $('#toast');
    el.textContent = msg;
    el.classList.add('show');
    clearTimeout(el._t);
    el._t = setTimeout(() => el.classList.remove('show'), ms);
  }

  function setSession(token, user) {
    S.token = token; S.user = user;
    if (token) { store.set('rs_token', token); store.set('rs_user', JSON.stringify(user)); }
    else { store.del('rs_token'); store.del('rs_user'); }
    renderUserChip();
  }

  function getCoords(timeout = 6000) {
    return new Promise((resolve) => {
      if (!navigator.geolocation) return resolve(S.coords);
      navigator.geolocation.getCurrentPosition(
        (p) => { S.coords = { lat: p.coords.latitude, lon: p.coords.longitude }; resolve(S.coords); },
        () => resolve(S.coords), { timeout, maximumAge: 120000 });
    });
  }

  // ------------------------------------------------------------------ speech
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  let recognizer = null;
  let audioEl = null;
  const speechCode = () => (window.LANGS.find((l) => l.code === S.lang) || window.LANGS[0]).speech;

  function stopSpeaking() {
    try { window.speechSynthesis && speechSynthesis.cancel(); } catch { /* noop */ }
    if (audioEl) { audioEl.pause(); audioEl = null; }
  }

  function speak(text) {
    return new Promise((resolve) => {
      if (!S.voiceOn || !text) return resolve();
      stopSpeaking();
      const code = speechCode();
      const voices = window.speechSynthesis ? speechSynthesis.getVoices() : [];
      const voice = voices.find((v) => v.lang === code) || voices.find((v) => v.lang && v.lang.startsWith(S.lang + '-'));
      if (voice) {
        const u = new SpeechSynthesisUtterance(text);
        u.voice = voice; u.lang = code; u.rate = 0.95;
        u.onend = resolve; u.onerror = resolve;
        speechSynthesis.speak(u);
      } else {
        // no local voice for this language (common for kn/ta/te) -> server-side TTS
        audioEl = new Audio(`${API}/api/voice/tts?lang=${S.lang}&text=${encodeURIComponent(text.slice(0, 590))}`);
        audioEl.onended = resolve; audioEl.onerror = resolve;
        audioEl.play().catch(resolve);
      }
    });
  }
  if (window.speechSynthesis) speechSynthesis.onvoiceschanged = () => {};

  function listen(onInterim, onFinal, onEnd) {
    if (!SR) { toast('Voice input needs Chrome or Edge. You can type instead.'); return null; }
    stopSpeaking();
    const r = new SR();
    r.lang = speechCode(); r.interimResults = true; r.maxAlternatives = 1; r.continuous = false;
    let finalText = '';
    r.onresult = (e) => {
      let interim = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const t = e.results[i][0].transcript;
        if (e.results[i].isFinal) finalText += t; else interim += t;
      }
      onInterim(finalText + interim);
    };
    r.onerror = (e) => { if (e.error === 'not-allowed') toast('Microphone permission is blocked.'); };
    r.onend = () => { recognizer = null; onEnd(); if (finalText.trim()) onFinal(finalText.trim()); };
    r.start();
    recognizer = r;
    return r;
  }

  // ------------------------------------------------------------------ chrome
  function renderUserChip() {
    const el = $('#userChip');
    if (!S.user) {
      el.innerHTML = '';
      return;
    }
    el.innerHTML = `<span class="user-chip"><span class="nm"><b>${esc(S.user.name || S.user.phone)}</b> · ${esc(S.user.role)}</span>
      <button class="btn ghost small" id="logoutBtn">${T('logout')}</button></span>`;
    $('#logoutBtn').onclick = () => { setSession(null, null); S.sid = null; S.chat = []; route(); toast('Logged out'); };
  }

  function applyLang() {
    document.documentElement.lang = S.lang || 'en';
    $$('[data-i18n]').forEach((el) => { el.textContent = T(el.dataset.i18n); });
    const sel = $('#langSelect');
    sel.innerHTML = window.LANGS.map((l) => `<option value="${l.code}" ${l.code === S.lang ? 'selected' : ''}>${l.name}</option>`).join('');
  }

  function setLang(code) {
    S.lang = code; store.set('rs_lang', code);
    applyLang();
  }

  function showLangGate() {
    const gate = $('#langGate');
    $('#langButtons').innerHTML = window.LANGS.map((l) => `<button class="lang-btn" data-l="${l.code}">${l.name}</button>`).join('');
    gate.hidden = false;
    $$('.lang-btn', gate).forEach((b) => b.onclick = () => {
      setLang(b.dataset.l); gate.hidden = true;
      S.sid = null; S.chat = [];
      route();
    });
  }

  function cleanup() {
    S.sockets.forEach((s) => s.close()); S.sockets = [];
    S.timers.forEach(clearInterval); S.timers = [];
    S.charts.forEach((c) => c.destroy()); S.charts = [];
    if (S.map) { S.map.remove(); S.map = null; }
    if (recognizer) { try { recognizer.abort(); } catch { /* noop */ } recognizer = null; }
  }

  // ------------------------------------------------------------------ login widget
  function loginCard(title, onDone, { demoRole } = {}) {
    const id = 'lc' + Math.random().toString(36).slice(2, 7);
    const html = `<div class="card" id="${id}">
      <h2>${esc(title)}</h2>
      <p class="muted small" style="margin-top:.4rem">Mobile number + one-time code. No passwords to remember.</p>
      <div class="stack" style="margin-top:1rem">
        <label class="field"><span>Mobile number</span><input type="tel" inputmode="numeric" maxlength="14" placeholder="98XXXXXXXX" data-phone></label>
        <div class="row"><button class="btn primary" data-send>Send code</button></div>
        <div data-otp-step hidden class="stack">
          <div class="otp-card" data-hint hidden></div>
          <label class="field"><span>6-digit code</span><input type="text" inputmode="numeric" maxlength="6" data-otp></label>
          <button class="btn primary" data-verify>${T('login')}</button>
        </div>
        ${demoRole ? `<div class="notice">Demo shortcuts: <button class="btn small" data-demo="${demoRole}">Log in as demo ${demoRole}</button></div>` : ''}
      </div></div>`;
    const bind = (root) => {
      const el = $('#' + id, root);
      const phone = $('[data-phone]', el);
      $('[data-send]', el).onclick = async () => {
        try {
          const r = await api('/api/auth/request-otp', { method: 'POST', body: { phone: phone.value }, auth: false });
          $('[data-otp-step]', el).hidden = false;
          if (r.demo_otp) { const h = $('[data-hint]', el); h.hidden = false; h.innerHTML = `Demo mode — SMS gateway off. Your code: <b>${r.demo_otp}</b>`; }
          $('[data-otp]', el).focus();
        } catch (e) { toast(e.message); }
      };
      $('[data-verify]', el).onclick = async () => {
        try {
          const r = await api('/api/auth/verify-otp', { method: 'POST', body: { phone: phone.value, otp: $('[data-otp]', el).value, lang: S.lang }, auth: false });
          setSession(r.token, r.user); onDone();
        } catch (e) { toast(e.message); }
      };
      const demoBtn = $('[data-demo]', el);
      if (demoBtn) demoBtn.onclick = async () => {
        try {
          const accounts = await api('/api/demo/accounts', { auth: false });
          const acc = accounts.find((a) => a.role === demoRole);
          const r = await api(`/api/demo/login/${acc.id}`, { method: 'POST', auth: false });
          setSession(r.token, r.user); onDone();
        } catch (e) { toast(e.message); }
      };
    };
    return { html, bind };
  }

  // ================================================================== ASSISTANT
  function slotDefs() {
    const isDonor = (S.step || '').startsWith('don_') || S.slots.name !== undefined && S.slots.gender !== undefined;
    if (isDonor) {
      return [
        ['name', 'name', ICON.user, S.slots.name],
        ['blood_group', 'blood_group', ICON.drop, S.slots.blood_group],
        ['gender', 'gender', ICON.user, S.slots.gender === 'F' ? '♀' : S.slots.gender === 'M' ? '♂' : null],
        ['last', 'last_donation', ICON.clock, S.slots.last_set ? (S.slots.last_donation || '—') : null],
        ['area', 'area', ICON.pin, S.slots.area],
      ];
    }
    return [
      ['blood_group', 'blood_group', ICON.drop, S.slots.blood_group],
      ['units', 'units', ICON.hash, S.slots.units],
      ['hospital', 'hospital', ICON.hospital, S.slots.hospital],
      ['urgency', 'urgency', ICON.clock, S.slots.urgency],
    ];
  }

  function renderAssistant(main) {
    main.innerHTML = `
      <div class="page-head">
        <div><span class="eyebrow">Voice-first · ${esc((window.LANGS.find((l) => l.code === S.lang) || {}).name)}</span>
          <h1>Need blood? Want to donate? Just speak.</h1>
          <p>Tap the red button and talk in your language. The assistant asks one question at a time, confirms, and then alerts matching donors live.</p></div>
      </div>
      <div class="assistant">
        <section class="card chat-card" aria-label="Conversation">
          <div class="chat-head">
            <div class="who"><div class="avatar">${ICON.drop}</div><div><b>RaktaSetu</b><div class="xs muted" id="asStatus">${T('tap_to_speak')}</div></div></div>
            <div class="row">
              <button class="btn small ghost" id="voiceToggle" aria-pressed="${S.voiceOn}">${S.voiceOn ? T('voice_on') : T('voice_off')}</button>
              <button class="btn small ghost" id="restartBtn">${T('start_over')}</button>
            </div>
          </div>
          <div class="chat-log" id="chatLog" aria-live="polite"></div>
          <div class="chips" id="chips"></div>
          <form class="composer" id="composer">
            <div class="mic-wrap"><button type="button" class="mic" id="micBtn" aria-label="${T('tap_to_speak')}">${ICON.mic}</button></div>
            <input type="text" id="textIn" autocomplete="off" placeholder="${T('type_here')}" aria-label="${T('type_here')}">
            <button class="btn primary" type="submit">${T('send')}</button>
          </form>
        </section>
        <aside>
          <div class="card">
            <h2>${T('understood')}</h2>
            <div class="slots" id="slots"></div>
            <div id="otpBox"></div>
            <label class="small" style="margin-top:1rem;display:flex;align-items:flex-start;gap:.5rem;flex-wrap:nowrap"><input type="checkbox" id="handsFree" style="margin-top:.2rem;flex:none" ${S.handsFree ? 'checked' : ''}> <span>Hands-free: listen again automatically after each reply</span></label>
            <p class="notice">RaktaSetu coordinates voluntary donors. It does not give medical clearance — screening, testing and cross-matching are done by the licensed blood centre. Never pay or accept money for blood.</p>
          </div>
          <div class="card small">
            <h3>Try saying</h3>
            <ul class="muted" style="margin:.5rem 0 0;padding-left:1.1rem">
              <li>“ನನಗೆ ಬಿ ಪಾಸಿಟಿವ್ ರಕ್ತ ಬೇಕು, ತುಂಬಾ ತುರ್ತು”</li>
              <li>“मुझे ओ नेगेटिव खून चाहिए, मणिपाल अस्पताल”</li>
              <li>“I want to donate blood”</li>
            </ul>
          </div>
        </aside>
      </div>`;

    const log = $('#chatLog');
    const renderChat = () => {
      log.innerHTML = S.chat.map((m, i) => {
        if (m.kind === 'link') return `<div class="bubble bot"><a class="btn primary small" href="${m.href}">${esc(m.text)}</a></div>`;
        return `<div class="bubble ${m.who}${m.interim ? ' interim' : ''}">${esc(m.text)}${m.who === 'bot' ? `<button class="replay" data-i="${i}" aria-label="Play again">${ICON.speaker}</button>` : ''}</div>`;
      }).join('');
      log.scrollTop = log.scrollHeight;
      $$('.replay', log).forEach((b) => b.onclick = () => speak(S.chat[+b.dataset.i].text));
    };
    const renderSide = () => {
      $('#slots').innerHTML = slotDefs().map(([, label, icon, v]) =>
        `<div class="slot ${v ? 'filled' : ''}"><div class="k">${icon}${T(label)}</div><div class="v">${v ? esc(v) : '<span class="muted">—</span>'}</div></div>`).join('');
      $('#chips').innerHTML = S.chips.map((c, i) => `<button class="chip ${/^[ABO]{1,2}[+-]$/.test(c.label) ? 'bg' : ''}" data-i="${i}">${esc(c.label)}</button>`).join('');
      $$('#chips .chip').forEach((b) => b.onclick = () => { const c = S.chips[+b.dataset.i]; send(c.value, c.label); });
      $('#otpBox').innerHTML = S.demoOtp && S.step === 'ask_otp'
        ? `<div class="otp-card">Demo mode — SMS gateway off. Code sent: <b>${esc(S.demoOtp)}</b></div>` : '';
      const ti = $('#textIn');
      ti.type = S.inputHint === 'phone' ? 'tel' : 'text';
      ti.inputMode = S.inputHint === 'text' ? 'text' : 'numeric';
    };

    let busy = false;
    async function send(text, labelText) {
      if (busy) return;
      busy = true;
      if (text !== '__start__') S.chat.push({ who: 'user', text: labelText || text });
      renderChat();
      let lat, lon;
      if (text === 'location') { const c = await getCoords(); if (c) { lat = c.lat; lon = c.lon; } else toast('Location unavailable — using area instead'); }
      else if (S.coords) { lat = S.coords.lat; lon = S.coords.lon; }
      try {
        const r = await api('/api/voice/turn', { method: 'POST', body: { session_id: S.sid, lang: S.lang, text, lat, lon } });
        S.sid = r.session_id; S.step = r.step; S.chips = r.chips || []; S.slots = r.slots || {}; S.inputHint = r.input_hint;
        if (r.demo_otp) S.demoOtp = r.demo_otp;
        S.chat.push({ who: 'bot', text: r.reply });
        const a = r.action;
        if (a && a.type === 'login') setSession(a.token, a.user);
        if (a && a.type === 'donor_registered') { setSession(S.token, a.user); S.chat.push({ kind: 'link', href: '#/donor', text: T('nav_donor') + ' →' }); }
        if (a && a.type === 'open_donor') S.chat.push({ kind: 'link', href: '#/donor', text: T('nav_donor') + ' →' });
        if (a && a.type === 'open_request') S.chat.push({ kind: 'link', href: `#/request/${a.request_id}`, text: 'Live tracker →' });
        renderChat(); renderSide();
        busy = false;
        // never let a stuck speech engine block the flow
        await Promise.race([speak(r.reply), new Promise((res) => setTimeout(res, a && a.type === 'open_request' ? 4000 : 15000))]);
        const onAssistant = ['', '#', '#/'].includes(location.hash);
        if (a && a.type === 'open_request' && onAssistant) { location.hash = `#/request/${a.request_id}`; return; }
        if (S.handsFree && SR && r.step !== 'done' && location.hash.replace('#/', '') === '') startListening();
      } catch (e) {
        busy = false;
        S.chat.push({ who: 'bot', text: '⚠ ' + e.message });
        renderChat();
      }
    }

    function startListening() {
      const mic = $('#micBtn');
      if (!mic) return;
      if (recognizer) { recognizer.stop(); return; }
      const interimIdx = S.chat.push({ who: 'user', text: '…', interim: true }) - 1;
      renderChat();
      mic.classList.add('listening'); mic.innerHTML = ICON.stop; $('#asStatus').textContent = T('listening');
      const r = listen(
        (txt) => { S.chat[interimIdx].text = txt || '…'; renderChat(); },
        (finalTxt) => { S.chat.splice(interimIdx, 1); send(finalTxt); },
        () => {
          if (S.chat[interimIdx] && S.chat[interimIdx].interim) { S.chat.splice(interimIdx, 1); renderChat(); }
          const m = $('#micBtn'); if (m) { m.classList.remove('listening'); m.innerHTML = ICON.mic; }
          const st = $('#asStatus'); if (st) st.textContent = T('tap_to_speak');
        });
      if (!r) { S.chat.splice(interimIdx, 1); renderChat(); mic.classList.remove('listening'); mic.innerHTML = ICON.mic; }
    }

    $('#micBtn').onclick = startListening;
    $('#composer').onsubmit = (e) => { e.preventDefault(); const v = $('#textIn').value.trim(); if (v) { $('#textIn').value = ''; send(v); } };
    $('#voiceToggle').onclick = (e) => {
      S.voiceOn = !S.voiceOn; store.set('rs_voice', S.voiceOn ? 'on' : 'off');
      e.target.textContent = S.voiceOn ? T('voice_on') : T('voice_off'); if (!S.voiceOn) stopSpeaking();
    };
    $('#restartBtn').onclick = () => { S.chat = []; S.sid = null; S.slots = {}; S.chips = []; S.demoOtp = null; renderChat(); send('__start__'); };
    $('#handsFree').onchange = (e) => { S.handsFree = e.target.checked; store.set('rs_handsfree', S.handsFree ? 'on' : 'off'); };

    renderChat(); renderSide();
    getCoords(4000);
    if (!S.chat.length) send('__start__');
  }

  // ================================================================== REQUESTS (list + manual form)
  async function renderRequests(main) {
    if (!S.token) {
      const lc = loginCard('Log in to create or track requests', () => route());
      main.innerHTML = `<div class="page-head"><div><h1>Blood requests</h1><p>Prefer speaking? Use the Assistant tab — it does all of this by voice.</p></div></div><div style="max-width:520px">${lc.html}</div>`;
      lc.bind(main);
      return;
    }
    const meta = S.meta || (S.meta = await api('/api/meta', { auth: false }));
    main.innerHTML = `<div class="page-head"><div><h1>Blood requests</h1><p>Create a request with the form, or say it to the Assistant. Matching donors are alerted instantly.</p></div>
      <a class="btn" href="#/">${ICON.mic.replace('<svg', '<svg width="16" height="16"')} ${T('nav_assistant')}</a></div>
      <div class="grid-2">
        <section class="card"><h2>New emergency request</h2>
          <form id="reqForm" class="stack" style="margin-top:1rem">
            <div class="form-grid">
              <label class="field"><span>${T('blood_group')}</span><select class="input" name="blood_group">${meta.blood_groups.map((g) => `<option>${g}</option>`).join('')}</select></label>
              <label class="field"><span>${T('units')}</span><input type="number" name="units" min="1" max="10" value="1"></label>
            </div>
            <label class="field"><span>${T('hospital')}</span><select class="input" name="hospital">${meta.hospitals.map((h, i) => `<option value="${i}">${esc(h.name)}</option>`).join('')}<option value="here">Other — use my current location</option></select></label>
            <label class="field" id="otherHosp" hidden><span>Hospital name</span><input type="text" name="other_name" placeholder="Hospital name"></label>
            <div class="form-grid">
              <label class="field"><span>${T('urgency')}</span><select class="input" name="urgency"><option value="critical">Critical (hours)</option><option value="urgent" selected>Urgent (today)</option><option value="normal">Normal</option></select></label>
              <label class="field"><span>Patient name (optional)</span><input type="text" name="patient_name"></label>
            </div>
            <button class="btn primary big" type="submit">Alert matching donors</button>
          </form></section>
        <section class="card"><h2>My requests</h2><div id="myReqs" class="stack" style="margin-top:1rem"><div class="skeleton"></div></div></section>
      </div>`;
    const f = $('#reqForm');
    f.hospital.onchange = () => { $('#otherHosp').hidden = f.hospital.value !== 'here'; };
    f.onsubmit = async (e) => {
      e.preventDefault();
      let hospital, lat, lon;
      if (f.hospital.value === 'here') {
        const c = await getCoords();
        if (!c) return toast('Could not read your location. Choose a hospital from the list.');
        hospital = f.other_name.value || 'Patient location'; lat = c.lat; lon = c.lon;
      } else { const h = meta.hospitals[+f.hospital.value]; hospital = h.name; lat = h.lat; lon = h.lon; }
      try {
        const r = await api('/api/requests', { method: 'POST', body: { blood_group: f.blood_group.value, units: +f.units.value, urgency: f.urgency.value, hospital, lat, lon, patient_name: f.patient_name.value, language: S.lang } });
        location.hash = `#/request/${r.id}`;
      } catch (err) { toast(err.message); }
    };
    const mine = await api('/api/requests/mine');
    $('#myReqs').innerHTML = mine.length ? mine.map((r) => `<a href="#/request/${r.id}" class="donor-row" style="text-decoration:none;color:inherit">
        <span class="bg-badge sm">${esc(r.blood_group)}</span>
        <div><b>${esc(r.hospital_name)}</b><div class="sub">${fmtDT(r.created_at)} · ${r.units_fulfilled}/${r.units_needed} units · ${esc(r.urgency)}</div></div>
        ${statusPill(r.status)}</a>`).join('') : '<div class="empty">No requests yet.</div>';
  }

  function statusPill(s) {
    const map = { pending: ['amber', 'Pending'], searching: ['amber', 'Searching donors'], donor_committed: ['blue', 'Donor on the way'], fulfilled: ['green', 'Fulfilled'], cancelled: ['', 'Cancelled'], unfulfilled: ['red', 'Unfulfilled'],
      notified: ['amber', 'Alerted'], accepted: ['blue', 'Committed'], checked_in: ['blue', 'Checked in'], donated: ['green', 'Donated'], declined: ['', 'Declined'], expired: ['', 'Expired'], no_show: ['red', 'No-show'] };
    const [c, l] = map[s] || ['', s];
    return `<span class="pill ${c}">${esc(l)}</span>`;
  }

  // ================================================================== REQUEST TRACKER
  async function renderRequest(main, id) {
    main.innerHTML = '<div class="skeleton" style="height:320px"></div>';
    let data, lastEventCount = 0;
    const load = async () => { data = await api(`/api/requests/${id}`); };
    try { await load(); } catch (e) { main.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }

    const evClass = (t) => ({ donor_accepted: 'good', donor_checked_in: 'good', donation_confirmed: 'good', created: 'info', donors_notified: 'info', radius_expanded: 'info', no_show: 'bad', alert_expired: 'bad', no_donors: 'bad', cancelled: 'bad', donor_declined: 'bad' }[t] || '');
    const stepIndex = () => {
      if (data.status === 'fulfilled') return 5;
      if (data.matches.some((m) => m.status === 'checked_in')) return 3;
      if (data.status === 'donor_committed') return 2;
      if (data.matches.length) return 1;
      return 0;
    };

    const draw = (highlightNew) => {
      const si = stepIndex();
      const steps = ['Requested', 'Donors alerted', 'Donor committed', 'Checked in', 'Fulfilled'];
      const canAct = data.is_owner || (S.user && ['admin', 'staff'].includes(S.user.role));
      const open = ['pending', 'searching', 'donor_committed'].includes(data.status);
      main.innerHTML = `
        <section class="card">
          <div class="status-hero">
            <span class="bg-badge" style="min-width:72px;height:72px;font-size:1.6rem">${esc(data.blood_group)}</span>
            <div class="meta">
              <span class="eyebrow">Request ${esc(data.id)} · via ${esc(data.created_via)} · ${esc(data.language)}</span>
              <h1>${esc(data.hospital_name)}</h1>
              <div class="row small muted">${statusPill(data.status)} <span>${data.units_fulfilled}/${data.units_needed} units</span> <span>· ${esc(data.urgency)}</span> <span>· radius ${data.radius_km} km · wave ${data.wave}</span></div>
              <div class="xs muted" style="margin-top:.35rem">Compatible donor groups: ${data.compatible_groups.join(', ')}</div>
            </div>
            ${canAct && open ? `<div class="row"><button class="btn" id="escBtn">Alert more donors</button><button class="btn danger-ghost" id="cancelBtn">Cancel</button></div>` : ''}
          </div>
          <div class="steps">${steps.map((s, i) => `<div class="step ${i < si || si === 5 ? 'done' : i === si ? 'now' : ''}">${s}</div>`).join('')}</div>
        </section>
        <div class="grid-2" style="margin-top:1.5rem">
          <div class="stack">
            <section class="card"><div class="row between"><h2>Matched donors</h2><span class="xs muted">Ranked by ML acceptance probability + distance + reliability</span></div>
              <div class="donor-list" style="margin-top:1rem">${data.matches.length ? data.matches.map((m) => donorRow(m, canAct)).join('') : '<div class="empty">Searching for compatible donors…</div>'}</div>
            </section>
            <section class="card"><h2>Map</h2><p class="xs muted" style="margin:.25rem 0 .75rem">Hospital, current search radius and nearby blood banks. Donor home locations stay private.</p><div id="map" class="map"></div></section>
          </div>
          <div class="stack">
            <section class="card"><div class="row between"><h2>Live timeline</h2><span class="pill green" id="liveDot">● live</span></div>
              <ul class="timeline" style="margin-top:1rem">${[...data.events].reverse().map((e, i) => `<li class="${evClass(e.type)} ${highlightNew && i === 0 ? 'new' : ''}"><time>${fmtTime(e.at)}</time>${esc(e.message)}</li>`).join('')}</ul>
            </section>
            <section class="card"><h2>Backup: blood banks</h2>
              <div class="stack small" style="margin-top:.75rem">${(data.blood_banks || []).map((b) => `<div class="row between"><div><b>${esc(b.name)}</b><div class="xs muted">${b.distance_km} km · ${esc(b.phone)}</div></div><span class="pill ${b.compatible_units ? 'green' : ''}">${b.compatible_units} compatible units</span></div>`).join('')}</div>
              <p class="notice">Demo stock. For live government stock, check <a href="https://eraktkosh.mohfw.gov.in/" target="_blank" rel="noopener">e-RaktKosh</a>.</p>
            </section>
          </div>
        </div>
        <div id="reportBox"></div>`;
      bindRequestActions();
      drawMap();
    };

    const donorRow = (m, canAct) => {
      const committed = ['accepted', 'checked_in', 'donated'].includes(m.status);
      const pct = Math.round(m.accept_probability * 100);
      return `<div class="donor-row ${committed ? 'committed' : ''}">
        <span class="bg-badge sm">${esc(m.blood_group)}</span>
        <div><b>${esc(m.donor_name)}</b> ${m.exact_match ? '' : '<span class="pill blue">compatible</span>'} ${m.noshow_risk ? `<span class="pill ${m.noshow_risk === 'high' ? 'red' : m.noshow_risk === 'medium' ? 'amber' : 'green'}">no-show risk ${m.noshow_risk}</span>` : ''}
          <div class="sub">#${m.rank} · wave ${m.wave} · ${m.distance_km} km · ${pct}% likely to accept (${esc(m.score_source)}) · reliability ${m.reliability ?? '–'}</div>
          <div class="prob"><i style="width:${pct}%"></i></div>
          <div class="sub">${committed ? `📞 <b>${esc(m.donor_phone)}</b> · ` : `Phone hidden until accepted (${esc(m.donor_phone)}) · `}${m.commitment_deadline && m.status === 'accepted' ? `arrive by ${fmtTime(m.commitment_deadline)}` : ''}${m.checkin_at ? `checked in ${fmtTime(m.checkin_at)}${m.checkin_distance_km != null ? ` (${m.checkin_distance_km} km from hospital)` : ''}` : ''}</div>
        </div>
        <div class="row">${statusPill(m.status)}
          ${canAct && ['accepted', 'checked_in'].includes(m.status) ? `<button class="btn ok small" data-confirm="${m.id}">Confirm donation</button>` : ''}
          ${data.is_owner && committed ? `<button class="btn ghost small" data-report="${m.id}">Report</button>` : ''}
        </div></div>`;
    };

    const bindRequestActions = () => {
      const esc_ = $('#escBtn'); if (esc_) esc_.onclick = async () => { try { const r = await api(`/api/requests/${id}/escalate`, { method: 'POST' }); toast(`${r.notified} more donors alerted`); } catch (e) { toast(e.message); } };
      const c = $('#cancelBtn'); if (c) c.onclick = async () => { try { await api(`/api/requests/${id}/cancel`, { method: 'POST' }); } catch (e) { toast(e.message); } };
      $$('[data-confirm]').forEach((b) => b.onclick = async () => { try { await api(`/api/matches/${b.dataset.confirm}/confirm`, { method: 'POST' }); } catch (e) { toast(e.message); } });
      $$('[data-report]').forEach((b) => b.onclick = () => showReport(b.dataset.report));
    };

    const showReport = async (matchId) => {
      const box = $('#reportBox');
      box.innerHTML = `<section class="card" style="margin-top:1.5rem;max-width:560px"><h2>Report this donor</h2>
        <p class="small muted" style="margin:.4rem 0 1rem">Blood donation in India is voluntary and unpaid. Report payment demands, fake profiles or harassment — an admin will review and can suspend the account.</p>
        <form id="repForm" class="stack"><label class="field"><span>Reason</span><select class="input" name="reason"><option value="payment_demand">Asked for money</option><option value="fake_profile">Fake profile</option><option value="harassment">Harassment</option><option value="no_show">Did not come</option><option value="other">Other</option></select></label>
        <label class="field"><span>Details</span><textarea name="details" rows="3"></textarea></label>
        <div class="row"><button class="btn primary">Submit report</button><button type="button" class="btn ghost" id="repCancel">Cancel</button></div></form></section>`;
      $('#repCancel').onclick = () => { box.innerHTML = ''; };
      $('#repForm').onsubmit = async (e) => {
        e.preventDefault();
        try {
          // the reported user is resolved server-side from the match via the admin/staff view; requester sends match's donor id
          const full = await api(`/api/requests/${id}`);
          const m = full.matches.find((x) => x.id === matchId);
          await api('/api/reports', { method: 'POST', body: { reported_user_id: m.donor_user_id, request_id: id, reason: e.target.reason.value, details: e.target.details.value } });
          toast('Report submitted. Thank you.'); box.innerHTML = '';
        } catch (err) { toast(err.message); }
      };
    };

    const drawMap = () => {
      if (!window.L) return;
      if (S.map) { S.map.remove(); S.map = null; }
      const m = L.map('map', { scrollWheelZoom: false }).setView([data.lat, data.lon], 12);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 18, attribution: '© OpenStreetMap' }).addTo(m);
      L.circle([data.lat, data.lon], { radius: data.radius_km * 1000, color: '#b42318', weight: 1.5, fillOpacity: .06 }).addTo(m);
      L.circleMarker([data.lat, data.lon], { radius: 9, color: '#fff', weight: 2, fillColor: '#b42318', fillOpacity: 1 }).addTo(m).bindPopup(esc(data.hospital_name));
      (data.blood_banks || []).forEach((b) => b.lat && L.circleMarker([b.lat, b.lon], { radius: 7, color: '#fff', weight: 2, fillColor: '#2b5c8a', fillOpacity: 1 }).addTo(m).bindPopup(`${esc(b.name)}<br>${b.compatible_units} compatible units`));
      S.map = m;
    };

    lastEventCount = data.events.length;
    draw(false);
    subscribe([`request:${id}`], async (msg) => {
      if (msg.type !== 'event') return;
      await load();
      const newEvents = data.events.slice(lastEventCount);
      lastEventCount = data.events.length;
      draw(true);
      if (data.is_owner) {
        const types = newEvents.map((e) => e.type);
        if (types.includes('donation_confirmed') && data.status === 'fulfilled') speak(T('fulfilled_say'));
        else if (types.includes('donor_checked_in')) speak(T('checked_in_say'));
        else if (types.includes('donor_accepted')) speak(T('donor_accepted_say'));
        else if (types.includes('escalated')) speak(T('escalated_say'));
      }
    });
  }

  // ================================================================== DONOR CONSOLE
  async function renderDonor(main) {
    if (!S.token) {
      const lc = loginCard('Donor login', () => route(), { demoRole: 'donor' });
      main.innerHTML = `<div class="page-head"><div><h1>Donor console</h1><p>Set your availability, receive emergency alerts near you, and commit with one tap.</p></div></div>
        <div class="grid-2"><div>${lc.html}</div><div class="card" id="demoPicker"><h2>Demo donors</h2><p class="small muted" style="margin:.4rem 0 1rem">Open this page in a second browser window and log in as one of the seeded donors to receive live alerts.</p><div class="skeleton"></div></div></div>`;
      lc.bind(main);
      try {
        const acc = (await api('/api/demo/accounts', { auth: false })).filter((a) => a.role === 'donor');
        $('#demoPicker .skeleton').outerHTML = `<div class="stack small" style="max-height:420px;overflow:auto">${acc.map((a) => `<button class="donor-row" style="width:100%;text-align:left;cursor:pointer" data-acc="${a.id}"><span class="bg-badge sm">${esc(a.blood_group)}</span><div><b>${esc(a.name)}</b><div class="sub">${esc(a.area)} · ${esc(a.status)}</div></div><span class="pill">${T('login')}</span></button>`).join('')}</div>`;
        $$('[data-acc]').forEach((b) => b.onclick = async () => { const r = await api(`/api/demo/login/${b.dataset.acc}`, { method: 'POST', auth: false }); setSession(r.token, r.user); route(); });
      } catch { $('#demoPicker').hidden = true; }
      return;
    }
    let me;
    const load = async () => { me = await api('/api/donors/me'); };
    await load();

    if (!me.registered) {
      const meta = S.meta || (S.meta = await api('/api/meta', { auth: false }));
      main.innerHTML = `<div class="page-head"><div><h1>Become a donor</h1><p>Takes a minute. Or tap the button and register by voice in your language.</p></div><a class="btn primary" href="#/" id="voiceReg">${T('nav_assistant')}</a></div>
        <section class="card" style="max-width:720px"><form id="donForm" class="stack">
          <div class="form-grid">
            <label class="field"><span>${T('name')}</span><input type="text" name="name" required value="${esc(S.user?.name || '')}"></label>
            <label class="field"><span>${T('blood_group')}</span><select class="input" name="blood_group">${meta.blood_groups.map((g) => `<option>${g}</option>`).join('')}</select></label>
            <label class="field"><span>${T('gender')}</span><select class="input" name="gender"><option value="M">Male (90-day gap)</option><option value="F">Female (120-day gap)</option></select></label>
            <label class="field"><span>${T('last_donation')}</span><input type="date" name="last"></label>
          </div>
          <label class="field"><span>${T('area')}</span><input type="text" name="area" placeholder="e.g. Koramangala"></label>
          <p class="xs muted">We use your current location to match nearby emergencies. Your exact location and number are never shown publicly.</p>
          <button class="btn primary big">Register as donor</button></form></section>`;
      $('#voiceReg').onclick = () => { S.chat = []; S.sid = null; };
      $('#donForm').onsubmit = async (e) => {
        e.preventDefault();
        const f = e.target; const c = (await getCoords()) || { lat: 12.9716, lon: 77.5946 };
        try {
          await api('/api/donors/register', { method: 'POST', body: { name: f.name.value, blood_group: f.blood_group.value, gender: f.gender.value, last_donation_date: f.last.value || null, lat: c.lat, lon: c.lon, area: f.area.value } });
          toast('Registered. You are live.'); route();
        } catch (err) { toast(err.message); }
      };
      return;
    }

    const draw = () => {
      const alerts = me.matches.filter((m) => m.status === 'notified');
      const active = me.matches.filter((m) => ['accepted', 'checked_in'].includes(m.status));
      const past = me.matches.filter((m) => !['notified', 'accepted', 'checked_in'].includes(m.status));
      main.innerHTML = `
        <div class="page-head"><div><span class="eyebrow">Donor console</span><h1>${esc(me.name)}</h1><p>Keep this page open — emergency alerts arrive live with sound and voice.</p></div>
          <span class="bg-badge" style="min-width:64px;height:64px">${esc(me.blood_group)}</span></div>
        <div class="grid-2">
          <div class="stack">
            ${alerts.map((a) => `<section class="card alert-card" data-alert="${a.match_id}">
              <div class="row between"><span class="eyebrow" style="color:var(--blood-deep)">${T('emergency_near')}</span><span class="countdown" data-expires="${a.expires_at}">--:--</span></div>
              <h2 style="margin-top:.5rem">${esc(a.blood_group)} · ${a.units} unit(s) · ${esc(a.urgency)}</h2>
              <p class="muted" style="margin-top:.25rem">${esc(a.hospital)} — ${a.distance_km} km away. Family contact unlocks after you accept (${esc(a.requester_phone)}).</p>
              <div class="row" style="margin-top:1rem"><button class="btn ok big" data-accept="${a.match_id}">${T('accept')}</button><button class="btn big" data-decline="${a.match_id}">${T('decline')}</button>
                <button class="btn ghost" data-voice="${a.match_id}">${ICON.mic.replace('<svg', '<svg width="18" height="18"')} Say yes / no</button></div>
            </section>`).join('')}
            ${active.map((a) => `<section class="card" style="border:2px solid var(--ok)">
              <div class="row between"><span class="eyebrow" style="color:var(--ok)">Your commitment</span>${statusPill(a.status)}</div>
              <h2 style="margin-top:.5rem">${esc(a.hospital)}</h2>
              <p class="muted small" style="margin-top:.25rem">${esc(a.requester_name)} · 📞 <b><a href="tel:${esc(a.requester_phone)}">${esc(a.requester_phone)}</a></b>${a.patient_name ? ' · patient ' + esc(a.patient_name) : ''}</p>
              ${a.status === 'accepted' ? `<p style="margin-top:.75rem">Reach the blood centre within <b class="countdown" data-deadline="${a.commitment_deadline}" style="font-size:inherit">--:--</b> or the request moves to the next donor.</p>
              <div class="row" style="margin-top:1rem"><button class="btn ok big" data-checkin="${a.match_id}">${T('checkin')}</button>
              <button class="btn ghost small" data-checkin-demo="${a.match_id}" data-lat="${a.lat}" data-lon="${a.lon}">Demo: check in at hospital location</button>
              <a class="btn ghost small" target="_blank" rel="noopener" href="https://www.google.com/maps/dir/?api=1&destination=${a.lat},${a.lon}">Directions</a></div>`
              : '<p style="margin-top:.75rem" class="muted">Checked in. Blood centre staff will confirm after screening. Thank you!</p>'}
            </section>`).join('')}
            ${!alerts.length && !active.length ? `<section class="card empty"><p><b>No active alerts.</b></p><p class="small">When a compatible patient near you needs blood, it will appear here instantly.</p></section>` : ''}
            <section class="card"><h2>History</h2><div class="stack small" style="margin-top:.75rem">${past.length ? past.map((m) => `<div class="row between"><span>${esc(m.blood_group)} · ${esc(m.hospital)} · ${fmtDT(m.notified_at)}</span>${statusPill(m.status)}</div>`).join('') : '<span class="muted">No past alerts yet.</span>'}</div></section>
          </div>
          <div class="stack">
            <section class="card"><h2>Availability</h2><p class="small muted">Only “available” donors receive alerts.</p>
              <div class="avail">${['available', 'busy', 'unavailable'].map((s) => `<button data-s="${s}" class="${me.availability === s ? 'on' : ''}"><i></i>${T(s)}</button>`).join('')}</div>
              ${me.in_cooldown ? `<p class="otp-card" style="margin-top:1rem">Safe-gap period: you can donate again from <b style="font-size:inherit;letter-spacing:0">${esc(me.next_eligible)}</b> (${me.cooldown_days}-day rule).</p>` : ''}
            </section>
            <section class="card"><h2>Your impact</h2>
              <div class="stat-grid"><div class="stat"><div class="n">${me.total_donations}</div><div class="l">donations</div></div>
              <div class="stat"><div class="n">${Math.round(me.reliability)}</div><div class="l">reliability</div></div>
              <div class="stat"><div class="n">${me.stats.accepted}/${me.stats.notified}</div><div class="l">accepted</div></div></div>
              <p class="small muted" style="margin-top:1rem">You can help patients with: <b>${me.can_help.join(', ')}</b></p>
              <p class="xs muted" style="margin-top:.5rem">Reliability rises when you accept and check in, and drops sharply on no-shows. Higher reliability means you are alerted first.</p>
            </section>
          </div>
        </div>`;
      bind();
      tick();
    };

    const tick = () => {
      $$('[data-expires]').forEach((el) => { const s = Math.max(0, Math.round((new Date(el.dataset.expires) - Date.now()) / 1000)); el.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`; });
      $$('[data-deadline]').forEach((el) => { const s = Math.max(0, Math.round((new Date(el.dataset.deadline) - Date.now()) / 1000)); el.textContent = `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s`; });
    };

    const act = async (path, body) => { try { await api(path, { method: 'POST', body }); await load(); draw(); } catch (e) { toast(e.message); await load(); draw(); } };
    const bind = () => {
      $$('[data-accept]').forEach((b) => b.onclick = () => act(`/api/matches/${b.dataset.accept}/accept`));
      $$('[data-decline]').forEach((b) => b.onclick = () => act(`/api/matches/${b.dataset.decline}/decline`));
      $$('[data-checkin]').forEach((b) => b.onclick = async () => { const c = await getCoords(); act(`/api/matches/${b.dataset.checkin}/checkin`, c || {}); });
      $$('[data-checkin-demo]').forEach((b) => b.onclick = () => act(`/api/matches/${b.dataset.checkinDemo}/checkin`, { lat: +b.dataset.lat, lon: +b.dataset.lon }));
      $$('[data-voice]').forEach((b) => b.onclick = () => {
        b.textContent = T('listening');
        listen(() => {}, (txt) => {
          if (no) act(`/api/matches/${b.dataset.voice}/decline`); else if (yes) act(`/api/matches/${b.dataset.voice}/accept`); else toast(`Heard: “${txt}” — please tap a button`);
        }, () => {});
      });
      $$('.avail button').forEach((b) => b.onclick = async () => {
        try { me = { ...me, ...(await api('/api/donors/availability', { method: 'PATCH', body: { status: b.dataset.s } })) }; await load(); draw(); toast(T(b.dataset.s)); } catch (e) { toast(e.message); }
      });
    };

    draw();
    S.timers.push(setInterval(tick, 1000));
    if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission().catch(() => {});
    subscribe([`donor:${S.user.id}`], async (msg) => {
      await load(); draw();
      if (msg.type === 'alert') {
        beep();
        const a = msg.match;
        const text = `${T('emergency_near')}: ${a.blood_group}, ${a.hospital}, ${a.distance_km} km`;
        if ('Notification' in window && Notification.permission === 'granted') { try { new Notification('RaktaSetu', { body: text }); } catch { /* noop */ } }
        speak(text);
      } else if (msg.type === 'thank_you') { toast('Donation confirmed — thank you for saving a life'); }
    });
  }

  function beep() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      [0, 0.25].forEach((t) => { const o = ctx.createOscillator(); const g = ctx.createGain(); o.frequency.value = 880; o.connect(g); g.connect(ctx.destination); g.gain.setValueAtTime(0.15, ctx.currentTime + t); g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + t + 0.2); o.start(ctx.currentTime + t); o.stop(ctx.currentTime + t + 0.22); });
    } catch { /* noop */ }
  }

  // ================================================================== BLOOD BANKS
  async function renderBanks(main) {
    main.innerHTML = '<div class="skeleton" style="height:240px"></div>';
    const c = S.coords || { lat: 12.9716, lon: 77.5946 };
    const banks = await api(`/api/blood-banks?lat=${c.lat}&lon=${c.lon}`, { auth: false });
    const staff = S.user && ['admin', 'staff'].includes(S.user.role);
    const groups = ['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'];
    main.innerHTML = `<div class="page-head"><div><h1>Blood banks</h1><p>Backup supply when no donor responds. Stock shown here is demo data maintained by blood-centre staff in this app; for official live stock use <a href="https://eraktkosh.mohfw.gov.in/" target="_blank" rel="noopener">e-RaktKosh</a>.</p></div></div>
      <div class="grid-3">${banks.map((b) => `<section class="card" data-bank="${b.id}"><h3>${esc(b.name)}</h3><p class="xs muted" style="margin-top:.25rem">${esc(b.address)} · ${b.distance_km} km · ${esc(b.phone)}</p>
        <div class="bank-stock">${groups.map((g) => `<div class="${(b.stock[g] || 0) ? '' : 'zero'}">${g}${staff ? `<input type="number" min="0" value="${b.stock[g] || 0}" data-g="${g}" aria-label="${g} units">` : `<b>${b.stock[g] || 0}</b>`}</div>`).join('')}</div>
        <div class="row between" style="margin-top:.75rem"><span class="xs muted">Updated ${fmtDT(b.stock_updated_at)}</span>${staff ? `<button class="btn small" data-save="${b.id}">Save stock</button>` : ''}</div></section>`).join('')}</div>`;
    $$('[data-save]').forEach((btn) => btn.onclick = async () => {
      const card = $(`[data-bank="${btn.dataset.save}"]`);
      const stock = {}; $$('input[data-g]', card).forEach((i) => { stock[i.dataset.g] = +i.value; });
      try { await api(`/api/blood-banks/${btn.dataset.save}/stock`, { method: 'PATCH', body: { stock } }); toast('Stock updated'); } catch (e) { toast(e.message); }
    });
  }

  // ================================================================== ADMIN
  async function renderAdmin(main) {
    if (!S.token || !['admin', 'staff'].includes(S.user?.role)) {
      const lc = loginCard('Admin / blood-centre staff login', () => route(), { demoRole: 'admin' });
      main.innerHTML = `<div class="page-head"><div><h1>Operations dashboard</h1><p>Live requests, donor response analytics, ML demand forecast and fraud review.</p></div></div><div style="max-width:520px">${lc.html}</div>`;
      lc.bind(main);
      return;
    }
    main.innerHTML = '<div class="skeleton" style="height:400px"></div>';
    let ov = await api('/api/admin/overview');
    const [model, reports] = await Promise.all([api('/api/admin/model-info').catch(() => null), api('/api/admin/reports')]);

    const pct = (x) => `${Math.round((x || 0) * 100)}%`;
    const draw = () => {
      const k = ov.kpis;
      main.innerHTML = `
        <div class="page-head"><div><span class="eyebrow">Operations</span><h1>Live network dashboard</h1></div>
          <div class="row"><button class="btn" id="tickBtn">Run escalation cycle</button><span class="pill green">● live</span></div></div>
        <div class="kpis">
          ${[['Open requests', k.open_requests], ['Fulfilled', k.fulfilled], ['Donors available', `${k.donors_available}/${k.donors_total}`], ['Acceptance rate', pct(k.acceptance_rate)],
             ['Avg response', k.avg_response_sec != null ? `${Math.round(k.avg_response_sec)}s` : '—'], ['No-show rate', pct(k.no_show_rate)], ['Voice-created', pct(k.voice_share)], ['Open fraud reports', k.open_reports]]
            .map(([l, n]) => `<div class="kpi"><div class="l">${l}</div><div class="n">${n}</div></div>`).join('')}
        </div>
        <div class="grid-2">
          <section class="card"><h2>Requests</h2><div class="table-wrap" style="margin-top:.75rem"><table><thead><tr><th>Group</th><th>Hospital</th><th>Status</th><th>Units</th><th>Via</th><th>Radius</th><th>Created</th><th></th></tr></thead>
            <tbody>${ov.requests.length ? ov.requests.map((r) => `<tr class="clickable" data-go="${r.id}"><td><span class="bg-badge sm">${esc(r.blood_group)}</span></td><td>${esc(r.hospital.slice(0, 34))}</td><td>${statusPill(r.status)}</td><td>${r.fulfilled}/${r.units}</td><td>${esc(r.via)} · ${esc(r.lang)}</td><td>${r.radius_km} km</td><td>${fmtTime(r.created_at)}</td>
              <td>${['pending', 'searching', 'donor_committed'].includes(r.status) ? `<button class="btn small ghost" data-expire="${r.id}" title="Demo: fast-forward response window">⏩ expire</button>` : ''}</td></tr>`).join('') : '<tr><td colspan="8" class="muted">No requests yet</td></tr>'}</tbody></table></div></section>
          <section class="card"><h2>Live event feed</h2><ul class="timeline feed" style="margin-top:1rem">${ov.events.map((e) => `<li><time>${fmtTime(e.at)} · ${esc(e.request_id)}</time>${esc(e.message)}</li>`).join('')}</ul></section>
        </div>
        <div class="grid-2" style="margin-top:1.5rem">
          <section class="card"><h2>Supply vs demand by blood group</h2><div class="chart-box" style="margin-top:.75rem"><canvas id="sdChart"></canvas></div></section>
          <section class="card"><div class="row between"><h2>ML demand forecast (7 days)</h2>
            <select class="lang-select" id="fcArea">${['central', 'north', 'south', 'east', 'west'].map((a) => `<option>${a}</option>`).join('')}</select></div>
            <div class="chart-box" style="margin-top:.75rem"><canvas id="fcChart"></canvas></div></section>
        </div>
        <div class="grid-2" style="margin-top:1.5rem">
          <section class="card"><h2>Fraud &amp; safety reports</h2><div class="stack small" style="margin-top:.75rem">${reports.length ? reports.map((r) => `<div class="row between"><div><b>${esc(r.reason.replace('_', ' '))}</b> — ${esc(r.reported_user?.name || '')}<div class="xs muted">${esc(r.details)} · ${fmtDT(r.created_at)}</div></div>
            <div class="row">${statusPill(r.status === 'open' ? 'pending' : r.status === 'actioned' ? 'cancelled' : 'fulfilled')}${r.reported_user && !r.reported_user.suspended && S.user.role === 'admin' ? `<button class="btn small danger-ghost" data-suspend="${r.reported_user.id}">Suspend</button>` : r.reported_user?.suspended ? '<span class="pill red">suspended</span>' : ''}</div></div>`).join('') : '<span class="muted">No reports. Requesters can report payment demands or fake profiles from the request page.</span>'}</div></section>
          <section class="card"><h2>ML models</h2>${model ? `<div class="stack small" style="margin-top:.75rem">
            <div class="row between"><span>Donor acceptance · ${esc(model.acceptance.algorithm)}</span><span class="pill blue">AUC ${model.acceptance.roc_auc}</span></div>
            <div class="row between"><span>No-show risk · ${esc(model.no_show.algorithm)}</span><span class="pill blue">AUC ${model.no_show.roc_auc}</span></div>
            <div class="row between"><span>Demand forecast · ${esc(model.demand.algorithm)}</span><span class="pill blue">MAE ${model.demand.mae}</span></div>
            <div class="chart-box" style="height:200px"><canvas id="fiChart"></canvas></div>
            <p class="xs muted">Trained on ${esc(model.data)} data at ${fmtDT(model.trained_at)}. Retrained on every Docker build.</p></div>` : '<p class="muted small">ML service offline — matching is using the heuristic fallback.</p>'}</section>
        </div>`;
      bind();
      charts();
    };

    const charts = async () => {
      S.charts.forEach((c) => c.destroy()); S.charts = [];
      if (!window.Chart) return;
      Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
      Chart.defaults.color = '#6d625a';
      const g = Object.keys(ov.donors_by_group);
      S.charts.push(new Chart($('#sdChart'), { type: 'bar', data: { labels: g, datasets: [
        { label: 'Registered donors', data: g.map((x) => ov.donors_by_group[x]), backgroundColor: '#2b5c8a', borderRadius: 4 },
        { label: 'Requests', data: g.map((x) => ov.requests_by_group[x]), backgroundColor: '#b42318', borderRadius: 4 }] },
        options: { maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } }, x: { grid: { display: false } } } } }));
      if (model) {
        const fi = model.acceptance.feature_importance;
        S.charts.push(new Chart($('#fiChart'), { type: 'bar', data: { labels: Object.keys(fi).map((s) => s.replace(/_/g, ' ')), datasets: [{ label: 'Feature importance', data: Object.values(fi), backgroundColor: '#b42318', borderRadius: 4 }] },
          options: { indexAxis: 'y', maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { grid: { display: false } } } } }));
      }
      loadForecast();
    };

    let fcChart;
    const loadForecast = async () => {
      try {
        const area = $('#fcArea').value;
        const f = await api(`/api/admin/forecast?area=${area}&days=7`);
        const labels = Object.keys(f.totals_by_blood_group);
        if (fcChart) fcChart.destroy();
        fcChart = new Chart($('#fcChart'), { type: 'bar', data: { labels, datasets: [{ label: `Expected requests next 7 days (${area})`, data: Object.values(f.totals_by_blood_group), backgroundColor: labels.map((l) => l.endsWith('-') ? '#861a11' : '#e07a6f'), borderRadius: 4 }] },
          options: { maintainAspectRatio: false, plugins: { legend: { position: 'bottom' } }, scales: { y: { beginAtZero: true }, x: { grid: { display: false } } } } });
        S.charts.push(fcChart);
      } catch { const b = $('#fcChart'); if (b) b.parentElement.innerHTML = '<p class="muted small">ML service offline.</p>'; }
    };

    const bind = () => {
      $$('[data-go]').forEach((tr) => tr.onclick = (e) => { if (!e.target.closest('button')) location.hash = `#/request/${tr.dataset.go}`; });
      $$('[data-expire]').forEach((b) => b.onclick = async () => { try { const r = await api(`/api/admin/simulate-expiry/${b.dataset.expire}`, { method: 'POST' }); toast(`Expired ${r.expired}, no-shows ${r.no_shows} → escalated`); } catch (e) { toast(e.message); } });
      $$('[data-suspend]').forEach((b) => b.onclick = async () => { await api(`/api/admin/users/${b.dataset.suspend}/suspend`, { method: 'POST', body: { suspend: true } }); toast('User suspended'); route(); });
      $('#tickBtn').onclick = async () => { const r = await api('/api/admin/tick', { method: 'POST' }); toast(`Cycle done: ${r.expired} expired, ${r.no_shows} no-shows`); };
      $('#fcArea').onchange = loadForecast;
    };

    draw();
    let pending;
    subscribe(['admin'], () => {
      clearTimeout(pending);
      pending = setTimeout(async () => { ov = await api('/api/admin/overview'); draw(); }, 400);
    });
  }

  // ------------------------------------------------------------------ router
  async function route() {
    cleanup();
    const main = $('#main');
    const hash = location.hash.replace(/^#\/?/, '');
    const [name, arg] = hash.split('/');
    const key = name || 'assistant';
    $$('.tabs a').forEach((a) => a.classList.toggle('active', a.dataset.route === (key === 'request' ? 'requests' : key)));
    try {
      if (key === 'assistant') return renderAssistant(main);
      if (key === 'requests') return await renderRequests(main);
      if (key === 'request' && arg) return await renderRequest(main, arg);
      if (key === 'donor') return await renderDonor(main);
      if (key === 'banks') return await renderBanks(main);
      if (key === 'admin') return await renderAdmin(main);
      main.innerHTML = '<div class="empty">Page not found. <a href="#/">Go to assistant</a></div>';
    } catch (e) {
      main.innerHTML = `<div class="card empty"><p><b>Could not load this page.</b></p><p class="small">${esc(e.message)}</p><p class="small" style="margin-top:.5rem">Is the backend running? <a href="#/">Retry</a></p></div>`;
    }
  }

  // ------------------------------------------------------------------ boot
  $('#langSelect').onchange = (e) => { setLang(e.target.value); S.sid = null; S.chat = []; route(); };
  window.addEventListener('hashchange', route);
  applyLang();
  renderUserChip();
  if (!S.lang) { S.lang = 'en'; applyLang(); showLangGate(); } else route();
})();
