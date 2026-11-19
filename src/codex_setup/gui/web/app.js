"use strict";
(function () {
  var S = {};            // strings
  var STATUS = null;
  var lang = "en";
  var pending = {};
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
      if (res.base_url && !$("a-url").value) $("a-url").value = res.base_url;
      if (res.is_windows) loadSandbox();
    });
  }

  function loadModels() {
    return api("models").then(function (res) {
      if (!res.ok) { fail(res); return; }
      [$("q-model"), $("m-select")].forEach(function (sel) {
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
  }

  // -- generic preview/apply pairing ------------------------------------------
  function guardApply(applyBtn, inputs) {
    inputs.forEach(function (el) {
      ["input", "change"].forEach(function (ev) { el.addEventListener(ev, function () { applyBtn.disabled = true; }); });
    });
  }

  // -- quick setup ------------------------------------------------------------
  function backendOk() {
    var file = $("q-backend").value === "file";
    $("q-file-warn").hidden = !file;
    return !file || $("q-file-ok").checked;
  }
  $("q-backend").addEventListener("change", function () { backendOk(); $("q-apply").disabled = true; });
  $("q-file-ok").addEventListener("change", function () { backendOk(); });
  guardApply($("q-apply"), [$("q-url"), $("q-model")]);
  $("q-preview").addEventListener("click", function () {
    say(t("g_working"));
    api("preview_setup", $("q-url").value, $("q-model").value).then(function (res) {
      if (!res.ok) { fail(res); return; }
      say("");
      setDiff("q-diff", res);
      $("q-apply").disabled = false;
    });
  });
  $("q-apply").addEventListener("click", function () {
    if (!backendOk()) { say(t("file_confirm"), "error"); return; }
    var key = $("q-key").value;
    var btn = $("q-apply"); btn.disabled = true;
    api("quick_setup", $("q-url").value, $("q-model").value, key || null, $("q-backend").value, false).then(function (res) {
      if (!res.ok) { fail(res); btn.disabled = false; return; }
      $("q-key").value = "";
      setDiff("q-diff", res);
      var msg = t("qs_done");
      if (key && res.backend) msg = t("g_key_saved", { backend: res.backend }) + " " + msg;
      if (res.backend === "session") msg += " " + t("g_session_warn");
      if (res.backup) msg += " " + t("applied_backup", { path: res.backup });
      say(msg, "ok");
      refreshStatus();
    });
  });

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

  // -- api & key ----------------------------------------------------------------
  guardApply($("a-apply"), [$("a-url"), $("a-key"), $("a-delete")]);
  $("a-preview").addEventListener("click", function () {
    api("set_api", $("a-url").value || null, null, $("a-delete").checked, true).then(function (res) {
      if (!res.ok) { fail(res); return; }
      setDiff("a-diff", res); $("a-apply").disabled = false;
    });
  });
  $("a-apply").addEventListener("click", function () {
    var key = $("a-key").value;
    api("set_api", $("a-url").value || null, key || null, $("a-delete").checked, false).then(function (res) {
      if (!res.ok) { fail(res); return; }
      $("a-key").value = ""; $("a-delete").checked = false;
      setDiff("a-diff", res);
      say(key && res.backend ? t("g_key_saved", { backend: res.backend }) : t("g_saved"), "ok");
      $("a-apply").disabled = true; refreshStatus();
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
  function fmtDate(iso) {
    if (!iso) return "?";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return String(iso);
    var p = function (n) { return (n < 10 ? "0" : "") + n; };
    return p(d.getDate()) + "/" + p(d.getMonth() + 1) + "/" + d.getFullYear();
  }
  function newView() {
    return { keyInfo: null, models: null, probes: {}, wrote: false, done: false, result: null,
             checking: false, fetching: false, defaultModel: null, currentModel: null, hasBackup: false, last: false };
  }
  function foldStep(v, st) {
    var step = st.step, d = st.detail || {};
    if (step === "check_key") { if (d.valid !== undefined) v.keyInfo = d; else v.checking = true; }
    else if (step === "fetch_models") {
      if (d.models) { v.models = d.models; v.fetching = false;
        d.models.forEach(function (m) { if (!v.probes[m]) v.probes[m] = { pending: true }; }); }
      else v.fetching = true;
    } else if (step.indexOf("probe:") === 0) v.probes[d.model || step.slice(6)] = d;
    else if (step === "write_config") v.wrote = true;
  }
  function viewFromPoll(res) {
    var v = newView();
    (res.steps || []).forEach(function (st) { foldStep(v, st); });
    if (res.result) {
      v.done = true; v.result = res.result;
      if (res.result.key_info) v.keyInfo = res.result.key_info;
      v.defaultModel = res.result.default_model; v.hasBackup = res.result.has_backup;
      (res.result.models || []).forEach(function (r) { v.probes[r.model] = r; });
    }
    return v;
  }
  function viewFromLast(last) {
    var v = newView();
    v.last = true; v.done = true; v.result = { ok: true, code: "ok" }; v.keyInfo = last.key_info;
    v.models = last.models || [];
    (last.results || []).forEach(function (r) { v.probes[r.model] = r; });
    v.models.forEach(function (m) { if (!v.probes[m]) v.probes[m] = { pending: false, ok: false, error: "?" }; });
    v.defaultModel = last.default_model; v.currentModel = last.current_model; v.wrote = true; v.hasBackup = true;
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
  function modelRow(v, m) {
    var p = v.probes[m] || { pending: true };
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
      b.addEventListener("click", function () { reprobe(m); });
      row.appendChild(b);
    }
    return row;
  }
  function passing(v) {
    return (v.models || []).filter(function (m) { return v.probes[m] && v.probes[m].ok; });
  }
  function renderOC(v) {
    OC.view = v;
    var out = $("oc-out"); out.textContent = "";
    var failed = v.done && v.result && !v.result.ok;
    if (v.checking && !v.keyInfo && !failed) out.appendChild(line("", t("oc_checking")));
    if (v.keyInfo && v.keyInfo.valid && !v.keyInfo.expired) out.appendChild(line("ok", keyLine(v.keyInfo)));
    if (v.fetching && !v.models) out.appendChild(line("", t("oc_fetching")));
    if (v.models && v.models.length) {
      out.appendChild(line("ok", "✓ " + t("oc_models_found", { n: v.models.length })));
      var box = el("div", "oc-models");
      v.models.forEach(function (m) { box.appendChild(modelRow(v, m)); });
      out.appendChild(box);
    }
    if (failed) {
      var l = line("fail", "⚠ " + errText(v.result));
      out.appendChild(l);
      var r = el("div", "row");
      var retry = el("button", "primary", t("oc_retry")); retry.type = "button";
      retry.addEventListener("click", function () { if ($("oc-key").value) startOC(); else { showForm(true); $("oc-key").focus(); } });
      r.appendChild(retry);
      if (v.result.code === "not_codex_key") {
        var lk = el("button", null, t("oc_open_claude")); lk.type = "button";
        lk.addEventListener("click", function () { api("open_url", t("oc_claude_url")); });
        r.appendChild(lk);
      }
      out.appendChild(r);
    }
    var ok = v.done && v.result && v.result.ok;
    var want = v.currentModel || v.defaultModel;
    var pass = passing(v);
    var wantOk = pass.indexOf(want) >= 0;
    if (v.wrote && ok) {
      out.appendChild(line("ok", "\u2713 " + t(v.hasBackup ? "oc_wrote" : "oc_wrote_nobackup")));
      if (wantOk) out.appendChild(line("ok", "\u2713 " + t("oc_ready")));
      else out.appendChild(line("warn", "\u26A0 " + t("oc_default_broken", { model: want || "?" })));
    }
    $("oc-after").hidden = !ok;
    if (ok) {
      // Never show a replacement as if it were saved: the select mirrors the real config.
      var sel = $("oc-default");
      sel.textContent = "";
      if (!wantOk) {
        var ph = document.createElement("option");
        ph.value = ""; ph.disabled = true; ph.textContent = t("oc_pick_model"); sel.appendChild(ph);
      }
      pass.forEach(function (m) { var o = document.createElement("option"); o.value = m; o.textContent = m; sel.appendChild(o); });
      sel.value = wantOk ? want : "";
    }
  }
  function showForm(show) {
    $("oc-form").hidden = !show;
    $("oc-recheck-row").hidden = show || !(OC.view && OC.view.last);
  }
  function setRunning(on) {
    OC.running = on;
    $("oc-go").disabled = on; $("oc-key").disabled = on; $("oc-recheck").disabled = on;
    $("oc-spin").hidden = !on;
    $("oc-go-text").textContent = t(on ? "oc_running" : "oc_install");
  }
  function pollOC() {
    api("one_click_poll").then(function (res) {
      if (!res.ok) { setRunning(false); fail(res); return; }
      renderOC(viewFromPoll(res));
      if (res.running) { OC.timer = setTimeout(pollOC, 300); return; }
      setRunning(false);
      if (res.result && res.result.ok) { $("oc-key").value = ""; showForm(false); OC.view.last = false; $("oc-recheck-row").hidden = true; refreshStatus(); loadModels(); }
      else showForm(true);
    });
  }
  function startOC(keyOverride) {
    if (OC.running) return;
    var key = keyOverride !== undefined ? keyOverride : $("oc-key").value;
    say("");
    setRunning(true);
    OC.view = newView(); OC.view.checking = true; renderOC(OC.view);
    var modeEl = document.querySelector("input[name=oc-mode]:checked");
    var mode = (STATUS && STATUS.chatgpt_login && modeEl) ? modeEl.value : "lunovant";
    api("one_click_start", key, mode).then(function (res) {
      if (!res.ok) { setRunning(false); say(res.busy ? t("oc_busy") : t("g_error") + ": " + (res.error || "?"), "error"); return; }
      pollOC();
    });
  }
  function reprobe(m) {
    var v = OC.view; if (!v) return;
    v.probes[m] = { running: true }; renderOC(v);
    api("reprobe_model", m).then(function (res) {
      v.probes[m] = res.ok ? res.result : { ok: false, error: res.error || "?" };
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
  // "Check again" re-probes every listed model with the stored key (the key is never shown).
  $("oc-recheck").addEventListener("click", function () {
    var v = OC.view; if (!v || !v.models) return;
    $("oc-recheck").disabled = true;
    var chain = Promise.resolve();
    v.models.forEach(function (m) { chain = chain.then(function () { return new Promise(function (r) { v.probes[m] = { running: true }; renderOC(v); api("reprobe_model", m).then(function (res) { v.probes[m] = res.ok ? res.result : { ok: false, error: res.error || "?" }; renderOC(v); r(); }); }); }); });
    chain.then(function () { $("oc-recheck").disabled = false; });
  });
  $("oc-default").addEventListener("change", function () {
    var ch = $("oc-changed"); ch.hidden = true;
    api("set_default_model", $("oc-default").value).then(function (res) {
      if (!res.ok) { fail(res); return; }
      ch.textContent = "✓ " + t("oc_changed"); ch.hidden = false;
      if (OC.view) OC.view.currentModel = $("oc-default").value;
      refreshStatus();
    });
  });
  $("oc-app").addEventListener("click", function () {
    api("launch", "app").then(function (res) { res.ok ? say(t("ln_app_started"), "ok") : fail(res); });
  });
  $("oc-cli").addEventListener("click", function () {
    api("launch", "cli").then(function (res) { res.ok ? say(t("g_launched"), "ok") : fail(res); });
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

  // -- mode card + how-to -------------------------------------------------------------------
  function renderMode() {
    var st = STATUS || {};
    var show = !!st.lunovant_installed;
    $("mode-card").hidden = !show;
    $("howto").hidden = !show;
    $("oc-mode-ask").hidden = !st.chatgpt_login;
    if (!show) return;
    $("mode-lunovant").setAttribute("aria-pressed", st.mode === "lunovant" ? "true" : "false");
    $("mode-personal").setAttribute("aria-pressed", st.mode === "personal" ? "true" : "false");
    $("mode-personal").disabled = !st.chatgpt_login;
    var h = $("mode-hint");
    h.textContent = st.chatgpt_login ? "" : t("g_mode_no_login");
    h.hidden = !!st.chatgpt_login;
    renderHowto();
  }
  function switchMode(mode) {
    if (!STATUS || STATUS.mode === mode) return;
    api("set_mode", mode, false).then(function (res) {
      if (!res.ok) { fail(res); return; }
      say(t("g_mode_switched"), "ok");
      refreshStatus();
    });
  }
  $("mode-lunovant").addEventListener("click", function () { switchMode("lunovant"); });
  $("mode-personal").addEventListener("click", function () { switchMode("personal"); });

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
    box.appendChild(el("h4", null, t("g_howto_notes_t")));
    box.appendChild(el("p", null, "\u2022 " + t("g_howto_note_title")));
    box.appendChild(el("p", null, "\u2022 " + t("g_howto_note_cloud")));
    box.appendChild(el("p", null, "\u2022 " + t("g_howto_note_balance")));
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
      .then(refreshStatus).then(loadModels).then(loadLast);
  }
  if (window.pywebview && window.pywebview.api) init();
  else window.addEventListener("pywebviewready", init);
})();
