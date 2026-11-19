"use strict";
(function () {
  var S = {};            // strings
  var STATUS = null;
  var lang = "en";
  var pending = {};
  var DET = { seq: 0, lines: null, pending: false, timer: null };
  var OC = { running: false, view: null, timer: null };      // tab -> pending sandbox mode / backup id

  function $(id) { return document.getElementById(id); }
  function t(key, params) {
    var s = S[key] !== undefined ? S[key] : key;
    if (params) { Object.keys(params).forEach(function (k) { s = s.split("{" + k + "}").join(String(params[k])); }); }
    return s;
  }
  function api(name) {
    var args = Array.prototype.slice.call(arguments, 1);
    return window.pywebview.api[name].apply(null, args).catch(function (e) {
      return { ok: false, error: String(e && e.message || e) };
    });
  }

  function say(text, kind) {
    var m = $("message");
    m.textContent = text || "";
    m.className = "message" + (kind ? " " + kind : "");
    m.hidden = !text;
  }
  function fail(res) { say(t("g_error") + ": " + (res.error || "?"), "error"); }

  function setDiff(preId, res) {
    var pre = $(preId);
    pre.textContent = "";
    var text = res.diff || "";
    if (!text) { pre.textContent = res.changed === false ? t("g_no_diff") : ""; return; }
    text.split("\n").forEach(function (line) {
      var span = document.createElement("span");
      if (line.charAt(0) === "+" && line.indexOf("+++") !== 0) span.className = "add";
      else if (line.charAt(0) === "-" && line.indexOf("---") !== 0) span.className = "del";
      span.textContent = line + "\n";
      pre.appendChild(span);
    });
    (res.notes || []).forEach(function (n) {
      var span = document.createElement("span");
      span.textContent = n + "\n";
      pre.appendChild(span);
    });
  }

  function applyStrings() {
    document.documentElement.lang = lang;
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      el.textContent = t(el.getAttribute("data-i18n"));
    });
    $("nav-adv").textContent = t("g_nav_advanced");
    $("oc-adv").textContent = "\u25B8 " + t("g_nav_advanced");
    $("oc-eye").textContent = t($("oc-key").type === "password" ? "oc_show" : "oc_hide");
    if (!OC.running) $("oc-go-text").textContent = t("oc_install");
    $("l-env-warn").textContent = STATUS && STATUS.is_windows ? t("env_warn_win") : t("env_warn_posix");
    renderStatus();
    renderMode();
  }

  function row(dl, label, value) {
    var wrap = document.createElement("div");
    var dt = document.createElement("dt"); dt.textContent = label;
    var dd = document.createElement("dd"); dd.textContent = value;
    wrap.appendChild(dt); wrap.appendChild(dd); dl.appendChild(wrap);
  }

  function renderStatus() {
    var dl = $("status");
    dl.textContent = "";
    if (!STATUS) return;
    var s = STATUS;
    var desk = s.desktop.installed ? t("desktop_installed") : (s.desktop.supported ? t("desktop_missing") : t("desktop_unsupported"));
    var cfg = { ok: t("cfg_ok"), invalid: t("cfg_invalid"), missing: t("cfg_missing") }[s.config.state] || s.config.state;
    var lt = s.last_test ? s.last_test.overall + " (" + s.last_test.model + ", " + s.last_test.when + ")" : t("never");
    row(dl, t("hdr_os"), s.os.system + " " + s.os.release + " " + s.os.machine);
    row(dl, t("hdr_cli"), s.cli.version || s.cli.path || t("not_found"));
    row(dl, t("hdr_desktop"), desk);
    row(dl, t("hdr_provider"), (s.provider || t("none")) + " / " + (s.model || t("none")));
    row(dl, t("hdr_config"), cfg + (s.config.error ? " - " + s.config.error : ""));
    row(dl, t("hdr_key"), s.masked_key === "(not set)" ? t("none") : s.masked_key + " [" + (s.secret_backend || t("none")) + "]");
    row(dl, t("hdr_test"), lt);
  }

  function refreshStatus() {
    return api("status").then(function (res) {
      if (!res.ok) { fail(res); return; }
      STATUS = res;
      $("nav-sandbox").hidden = !res.is_windows;
      applyStrings();
      $("m-current").textContent = res.model || t("none");
      if (res.is_windows) loadSandbox();
    });
  }

  function loadModels() {
    return api("models").then(function (res) {
      if (!res.ok) { fail(res); return; }
      [$("m-select")].forEach(function (sel) {
        var keep = sel.value;
        sel.textContent = "";
        res.models.forEach(function (m) {
          var o = document.createElement("option"); o.value = m; o.textContent = m; sel.appendChild(o);
        });
        sel.value = keep && res.models.indexOf(keep) >= 0 ? keep : res.default;
      });
    });
  }

  // -- tabs ------------------------------------------------------------------
  function setAdvanced(open) {
    $("nav-adv-group").hidden = !open;
    $("nav-adv").setAttribute("aria-expanded", open ? "true" : "false");
  }
  function showTab(name) {
    if (name !== "oneclick") setAdvanced(true);
    document.querySelectorAll("#nav [role=tab]").forEach(function (b) {
      b.setAttribute("aria-selected", b.getAttribute("data-tab") === name ? "true" : "false");
    });
    document.querySelectorAll("main .panel").forEach(function (p) { p.hidden = p.id !== "tab-" + name; });
    say("");
    if (name === "backup") loadBackups();
    if (name === "model") loadModels();
    $("adv-intro").hidden = name === "oneclick";
  }

  // -- generic preview/apply pairing ------------------------------------------
  function guardApply(applyBtn, inputs) {
    inputs.forEach(function (el) {
      ["input", "change"].forEach(function (ev) { el.addEventListener(ev, function () { applyBtn.disabled = true; }); });
    });
  }

  // -- model ------------------------------------------------------------------
  function chosenModel() { return $("m-custom").value.trim() || $("m-select").value; }
  guardApply($("m-apply"), [$("m-select"), $("m-custom")]);
  $("m-preview").addEventListener("click", function () {
    api("change_model", chosenModel(), true).then(function (res) {
      if (!res.ok) { fail(res); return; }
      setDiff("m-diff", res); $("m-apply").disabled = false;
    });
  });
  $("m-apply").addEventListener("click", function () {
    api("change_model", chosenModel(), false).then(function (res) {
      if (!res.ok) { fail(res); return; }
      setDiff("m-diff", res); say(t("g_saved"), "ok"); $("m-apply").disabled = true;
      $("m-custom").value = ""; refreshStatus();
    });
  });

  // -- test ---------------------------------------------------------------------
  var BADGE = { ok: "g_ok", warn: "g_warn", fail: "g_fail", skip: "g_skip" };
  $("t-run").addEventListener("click", function () {
    say(t("g_working"));
    $("t-run").disabled = true;
    api("test_connection", $("t-model").value.trim() || null).then(function (res) {
      $("t-run").disabled = false;
      if (!res.ok) { fail(res); return; }
      say("");
      var tb = $("t-table").querySelector("tbody"); tb.textContent = "";
      res.steps.forEach(function (s) {
        var tr = document.createElement("tr");
        var cells = [s.step, null, s.problem_text || "-", s.detail_text];
        cells.forEach(function (c, i) {
          var td = document.createElement("td");
          if (i === 1) {
            var b = document.createElement("span");
            b.className = "badge b-" + s.outcome;
            b.textContent = t(BADGE[s.outcome] || "g_warn");
            td.appendChild(b);
          } else td.textContent = c;
          tr.appendChild(td);
        });
        tb.appendChild(tr);
      });
      $("t-table").hidden = false;
      var o = $("t-overall");
      o.className = "overall b-" + res.overall;
      o.textContent = t("g_overall") + ": " + t(BADGE[res.overall] || "g_warn");
      refreshStatus();
    });
  });

  // -- sandbox --------------------------------------------------------------------
  function loadSandbox() {
    api("sandbox_options").then(function (res) {
      if (!res.ok || !res.applicable) return;
      $("s-current").textContent = res.current || t("none");
      $("s-explain").textContent = res.explanation;
    });
  }
  function sbPreview(mode) {
    pending.sandbox = mode;
    api("set_sandbox", mode, true).then(function (res) {
      if (!res.ok) { fail(res); return; }
      setDiff("s-diff", res); $("s-apply").disabled = false;
    });
  }
  $("s-unelevated").addEventListener("click", function () { sbPreview("unelevated"); });
  $("s-elevated").addEventListener("click", function () { sbPreview("elevated"); });
  $("s-remove").addEventListener("click", function () { sbPreview(null); });
  $("s-apply").addEventListener("click", function () {
    api("set_sandbox", pending.sandbox === undefined ? null : pending.sandbox, false).then(function (res) {
      if (!res.ok) { fail(res); return; }
      setDiff("s-diff", res); say(t("g_saved"), "ok"); $("s-apply").disabled = true; refreshStatus();
    });
  });

  // -- backups ---------------------------------------------------------------------
  function loadBackups() {
    api("backups").then(function (res) {
      if (!res.ok) { fail(res); return; }
      var tb = $("b-table").querySelector("tbody"); tb.textContent = "";
      res.backups.forEach(function (b) {
        var tr = document.createElement("tr");
        [b.id, b.created, b.reason].forEach(function (v) {
          var td = document.createElement("td"); td.textContent = v; tr.appendChild(td);
        });
        var td = document.createElement("td");
        var btn = document.createElement("button");
        btn.type = "button"; btn.textContent = t("g_bk_restore");
        btn.addEventListener("click", function () { bkPreview(b.id); });
        td.appendChild(btn); tr.appendChild(td); tb.appendChild(tr);
      });
      $("b-table").hidden = res.backups.length === 0;
      $("b-none").hidden = res.backups.length !== 0;
      $("b-original").disabled = !res.has_original;
    });
  }
  function bkPreview(id) {
    pending.backup = id;  // null = original
    var call = id === null ? api("restore_original", true) : api("restore_backup", id, true);
    call.then(function (res) {
      if (!res.ok) { fail(res); return; }
      setDiff("b-diff", res); $("b-apply").disabled = false; say(t("g_confirm_backup"));
    });
  }
  $("b-original").addEventListener("click", function () { bkPreview(null); });
  $("b-create").addEventListener("click", function () {
    api("create_backup").then(function (res) {
      if (!res.ok) { fail(res); return; }
      say(t("bk_created_ok", { path: res.path }), "ok"); loadBackups();
    });
  });
  $("b-apply").addEventListener("click", function () {
    var id = pending.backup;
    var call = id === null ? api("restore_original", false) : api("restore_backup", id, false);
    call.then(function (res) {
      if (!res.ok) { fail(res); return; }
      setDiff("b-diff", res); say(t("g_saved"), "ok"); $("b-apply").disabled = true;
      loadBackups(); refreshStatus();
    });
  });

  // -- diagnostics ------------------------------------------------------------------
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }
  function runDiag(text) {
    api("diagnose", text).then(function (res) {
      if (!res.ok) { fail(res); return; }
      say("");
      var out = $("d-out"); out.textContent = "";
      res.checks.forEach(function (c) {
        var box = el("div", "issue");
        var h = el("div"); h.appendChild(el("span", "badge b-" + c.outcome, t(BADGE[c.outcome] || "g_warn")));
        h.appendChild(document.createTextNode(" " + c.title));
        box.appendChild(h);
        if (c.detail) box.appendChild(el("div", "hint", c.detail));
        if (c.fix) box.appendChild(el("div", "hint", t("dg_fix") + ": " + c.fix));
        out.appendChild(box);
      });
      res.issues.forEach(function (i) {
        var box = el("div", "issue");
        box.appendChild(el("strong", null, i.title));
        box.appendChild(el("p", null, i.explanation));
        var ol = el("ol");
        i.steps.forEach(function (s) { ol.appendChild(el("li", null, s)); });
        box.appendChild(ol); out.appendChild(box);
      });
      if (text && !res.issues.length) out.appendChild(el("p", null, t("g_diag_no_match")));
    });
  }
  $("d-explain").addEventListener("click", function () { runDiag($("d-text").value); });
  $("d-run").addEventListener("click", function () { runDiag(null); });

  // -- launch / env -------------------------------------------------------------------
  $("l-cli").addEventListener("click", function () {
    api("launch", "cli").then(function (res) { res.ok ? say(t("g_launched"), "ok") : fail(res); });
  });
  $("l-app").addEventListener("click", function () {
    api("launch", "app").then(function (res) { res.ok ? say(t("ln_app_started"), "ok") : fail(res); });
  });
  $("l-env-install").addEventListener("click", function () {
    if (!$("l-consent").checked) { say(t("env_consent"), "error"); return; }
    api("env_install", true).then(function (res) {
      res.ok ? say(t("env_installed", { where: res.where }), "ok") : fail(res);
    });
  });
  $("l-env-remove").addEventListener("click", function () {
    var map = { removed: "env_removed", restored: "env_restored", nothing: "env_nothing", not_owned: "env_not_owned", changed: "env_changed" };
    api("env_remove").then(function (res) { res.ok ? say(t(map[res.result] || "env_nothing"), "ok") : fail(res); });
  });

  // -- uninstall ------------------------------------------------------------------------
  guardApply($("u-apply"), [$("u-delete")]);
  $("u-preview").addEventListener("click", function () {
    api("uninstall", $("u-delete").checked, true).then(function (res) {
      if (!res.ok) { fail(res); return; }
      setDiff("u-diff", res); $("u-apply").disabled = false;
    });
  });
  $("u-apply").addEventListener("click", function () {
    api("uninstall", $("u-delete").checked, false).then(function (res) {
      if (!res.ok) { fail(res); return; }
      setDiff("u-diff", res); say(t("un_done"), "ok"); $("u-apply").disabled = true; refreshStatus();
    });
  });

  // -- one-click setup ---------------------------------------------------------------------
  var LINES = ["codex", "claude"];
  function fmtDate(iso) {
    if (!iso) return "?";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return String(iso);
    var p = function (n) { return (n < 10 ? "0" : "") + n; };
    return p(d.getDate()) + "/" + p(d.getMonth() + 1) + "/" + d.getFullYear();
  }
  function newSec() {
    return { models: null, probes: {}, wrote: false, result: null, defaultModel: null, currentModel: null, hasBackup: false };
  }
  function newView() {
    return { keyInfo: null, checking: false, fetching: false, lines: null, done: false, result: null, last: false,
             secs: { codex: newSec(), claude: newSec() } };
  }
  function isClaudeModel(m) { return String(m).toLowerCase().indexOf("claude-") === 0; }
  function foldStep(v, st) {
    var step = st.step, d = st.detail || {};
    if (step === "check_key") { if (d.valid !== undefined) v.keyInfo = d; else v.checking = true; }
    else if (step === "fetch_models") {
      if (d.models) {
        v.fetching = false;
        if (d.lines) v.lines = d.lines;
        var cx = v.secs.codex;
        cx.models = d.models.filter(function (m) { return !isClaudeModel(m); });
        cx.models.forEach(function (m) { if (!cx.probes[m]) cx.probes[m] = { pending: true }; });
      } else v.fetching = true;
    } else if (step === "claude_models") {
      var cl = v.secs.claude;
      cl.models = d.models || [];
      cl.models.forEach(function (m) {
        cl.probes[m] = (d.targets || []).indexOf(m) >= 0 ? { pending: true } : { untested: true };
      });
    } else if (step.indexOf("claude_probe:") === 0) v.secs.claude.probes[d.model || step.slice(13)] = d;
    else if (step.indexOf("probe:") === 0) v.secs.codex.probes[d.model || step.slice(6)] = d;
    else if (step === "write_config") v.secs.codex.wrote = true;
    else if (step === "claude_write") v.secs.claude.wrote = true;
  }
  function secFromResult(sec, r) {
    sec.result = r; sec.defaultModel = r.default_model; sec.hasBackup = r.has_backup;
    (r.models || []).forEach(function (row) { sec.probes[row.model] = row.tested === false ? { untested: true } : row; });
    if (r.models && r.models.length) sec.models = r.models.map(function (row) { return row.model; });
  }
  function viewFromPoll(res) {
    var v = newView();
    (res.steps || []).forEach(function (st) { foldStep(v, st); });
    if (res.result) {
      v.done = true; v.result = res.result;
      if (res.result.key_info) v.keyInfo = res.result.key_info;
      var secs = res.result.sections || {};
      LINES.forEach(function (n) { if (secs[n]) secFromResult(v.secs[n], secs[n]); });
      if (!Object.keys(secs).length) v.lines = [];
    }
    return v;
  }
  function viewFromLast(last) {
    var v = newView();
    v.last = true; v.done = true; v.result = { ok: true, code: "ok" }; v.keyInfo = last.key_info;
    v.lines = [];
    LINES.forEach(function (n) {
      var d = (last.sections || {})[n]; if (!d) return;
      var sec = v.secs[n]; v.lines.push(n);
      sec.models = d.models || [];
      sec.result = { ok: true, code: "ok" };
      (d.results || []).forEach(function (r) { sec.probes[r.model] = r.tested === false ? { untested: true } : r; });
      sec.models.forEach(function (m) { if (!sec.probes[m]) sec.probes[m] = { pending: false, ok: false, error: "?" }; });
      sec.defaultModel = d.default_model; sec.currentModel = d.current_model; sec.wrote = true; sec.hasBackup = true;
    });
    return v;
  }
  function line(kind, text) {
    var d = el("div", "oc-line " + kind);
    d.textContent = text;
    return d;
  }
  function errText(r) {
    var info = r.key_info || {};
    switch (r.code) {
      case "key_empty": return t("oc_err_key_empty");
      case "key_invalid": return t("oc_err_key_invalid");
      case "key_expired": return t("oc_err_key_expired", { date: fmtDate(info.expires_at) });
      case "network": return t("oc_err_network");
      case "not_codex_key": return t("oc_err_not_codex_key");
      case "no_model_works": return t("oc_err_no_model_works");
      default: return t("oc_err_generic") + (r.message ? ": " + r.message : "");
    }
  }
  function keyLine(info) {
    var parts = [t("oc_key_ok")];
    if (info.plan) parts.push(info.plan);
    if (info.remaining !== null && info.remaining !== undefined && info.remaining !== "") {
      var n = Number(info.remaining);
      parts.push((isNaN(n) ? info.remaining : String(Math.round(n * 100) / 100)) + "\u{1F48E}");
    }
    parts.push(info.expires_at ? t("oc_expires", { date: fmtDate(info.expires_at) }) : t("g_no_expiry"));
    return "✓ " + parts.join(" · ");
  }
  function modelRow(v, name, m) {
    var p = v.secs[name].probes[m] || { pending: true };
    if (p.untested) {
      var u = el("div", "oc-model");
      u.appendChild(el("span", "st", "•"));
      u.appendChild(el("span", "name", m));
      u.appendChild(el("span", "lat", t("oc_untested")));
      return u;
    }
    var row = el("div", "oc-model " + (p.pending || p.running ? "" : (p.ok ? "ok" : "warn")));
    var st = el("span", "st");
    if (p.pending || p.running) { st.appendChild(el("span", "spinner")); }
    else st.textContent = p.ok ? "✓" : "⚠";
    row.appendChild(st);
    row.appendChild(el("span", "name", m));
    if (p.pending || p.running) return row;
    if (p.ok) {
      row.appendChild(el("span", "lat", p.latency_ms !== null && p.latency_ms !== undefined ? (p.latency_ms / 1000).toFixed(1) + "s" : ""));
    } else {
      row.appendChild(el("span", "lat", p.error || "?"));
      if (!v.done) return row;  // no per-model retry while the run is still in progress
      var b = el("button", null, t("oc_retry")); b.type = "button";
      b.addEventListener("click", function () { reprobe(name, m); });
      row.appendChild(b);
    }
    return row;
  }
  function passing(v, name) {
    var sec = v.secs[name];
    return (sec.models || []).filter(function (m) { return sec.probes[m] && sec.probes[m].ok; });
  }
  function lineInfo(name) {
    var s = STATUS || {};
    if (name === "claude") {
      var c = s.claude || {};
      return { installed: !!c.installed, mode: c.mode, login: !!c.login };
    }
    return { installed: !!s.lunovant_installed, mode: s.mode, login: !!s.chatgpt_login };
  }
  function modeCard(name) {
    var info = lineInfo(name);
    if (!info.installed) return null;
    var cl = name === "claude";
    var personal = info.mode === "personal";
    var card = el("div", "mode-card");
    card.appendChild(el("h4", null, t(personal ? "g_cur_personal" : "g_cur_lunovant", {
      line: t(cl ? "g_line_claude" : "g_line_codex"), account: t(cl ? "g_acct_claude" : "g_acct_chatgpt") })));
    var b = el("button", null, t(personal ? "g_cur_to_lunovant" : (cl ? "g_cur_to_claude" : "g_cur_to_chatgpt")));
    b.type = "button";
    b.disabled = !personal && !info.login;
    b.addEventListener("click", function () { switchMode(name, personal ? "lunovant" : "personal"); });
    var r = el("div", "row"); r.appendChild(b); card.appendChild(r);
    if (!personal && !info.login) card.appendChild(el("p", "hint", t(cl ? "g_claude_mode_no_login" : "g_mode_no_login")));
    card.appendChild(el("p", "hint", t(cl ? "g_cur_hint_claude" : "g_cur_hint_codex")));
    return card;
  }
  // The only place the per-line "currently using" cards are rendered (above the key form).
  function renderCurrent() {
    var box = $("cur-out"); box.textContent = "";
    var any = false;
    LINES.forEach(function (n) {
      var mc = modeCard(n);
      if (mc) { box.appendChild(mc); any = true; }
    });
    $("un-main").hidden = !any;
    if (!any) $("un-confirm").hidden = true;
  }
  function launchRow(v, name) {
    var sec = v.secs[name];
    var r = el("div", "row oc-launch");
    if (name === "claude") {
      var c = (STATUS && STATUS.claude) || {};
      if (c.terminal) {
        var tb = el("button", "primary", t("oc_open_claude_terminal")); tb.type = "button";
        tb.addEventListener("click", function () {
          api("launch", "claude").then(function (res) { res.ok ? say(t("g_launched"), "ok") : fail(res); });
        });
        r.appendChild(tb);
      } else {
        r.appendChild(el("span", null, t("oc_claude_run")));
        r.appendChild(cmdRow(c.command || "claude"));
      }
      return r;
    }
    var app = el("button", "primary", t("oc_open_app")); app.type = "button";
    app.addEventListener("click", function () {
      api("launch", "app").then(function (res) { res.ok ? say(t("ln_app_started"), "ok") : fail(res); });
    });
    var cli = el("button", null, t("oc_open_cli")); cli.type = "button";
    cli.addEventListener("click", function () {
      api("launch", "cli").then(function (res) { res.ok ? say(t("g_launched"), "ok") : fail(res); });
    });
    r.appendChild(app); r.appendChild(cli);
    var want = sec.currentModel || sec.defaultModel;
    var pass = passing(v, name);
    var wantOk = pass.indexOf(want) >= 0;
    var lab = el("label", "oc-defl", t("oc_default_model") + ":"); lab.htmlFor = "oc-default";
    var sel = el("select"); sel.id = "oc-default";
    // Never show a replacement as if it were saved: the select mirrors the real config.
    if (!wantOk) {
      var ph = document.createElement("option");
      ph.value = ""; ph.disabled = true; ph.textContent = t("oc_pick_model"); sel.appendChild(ph);
    }
    pass.forEach(function (m) { var o = document.createElement("option"); o.value = m; o.textContent = m; sel.appendChild(o); });
    sel.value = wantOk ? want : "";
    var changed = el("span", "b-ok"); changed.hidden = true;
    sel.addEventListener("change", function () {
      changed.hidden = true;
      api("set_default_model", sel.value).then(function (res) {
        if (!res.ok) { fail(res); return; }
        changed.textContent = "✓ " + t("oc_changed"); changed.hidden = false;
        sec.currentModel = sel.value;
        refreshStatus();
      });
    });
    r.appendChild(lab); r.appendChild(sel); r.appendChild(changed);
    return r;
  }
  function renderSec(v, name) {
    var sec = v.secs[name];
    var box = el("div", "oc-sec");
    box.appendChild(el("h3", null, t(name === "claude" ? "g_line_claude" : "g_line_codex")));
    if (sec.models && sec.models.length) {
      box.appendChild(line("ok", "✓ " + t("oc_models_found", { n: sec.models.length })));
      if (name === "claude" && !v.done) box.appendChild(el("p", "hint", t("oc_claude_tested")));
      var list = el("div", "oc-models");
      sec.models.forEach(function (m) { list.appendChild(modelRow(v, name, m)); });
      box.appendChild(list);
    }
    var failed = v.done && sec.result && !sec.result.ok;
    if (failed) {
      box.appendChild(line("fail", "⚠ " + errText(sec.result)));
      var rr = el("div", "row");
      var retry = el("button", "primary", t("oc_retry")); retry.type = "button";
      retry.addEventListener("click", retryOC);
      rr.appendChild(retry); box.appendChild(rr);
    }
    var ok = v.done && sec.result && sec.result.ok;
    if (sec.wrote && ok) {
      var cl = name === "claude";
      box.appendChild(line("ok", "✓ " + t(cl ? (sec.hasBackup ? "oc_wrote_claude" : "oc_wrote_claude_nobackup")
                                              : (sec.hasBackup ? "oc_wrote" : "oc_wrote_nobackup"))));
      var want = sec.currentModel || sec.defaultModel;
      if (cl || passing(v, name).indexOf(want) >= 0) box.appendChild(line("ok", "✓ " + t(cl ? "oc_ready_claude" : "oc_ready")));
      else box.appendChild(line("warn", "⚠ " + t("oc_default_broken", { model: want || "?" })));
      if (!cl && sec.result.catalog_text) box.appendChild(line(sec.result.catalog && sec.result.catalog.ok ? "ok" : "warn", (sec.result.catalog && sec.result.catalog.ok ? "✓ " : "⚠ ") + sec.result.catalog_text));
    }
    if (ok) {
      box.appendChild(launchRow(v, name));
    }
    return box;
  }
  function retryOC() {
    if ($("oc-key").value) startOC(); else { showForm(true); $("oc-key").focus(); }
  }
  function renderOC(v) {
    OC.view = v;
    var out = $("oc-out"); out.textContent = "";
    var failed = v.done && v.result && !v.result.ok;
    if (v.checking && !v.keyInfo && !failed) out.appendChild(line("", t("oc_checking")));
    if (v.keyInfo && v.keyInfo.valid && !v.keyInfo.expired) out.appendChild(line("ok", keyLine(v.keyInfo)));
    if (v.fetching && !v.lines && !(v.secs.codex.models && v.secs.codex.models.length)) out.appendChild(line("", t("oc_fetching")));
    var shown = {};
    (v.lines || (v.secs.codex.models && v.secs.codex.models.length ? ["codex"] : [])).forEach(function (n) {
      if (v.done && !v.secs[n].result && !v.secs[n].models) return;
      shown[n] = true; out.appendChild(renderSec(v, n));
    });
    if (failed && !Object.keys(shown).length || (failed && !v.result.sections)) {
      out.appendChild(line("fail", "⚠ " + errText(v.result)));
      var r = el("div", "row");
      var retry = el("button", "primary", t("oc_retry")); retry.type = "button";
      retry.addEventListener("click", retryOC);
      r.appendChild(retry); out.appendChild(r);
    }
  }
  function showForm(show) {
    $("oc-form").hidden = !show;
    $("oc-recheck-row").hidden = show || !(OC.view && OC.view.last);
  }
  // -- key -> lines detection (decides which personal-login questions are shown) ---------------
  function detStatus(text, cls) {
    var p = $("oc-lines"); p.textContent = text || ""; p.hidden = !text; p.className = "hint" + (cls ? " " + cls : "");
  }
  function detReset() {
    DET.seq++; DET.lines = null; DET.pending = false;
    clearTimeout(DET.timer); detStatus("");
    syncGo(); renderMode();
  }
  function detRun() {
    var key = $("oc-key").value.trim();
    var seq = ++DET.seq;
    DET.pending = true; DET.lines = null; syncGo(); renderMode();
    detStatus(t("oc_detecting"));
    api("detect_lines", key).then(function (res) {
      if (seq !== DET.seq) return;           // stale: the key changed meanwhile
      DET.pending = false; syncGo();   // user now picks radios and clicks Install themselves
      if (res.ok) {
        DET.lines = res.lines || [];
        var both = DET.lines.length > 1;
        detStatus(t(both ? "oc_lines_both" : "oc_lines_" + DET.lines[0]), "ok");
      } else {
        DET.lines = null;
        detStatus(errText({ code: res.error_code, message: res.error }), "warn");
      }
      renderMode();
    });
  }
  $("oc-key").addEventListener("input", function () {
    detReset();
    if ($("oc-key").value.trim().length >= 20) {
      // debounce + request both count as "checking": Install/Enter stay disabled until the result
      DET.pending = true; syncGo(); detStatus(t("oc_detecting"));
      DET.timer = setTimeout(detRun, 600);
    }
  });
  function syncGo() { $("oc-go").disabled = OC.running || DET.pending; }
  function setRunning(on) {
    OC.running = on;
    $("oc-go").disabled = on || DET.pending; $("oc-key").disabled = on; $("oc-recheck").disabled = on;
    $("oc-spin").hidden = !on;
    $("oc-go-text").textContent = t(on ? "oc_running" : "oc_install");
  }
  function pollOC() {
    api("one_click_poll").then(function (res) {
      if (!res.ok) { setRunning(false); fail(res); return; }
      renderOC(viewFromPoll(res));
      if (res.running) { OC.timer = setTimeout(pollOC, 300); return; }
      setRunning(false);
      var secs = (res.result && res.result.sections) || {};
      var anyOk = Object.keys(secs).some(function (n) { return secs[n].ok; });
      if (res.result && res.result.ok) { $("oc-key").value = ""; detReset(); showForm(false); OC.view.last = false; $("oc-recheck-row").hidden = true; }
      else { if (anyOk) { $("oc-key").value = ""; detReset(); } showForm(true); }
      if (anyOk) { refreshStatus(); loadModels(); }
    });
  }
  function startOC(keyOverride) {
    if (OC.running) return;
    // Detection (debounce or request) running: its result decides which questions exist.
    if (keyOverride === undefined && DET.pending) return;  // still checking the key: no click/Enter
    var key = keyOverride !== undefined ? keyOverride : $("oc-key").value;
    say("");
    setRunning(true);
    OC.view = newView(); OC.view.checking = true; renderOC(OC.view);
    // A hidden group never sends a choice: only a visible question yields "personal".
    var modeEl = document.querySelector("input[name=oc-mode]:checked");
    var mode = (!$("oc-mode-ask").hidden && modeEl) ? modeEl.value : "lunovant";
    var cEl = document.querySelector("input[name=oc-mode-claude]:checked");
    var cMode = (!$("oc-mode-ask-claude").hidden && cEl) ? cEl.value : "lunovant";
    api("one_click_start", key, mode, cMode).then(function (res) {
      if (!res.ok) { setRunning(false); say(res.busy ? t("oc_busy") : t("g_error") + ": " + (res.error || "?"), "error"); return; }
      pollOC();
    });
  }
  var RECHECK = { busy: false, max: 3 };
  // `v` pins the call to the view it started from: a result arriving after uninstall, a new
  // setup or loadLast replaced OC.view is dropped instead of re-rendering a stale view.
  function reprobe(name, m, v) {
    v = v || OC.view; if (!v || OC.view !== v) return Promise.resolve();
    v.secs[name].probes[m] = { running: true }; renderOC(v);
    return api("reprobe_model", m, name).then(function (res) {
      if (OC.view !== v) return;
      v.secs[name].probes[m] = res.ok ? res.result : { ok: false, error: res.error || "?" };
      renderOC(v);
    });
  }
  $("oc-go").addEventListener("click", function () { startOC(); });
  $("oc-key").addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); startOC(); } });
  $("oc-eye").addEventListener("click", function () {
    var k = $("oc-key"); k.type = k.type === "password" ? "text" : "password";
    $("oc-eye").setAttribute("aria-pressed", k.type === "text" ? "true" : "false");
    $("oc-eye").textContent = t(k.type === "password" ? "oc_show" : "oc_hide");
  });
  $("oc-adv").addEventListener("click", function () { setAdvanced(true); $("nav-adv").focus(); });
  $("oc-change").addEventListener("click", function () { showForm(true); $("oc-key").focus(); });
  // "Check again" re-probes every tested model with the stored key (the key is never shown).
  $("oc-recheck").addEventListener("click", function () {
    var v = OC.view; if (!v || RECHECK.busy) return;
    var jobs = [];
    LINES.forEach(function (n) {
      (v.secs[n].models || []).forEach(function (m) {
        if (v.secs[n].probes[m] && v.secs[n].probes[m].untested) return;
        jobs.push([n, m]);
      });
    });
    if (!jobs.length) return;
    var btn = $("oc-recheck"), done = 0, next = 0, total = jobs.length;
    RECHECK.busy = true; btn.disabled = true;
    function progress() { btn.textContent = t("oc_rechecking", { done: Math.min(done + 1, total), total: total }); }
    progress();
    // At most RECHECK.max probes in flight; a rejected call never stalls the pool or the button.
    function worker() {
      if (next >= total || OC.view !== v) return Promise.resolve();  // view replaced: stop
      var j = jobs[next++];
      return Promise.resolve().then(function () { return reprobe(j[0], j[1], v); })
        .catch(function () {})
        .then(function () { done++; progress(); return worker(); });
    }
    var pool = [];
    for (var i = 0; i < Math.min(RECHECK.max, total); i++) pool.push(worker());
    Promise.all(pool).then(finish, finish);
    function finish() {
      RECHECK.busy = false; btn.disabled = OC.running; btn.textContent = t("oc_recheck");
    }
  });
  function loadLast() {
    return api("one_click_last").then(function (res) {
      if (!res.ok || !res.has_last || OC.running) return;
      var v = viewFromLast(res);
      showForm(false); renderOC(v); showForm(false);
      var lt = $("oc-last");
      lt.textContent = t("oc_last_title") + (res.when ? " " + t("oc_last_when", { when: res.when }) : "");
      lt.hidden = false;
    });
  }

  // -- mode switch + how-to -------------------------------------------------------------------
  function renderMode() {
    var st = STATUS || {};
    var cl = st.claude || {};
    var ln = DET.lines || [];
    $("oc-mode-ask").hidden = !(st.chatgpt_login && ln.indexOf("codex") >= 0);
    $("oc-mode-ask-claude").hidden = !(cl.login && ln.indexOf("claude") >= 0);
    renderCurrent();
    if (OC.view) renderOC(OC.view);
    $("howto").hidden = !(st.lunovant_installed || cl.installed);
    if (st.lunovant_installed || cl.installed) renderHowto();
  }
  function switchMode(name, mode) {
    var info = lineInfo(name);
    if (!STATUS || info.mode === mode) return;
    api("set_mode", mode, false, name).then(function (res) {
      if (!res.ok) { fail(res); return; }
      say(t(name === "claude" ? "g_claude_mode_switched" : "g_mode_switched"), "ok");
      return refreshStatus();
    });
  }

  // -- uninstall from the main screen: preview -> confirm -> run ---------------------------------
  $("un-go").addEventListener("click", function () {
    $("un-go").disabled = true; $("un-result").hidden = true;
    api("uninstall", true, true).then(function (res) {
      $("un-go").disabled = false;
      if (!res.ok) { fail(res); return; }
      setDiff("un-main-diff", res);
      $("un-confirm").hidden = false;
    });
  });
  $("un-no").addEventListener("click", function () { $("un-confirm").hidden = true; });
  $("un-yes").addEventListener("click", function () {
    $("un-yes").disabled = true;
    api("uninstall", true, false).then(function (res) {
      $("un-yes").disabled = false;
      if (!res.ok) { fail(res); return; }
      $("un-confirm").hidden = true;
      OC.view = null; $("oc-out").textContent = ""; $("oc-last").hidden = true;
      showForm(true);
      // Notes (failed key deletion, edited-after-setup values kept) must stay visible after the cards vanish.
      var notes = res.notes || [];
      var ul = $("un-result-notes"); ul.textContent = "";
      notes.forEach(function (n) { ul.appendChild(el("li", null, n)); });
      $("un-result-title").textContent = t(notes.length ? "g_un_main_partial" : "un_done");
      $("un-result").hidden = false;
      say(t(notes.length ? "g_un_main_partial" : "un_done"), notes.length ? "error" : "ok");
      return refreshStatus();
    });
  });

  function cmdRow(text) {
    var r = el("div", "cmd");
    r.appendChild(el("code", null, text));
    var b = el("button", null, t("g_copy")); b.type = "button";
    b.addEventListener("click", function () {
      var done = function () { b.textContent = t("g_copied"); setTimeout(function () { b.textContent = t("g_copy"); }, 1500); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, function () {});
      else { var ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta); ta.select(); try { document.execCommand("copy"); done(); } catch (e) {} document.body.removeChild(ta); }
    });
    r.appendChild(b);
    return r;
  }
  function renderHowto() {
    var box = $("howto-body"); box.textContent = "";
    var st = STATUS || {};
    if (st.lunovant_installed) {
      box.appendChild(el("h4", null, t("g_howto_desktop_t")));
      box.appendChild(el("p", null, t("g_howto_desktop")));
      box.appendChild(el("h4", null, t("g_howto_ide_t")));
      box.appendChild(el("p", null, t("g_howto_ide")));
      box.appendChild(el("h4", null, t("g_howto_cli_t")));
      box.appendChild(el("p", null, t("g_howto_cli_default")));
      box.appendChild(cmdRow("codex"));
      box.appendChild(el("p", null, t("g_howto_cli_profile")));
      box.appendChild(cmdRow("codex -p lunovant"));
      box.appendChild(el("p", null, t("g_howto_cli_model")));
      box.appendChild(cmdRow("/model"));
    }
    if (st.claude && st.claude.installed) {
      box.appendChild(el("h4", null, t("g_howto_claude_t")));
      box.appendChild(el("p", null, t("g_howto_claude_cli")));
      box.appendChild(cmdRow("claude"));
      box.appendChild(el("p", null, t("g_howto_claude_profile")));
      box.appendChild(cmdRow(st.claude.profile_command || "claude --settings ~/.claude/lunovant-settings.json"));
      box.appendChild(el("p", null, t("g_howto_claude_model")));
      box.appendChild(cmdRow("/model sonnet"));
      box.appendChild(el("h4", null, t("g_howto_claude_ide_t")));
      box.appendChild(el("p", null, t("g_howto_claude_ide")));
      box.appendChild(el("p", null, "• " + t("g_howto_claude_desktop")));
    }
    box.appendChild(el("h4", null, t("g_howto_notes_t")));
    if (st.lunovant_installed) {
      box.appendChild(el("p", null, "• " + t("g_howto_note_title")));
      box.appendChild(el("p", null, "• " + t("g_howto_note_cloud")));
    }
    box.appendChild(el("p", null, "• " + t("g_howto_note_balance")));
    box.appendChild(cmdRow(t("g_dashboard_url")));
  }

  // -- init -------------------------------------------------------------------------------
  function setLang(l) {
    return api("strings", l).then(function (res) {
      if (!res.ok) return;
      S = res.strings; lang = res.lang; $("lang").value = lang; applyStrings();
    });
  }
  document.querySelectorAll("#nav [role=tab]").forEach(function (b) {
    b.addEventListener("click", function () { showTab(b.getAttribute("data-tab")); });
    b.addEventListener("keydown", function (e) {
      var tabs = Array.prototype.filter.call(document.querySelectorAll("#nav [role=tab]"), function (x) { return !x.hidden && !x.closest("[hidden]"); });
      var i = tabs.indexOf(b);
      if (e.key === "ArrowDown" || e.key === "ArrowRight") { tabs[(i + 1) % tabs.length].focus(); e.preventDefault(); }
      if (e.key === "ArrowUp" || e.key === "ArrowLeft") { tabs[(i - 1 + tabs.length) % tabs.length].focus(); e.preventDefault(); }
    });
  });
  $("nav-adv").addEventListener("click", function () { setAdvanced($("nav-adv-group").hidden); });
  $("lang").addEventListener("change", function () { setLang($("lang").value); });
  $("refresh").addEventListener("click", function () { refreshStatus(); loadModels(); });

  function init() {
    api("default_lang").then(function (r) { return setLang(r.lang || "en"); })
      .then(refreshStatus).then(loadModels).then(loadLast)
      .then(refreshCatalog);
  }
  // Background: keep the Codex model list in line with what Lunovant sells. Shows one line
  // only when something changed; the window stays usable meanwhile.
  function refreshCatalog() {
    api("refresh_catalog").then(function (res) {
      var el = $("catalog-note");
      if (!res.ok || !res.text) return;
      el.textContent = res.text;
      el.hidden = false;
    });
  }
  if (window.pywebview && window.pywebview.api) init();
  else window.addEventListener("pywebviewready", init);
})();
