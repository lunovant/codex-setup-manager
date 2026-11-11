"use strict";
(function () {
  var S = {};            // strings
  var STATUS = null;
  var lang = "en";
  var pending = {};      // tab -> pending sandbox mode / backup id

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
    $("l-env-warn").textContent = STATUS && STATUS.is_windows ? t("env_warn_win") : t("env_warn_posix");
    renderStatus();
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
    row(dl, t("hdr_key"), s.masked_key + " [" + (s.secret_backend || t("none")) + "]");
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
  function showTab(name) {
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
      var tabs = Array.prototype.filter.call(document.querySelectorAll("#nav [role=tab]"), function (x) { return !x.hidden; });
      var i = tabs.indexOf(b);
      if (e.key === "ArrowDown" || e.key === "ArrowRight") { tabs[(i + 1) % tabs.length].focus(); e.preventDefault(); }
      if (e.key === "ArrowUp" || e.key === "ArrowLeft") { tabs[(i - 1 + tabs.length) % tabs.length].focus(); e.preventDefault(); }
    });
  });
  $("lang").addEventListener("change", function () { setLang($("lang").value); });
  $("refresh").addEventListener("click", function () { refreshStatus(); loadModels(); });

  function init() {
    api("default_lang").then(function (r) { return setLang(r.lang || "en"); })
      .then(refreshStatus).then(loadModels);
  }
  if (window.pywebview && window.pywebview.api) init();
  else window.addEventListener("pywebviewready", init);
})();
