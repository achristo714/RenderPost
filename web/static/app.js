const $ = (s, el=document) => el.querySelector(s);
function toast(msg, kind="bad", ms=5000){ const t = document.createElement("div"); t.className = "toast " + kind; t.innerHTML = `<i class="dot ${kind}"></i><span>${esc(msg)}</span>`; $("#toasts").appendChild(t); setTimeout(() => t.remove(), ms); }
function ask(body, title="Confirm", yes="Continue"){ return new Promise(res => { $("#asktitle").textContent = title; $("#askbody").textContent = body; $("#askyes").textContent = yes; const m = $("#askmodal"); m.hidden = false;
  const done = v => { m.hidden = false; m.hidden = true; $("#askyes").onclick = $("#askno").onclick = null; res(v); }; $("#askyes").onclick = () => done(true); $("#askno").onclick = () => done(false); $("#askyes").focus(); }); }
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const api = (p, body) => fetch(p, body ? {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)} : {}).then(r => r.json());
let S = null, mode = "wipe", cards = {}, dirtyNotes = false, saveTimer = null, selected = new Set(), imgmode = "detail";
let vmode = "clips", frames = [], clipEls = {}, reelEls = {}, stitchSel = new Set(), view = "images";

function setSaved(t){ $("#saved").innerHTML = t ? `<i class="dot ok"></i>${t}` : ""; }
async function saveNow(extra={}){
  clearTimeout(saveTimer);
  await api("/api/config", {model:$("#model").value, quality:$("#quality").value, long_edge:$("#size").value, resolution:$("#resolution").value,
    variations:$("#variations").value, angles:$("#angles").value, style_notes:$("#notes").value, review_first:$("#review").value === "1",
    character_on:$("#charon").checked, character_note:$("#charnote").value, take_character:!!($("#takechar") && $("#takechar").checked),
    video_res:$("#vres").value, video_duration:$("#vdur").value, take_duration:$("#tdur").value, video_audio:$("#vaudio").value === "1",
    crossfade:$("#crossfade").value, motion_notes:$("#mnotes").value, shots:$("#shots").value, video_frames: JSON.stringify(frames), video_model:$("#vmodel").value, show_all_models:$("#showall").checked, energy:$("#energy").value, ...extra});
  Object.assign(S.config, {style_notes:$("#notes").value, model:$("#model").value, quality:$("#quality").value, long_edge:$("#size").value, resolution:$("#resolution").value, variations:$("#variations").value, angles:$("#angles").value,
    video_model:$("#vmodel").value, video_res:$("#vres").value, video_duration:$("#vdur").value, take_duration:$("#tdur").value, video_audio:$("#vaudio").value === "1", crossfade:$("#crossfade").value, motion_notes:$("#mnotes").value, shots:$("#shots").value, video_frames: JSON.stringify(frames)});
  setSaved("Saved"); setTimeout(() => setSaved(""), 1500);
}
function saveConfig(extra={}){
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => saveNow(extra).then(render), 250);
}

function modelOpts(table, all){ return Object.fromEntries(Object.entries(table).filter(([k,v]) => all || v.recommended).map(([k,v]) => [k, v.label])); }
function syncModel(){ const m = S.models[$("#model").value]; if (!m) return; $("#setup").dataset.kind = m.kind; $("#modelhint").textContent = m.hint + (m.price ? " · fal rates as of Aug 2026" : ""); }
function fillModels(){
  const extra = Object.values(S.models).some(v => !v.recommended) || Object.values(S.video.models).some(v => !v.recommended);
  for (const el of document.querySelectorAll(".showall")) el.hidden = !extra;
  const all = $("#showall").checked;
  const cur = $("#model").value || S.config.model; fill($("#model"), modelOpts(S.models, all || !(S.models[cur] || {}).recommended), cur); if (!$("#model").value) $("#model").selectedIndex = 0;
  const vcur = $("#vmodel").value || S.config.video_model; fill($("#vmodel"), modelOpts(S.video.models, all || !(S.video.models[vcur] || {}).recommended), vcur); if (!$("#vmodel").value) $("#vmodel").selectedIndex = 0;
  syncModel(); syncVideoModel();
}
function syncVideoModel(){
  const m = S.video.models[$("#vmodel").value]; if (!m) return;
  const panel = $("#vmakepanel"); panel.dataset.nores = m.res ? "0" : "1";
  if (m.res) { const cur = $("#vres").value; fill($("#vres"), m.res, m.res[cur] ? cur : Object.keys(m.res)[0]); }
  const minD = m.min_duration || 1, cur = $("#vdur").value;
  fill($("#vdur"), Object.fromEntries(Object.entries(S.video.durations).filter(([k]) => Number(k) >= minD)), Number(cur) >= minD ? cur : String(minD));
  $("#vmodelhint").textContent = m.hint || "";
}
function estimate(count){
  const m = S.models[$("#model").value], n = Number($("#variations").value);
  if (!m.price) return `${count * n} generation${count*n===1?"":"s"} · token priced`;
  const cost = m.price * (m.mult[$("#resolution").value] || 1) * n * count;
  return `${count * n} generation${count*n===1?"":"s"} · about $${cost.toFixed(2)}`;
}
function fill(sel, opts, val){ sel.innerHTML = Object.entries(opts).map(([k,v]) => `<option value="${k}"${k===val?" selected":""}>${v}</option>`).join(""); }

async function boot(){
  S = await api("/api/state");
  fill($("#quality"), S.quality_options, S.config.quality);
  fill($("#size"), S.size_options, S.config.long_edge);
  fill($("#resolution"), S.res_options, S.config.resolution);
  fill($("#variations"), S.variation_options, S.config.variations);
  fill($("#angles"), S.angle_options, S.config.angles || "6");
  fill($("#vres"), S.video.res, S.config.video_res); fill($("#vdur"), S.video.durations, S.config.video_duration); fill($("#tdur"), S.video.take_durations, S.config.take_duration);
  $("#vaudio").value = S.config.video_audio === false ? "0" : "1"; $("#crossfade").value = S.config.crossfade || "0.6"; $("#mnotes").value = S.config.motion_notes || ""; $("#shots").value = S.config.shots || "1"; $("#energy").value = S.config.energy || "calm";
  try { frames = JSON.parse(S.config.video_frames || "[]"); } catch { frames = []; }
  $("#showall").checked = $("#vshowall").checked = !!S.config.show_all_models;
  $("#model").value = S.config.model; $("#vmodel").value = S.config.video_model || "h3max";
  fillModels(); $("#vres").value = S.config.video_res; syncVideoModel();
  for (const id of ["showall","vshowall"]) $("#"+id).addEventListener("change", e => { $("#showall").checked = $("#vshowall").checked = e.target.checked; fillModels(); saveConfig(); renderVideo(); });
  $("#vmodel").addEventListener("change", () => { syncVideoModel(); saveConfig(); renderVideo(); });
  for (const id of ["vres","vdur","tdur","vaudio","crossfade","shots","energy","takechar"]) $("#"+id).addEventListener("change", () => { saveConfig(); renderVideo(); });
  $("#takechar").checked = !!S.config.take_character;
  for (const b of document.querySelectorAll("[data-view]")) b.addEventListener("click", () => setView(b.dataset.view));
  document.body.dataset.view = "images"; imgmode = S.config.img_mode || "detail"; document.body.dataset.imgmode = imgmode;
  for (const b of document.querySelectorAll("[data-imgmode]")) { b.setAttribute("aria-pressed", b.dataset.imgmode === imgmode); b.addEventListener("click", () => { imgmode = b.dataset.imgmode; document.body.dataset.imgmode = imgmode; for (const o of document.querySelectorAll("[data-imgmode]")) o.setAttribute("aria-pressed", o === b); api("/api/config", {img_mode: imgmode}); render(); }); }
  $("#mnotes").addEventListener("input", () => saveConfig());
  for (const b of document.querySelectorAll("[data-vmode]")) b.addEventListener("click", () => { vmode = b.dataset.vmode; for (const o of document.querySelectorAll("[data-vmode]")) o.setAttribute("aria-pressed", o === b); renderVideo(); });
  $("#vprompts").addEventListener("click", () => videoPrompts());
  $("#vclear").addEventListener("click", async () => { await api("/api/video/clear_drafts", {}); poll(); });
  $("#vexport").addEventListener("click", async () => { const b = $("#vexport"); const r = await api("/api/video/export", {}); b.textContent = r.error ? "Failed" : `Saved ${r.count} to video folder`; setTimeout(() => b.textContent = "Export prompts", 2200); });
  $("#vmake").addEventListener("click", () => videoMake());
  $("#stitch").addEventListener("click", () => stitch());
  $("#openvideo").addEventListener("click", () => api("/api/open", {which: "video"}));
  $("#openmusic").addEventListener("click", () => api("/api/open", {which: "root"}));
  S.clips = S.clips || [];
  $("#notes").value = S.config.style_notes || "";
  $("#review").value = S.config.review_first === false ? "0" : "1";
  $("#ver").textContent = "v" + S.version;
  $("#folderhint").innerHTML = `<b>${S.items.length}</b> render${S.items.length===1?"":"s"} in <b>${esc(S.folder)}</b>${S.demo ? " · demo mode, nothing is sent to fal" : ""}`;
  S.recent = S.recent || []; S.catalog = S.catalog || {}; S.spend = S.spend || 0;
  for (const id of ["quality","size","resolution","variations","review"]) $("#"+id).addEventListener("change", () => saveConfig());
  $("#angles").addEventListener("change", () => { saveConfig(); for (const a of Object.values(cards)) a.dataset.sig = ""; render(); });
  $("#model").addEventListener("change", () => { syncModel(); saveConfig(); });
  $("#openfolder").addEventListener("click", () => api("/api/open", {which: "enhanced"}));
  $("#switchfolder").addEventListener("click", openFolderModal);
  document.body.classList.toggle("more", !!S.config.more_open); $("#moretoggle").textContent = S.config.more_open ? "Less" : "More";
  $("#moretoggle").addEventListener("click", () => { const on = !document.body.classList.contains("more"); document.body.classList.toggle("more", on); $("#moretoggle").textContent = on ? "Less" : "More"; api("/api/config", {more_open: on}); });
  $("#spendalert").value = S.spend_alert || 10; $("#spendalert").addEventListener("change", () => { api("/api/config", {spend_alert: Number($("#spendalert").value) || 10}); S.spend_alert = Number($("#spendalert").value) || 10; render(); });
  $("#catalogbtn").addEventListener("click", () => { $("#catalogurl").value = (S.catalog && S.catalog.url) || ""; $("#catalogstatus").innerHTML = catalogLine(); $("#catalogmodal").hidden = false; });
  $("#catalogcancel").addEventListener("click", () => $("#catalogmodal").hidden = true);
  $("#catalogsave").addEventListener("click", async () => { await api("/api/config", {catalog_url: $("#catalogurl").value}); setTimeout(() => location.reload(), 600); });
  $("#charon").checked = !!S.config.character_on; $("#charnote").value = S.config.character_note || ""; $("#chardesc").value = S.character.desc || "";
  $("#charon").addEventListener("change", () => { saveConfig(); renderChar(); });
  $("#charnote").addEventListener("input", () => saveConfig());
  $("#chargen").addEventListener("click", async () => { const b = $("#chargen"); b.disabled = true; b.textContent = "Generating"; const r = await api("/api/character/generate", {description: $("#chardesc").value}); b.disabled = false; b.textContent = "Generate"; if (r.need_key) { openKey(false); return; } if (r.error) { toast(r.error); return; } await poll(); $("#charon").checked = true; renderChar(); });
  $("#charupload").addEventListener("click", () => $("#charfile").click());
  $("#charfile").addEventListener("change", () => { const f = $("#charfile").files[0]; if (!f) return; const rd = new FileReader(); rd.onload = async () => { const r = await api("/api/character/upload", {data: rd.result}); if (r.error) { toast(r.error); return; } await poll(); $("#charon").checked = true; renderChar(); }; rd.readAsDataURL(f); $("#charfile").value = ""; });
  $("#charclear").addEventListener("click", async () => { if (!await ask("Remove the character from this project?", "Remove character", "Remove")) return; await api("/api/character/clear", {}); await poll(); $("#charon").checked = false; renderChar(); });
  renderChar();
  $("#foldercancel").addEventListener("click", () => $("#foldermodal").hidden = true);
  $("#folderbrowse").addEventListener("click", async () => { const r = await api("/api/folder", {browse: true}); if (r.error) { toast(r.error); return; } $("#foldermodal").hidden = true; waitForFolder(); });
  $("#rescan").addEventListener("click", async () => {
    const b = $("#rescan"), label = b.lastChild; label.textContent = "Scanning";
    const r = await api("/api/rescan", {}); await poll();
    label.textContent = r.pending ? `${r.pending} new` : "Nothing new"; setTimeout(() => label.textContent = "Rescan", 1800);
    $("#folderhint").innerHTML = `<b>${S.items.length}</b> render${S.items.length===1?"":"s"} in <b>${esc(S.folder)}</b>${S.demo ? " · demo mode, nothing is sent to fal" : ""}`;
    if (r.pending && S.has_key && $("#review").value !== "1") runAll(false);
  });
  $("#notes").addEventListener("input", () => { saveConfig(); render(); });
  $("#run").addEventListener("click", () => runAll(false));
  $("#newbatch").addEventListener("click", async () => { if (await ask("Write a fresh prompt for every image? Nothing is enhanced until you press Enhance.", "New batch", "Write prompts")) runAll(true); });
  $("#keybtn").addEventListener("click", () => openKey(true));
  $("#exportimg").addEventListener("click", async () => { const b = $("#exportimg"); const r = await api("/api/export_images", {}); b.textContent = r.error ? "Failed" : `Saved ${r.count} to enhanced`; setTimeout(() => b.textContent = "Export prompts", 2200); });
  $("#keysave").addEventListener("click", saveKey);
  $("#keycancel").addEventListener("click", () => $("#keymodal").hidden = true);
  $("#stop").addEventListener("click", async () => { await api("/api/cancel", {}); poll(); });
  $("#quit").addEventListener("click", async () => { if (S.active) { if (!await ask("Jobs are still running. Quit anyway?", "Quit", "Quit")) return; } await api("/api/quit", {}); document.body.innerHTML = '<div class="empty"><span class="label">Render Post stopped</span><span>You can close this tab.</span></div>'; });
  $("#keyinput").addEventListener("keydown", e => { if (e.key === "Enter") saveKey(); });
  if (!S.has_key) openKey(false);
  else if (S.items.some(i => i.status === "pending") && S.config.review_first === false) runAll(false);
  render(); setInterval(poll, 1500);
}
function catalogLine(){ const c = S.catalog || {}; if (!c.url) return "No catalog set. Built-in models only."; if (c.ok === true) return `<i class="dot ok"></i> ${c.note}`; if (c.ok === false) return `<i class="dot bad"></i> couldn't load: ${esc(c.note)}`; return "Loading…"; }
function renderChar(){
  const has = !!(S.character && S.character.file);
  $("#charthumb").innerHTML = has ? `<img src="/img/out/${S.character.file}" alt="character">` : `<span class="label">No character</span>`;
  $("#charclear").hidden = !has; $("#charon").disabled = !has; if (!has) $("#charon").checked = false;
  $("#charblock").classList.toggle("on", has && $("#charon").checked);
  const tc = $("#takechar"); if (tc) { tc.disabled = !has; if (!has) tc.checked = false; }
}
function openFolderModal(){
  const list = $("#recentlist"); list.innerHTML = (S.recent && S.recent.length) ? S.recent.map(r => `<button type="button" data-path="${esc(r)}" title="${esc(r)}">${esc(r)}</button>`).join("") : `<span class="none">No other projects yet. Browse to a folder of renders.</span>`;
  for (const b of list.querySelectorAll("button[data-path]")) b.addEventListener("click", async () => { const r = await api("/api/folder", {path: b.dataset.path}); if (r.error) { toast(r.error); return; } $("#foldermodal").hidden = true; reloadProject(); });
  $("#foldermodal").hidden = false;
}
async function waitForFolder(){
  // the picker runs on the desktop; poll until the folder changes or the user cancels (~2 min)
  const before = S.folder; const t0 = Date.now();
  while (Date.now() - t0 < 120000) { await new Promise(r => setTimeout(r, 800)); const st = await api("/api/state"); if (st.folder !== before) { reloadProject(); return; } }
}
function reloadProject(){ location.reload(); }
function openKey(cancelable){ $("#keycancel").hidden = !cancelable; $("#keyinput").value = ""; $("#keyerr").hidden = true; $("#keymodal").hidden = false; setTimeout(() => $("#keyinput").focus(), 50); }
async function saveKey(){
  const k = $("#keyinput").value.trim(); if (!k) return;
  const btn = $("#keysave"); btn.disabled = true; btn.textContent = "Checking"; $("#keyerr").hidden = true;
  const r = await api("/api/config", {fal_key:k});
  btn.disabled = false; btn.textContent = "Save key";
  if (r.error) { $("#keyerr").textContent = r.error; $("#keyerr").hidden = false; return; }
  $("#keymodal").hidden = true; S.has_key = true;
  if (S.items.some(i => i.status === "pending") && $("#review").value !== "1") runAll(false);
}
async function reviseAll(){ await saveNow(); const r = await api("/api/revise", {}); if (r.need_key) { openKey(false); $("#keyerr").textContent = r.error; $("#keyerr").hidden = false; return; } if (r.error) toast(r.error); poll(); }
async function enhanceAll(names){
  await saveNow();
  const prompts = {}; for (const [n, el] of Object.entries(cards)) { const ta = el.querySelector("textarea"); if (ta) prompts[n] = ta.value; }
  const r = await api("/api/enhance_all", {prompts, names: names || null, revise_stale: $("#review").value !== "1"});
  if (r.need_key) { openKey(false); $("#keyerr").textContent = r.error; $("#keyerr").hidden = false; return; }
  if (r.error) toast(r.error); poll();
}
async function runAll(all){ const r = await api("/api/run", {all: !!all}); if (r.need_key) { openKey(false); $("#keyerr").textContent = r.error; $("#keyerr").hidden = false; return; } if (r.error) toast(r.error); poll(); }
async function regen(name, rewrite){
  const ta = cards[name].querySelector("textarea");
  const r = await api("/api/regenerate", rewrite ? {name, rewrite:true} : {name, prompt: ta.value});
  if (r.need_key) { openKey(false); $("#keyerr").textContent = r.error; $("#keyerr").hidden = false; return; }
  if (r.error) toast(r.error); poll();
}
let lastCount = null;
async function poll(){ const s = await api("/api/state"); if (lastCount !== null && s.items.length > lastCount) toast(`${s.items.length - lastCount} new render${s.items.length - lastCount === 1 ? "" : "s"} found in the folder`, "ok", 4000); lastCount = s.items.length; S.items = s.items; S.active = s.active; S.picks = s.picks; S.clips = s.clips || []; S.video = s.video || S.video; S.recent = s.recent || []; S.character = s.character || {}; S.catalog = s.catalog || S.catalog; S.spend = s.spend; S.spend_alert = s.spend_alert;
  if (s.latest && s.latest.version) { const u = $("#update"); u.textContent = `v${s.latest.version} available`; u.href = s.latest.url || "#"; u.hidden = false; }
  render(); }

function stateLine(it){
  if (it.status === "working" || it.status === "queued") return `<i class="dot live"></i>${it.step}`;
  if (it.status === "failed") return `<i class="dot bad"></i>failed`;
  if (it.status === "done") { const v = it.versions[it.versions.length-1]; return `<i class="dot ok"></i>${it.versions.length} version${it.versions.length===1?"":"s"}${v && v.seconds != null ? " · last " + v.seconds + "s" : ""}`; }
  if (it.status === "ready") return `<i class="dot warn"></i>prompt ready · not sent`;
  return `<i class="dot"></i>waiting`;
}

function render(){
  const items = S.items, busy = items.filter(i => i.status === "working" || i.status === "queued").length;
  const done = items.filter(i => i.status === "done").length, failed = items.filter(i => i.status === "failed").length;
  const mdl = S.models[S.config.model] || {}; const setting = mdl.kind === "nano" ? S.config.resolution : `${S.config.quality} · ${S.config.long_edge}px`;
  $("#meta").innerHTML = [`<b>${items.length}</b> images`, "<s>·</s>", `<b>${done}</b> done`, failed ? `<s>·</s> <b>${failed}</b> failed` : "", S.picks ? `<s>·</s> <b>${S.picks}</b> picked` : "", "<s>·</s>", `${(mdl.label || "").split(" ·")[0]} · ${setting}`].join(" ");
  $("#status").innerHTML = busy ? `<i class="dot live"></i>${busy} in progress` : `<i class="dot ok"></i>idle`;
  const sp = Number(S.spend || 0), lim = Number(S.spend_alert || 10); $("#spend").innerHTML = sp > 0 ? `<i class="dot ${sp >= lim ? "warn" : ""}"></i>≈ $${sp.toFixed(2)} this project` : "";
  $("#stop").hidden = busy === 0;
  const pending = items.filter(i => i.status === "pending").length;
  const ready = items.filter(i => i.status === "ready").length;
  const anyPrompt = items.filter(i => i.prompt && i.status !== "pending").length;
  const reviewMode = $("#review").value === "1";
  const notesNow = $("#notes").value.trim();
  const stale = items.filter(i => i.prompt && ["ready","failed","done"].includes(i.status) && (i.notes_used || "") !== notesNow).length;
  $("#stale").hidden = stale === 0; $("#stale").innerHTML = `<i class="dot warn"></i>${stale} prompt${stale===1?"":"s"} written with old notes`;
  $("#run").hidden = !reviewMode || pending === 0; $("#run").disabled = busy > 0;
  $("#exportimg").hidden = !items.some(i => i.prompt || i.versions.length);
  $("#run").textContent = `Write ${pending} prompt${pending===1?"":"s"}`;
  $("#run").classList.toggle("solid", reviewMode && pending > 0 && anyPrompt === 0);
  $("#enhance").hidden = reviewMode && pending > 0 && anyPrompt === 0;
  $("#newbatch").hidden = pending > 0 || !items.length; $("#newbatch").disabled = busy > 0;
  $("#enhance").disabled = busy > 0 || (anyPrompt === 0 && !(pending && !reviewMode));
  const toSend = selected.size ? [...selected].filter(nm => items.some(i => i.name === nm && i.prompt)).length : (ready || anyPrompt || pending); $("#estimate").textContent = toSend ? estimate(toSend) : "";
  if (pending && !reviewMode) { $("#enhance").textContent = `Enhance ${pending} image${pending===1?"":"s"}`; $("#enhance").onclick = () => runAll(false); }
  else if (reviewMode && stale) { $("#enhance").textContent = `Update ${stale} prompt${stale===1?"":"s"}`; $("#enhance").onclick = reviseAll; }
  else if (selected.size) { const n = [...selected].filter(nm => items.some(i => i.name === nm && ["ready","failed","done"].includes(i.status) && i.prompt)).length; $("#enhance").textContent = `Enhance ${n} selected`; $("#enhance").disabled = busy > 0 || n === 0; $("#enhance").onclick = () => enhanceAll([...selected]); }
  else { $("#enhance").textContent = ready ? `Enhance ${ready} reviewed` : (stale ? "Update prompts and enhance" : "Enhance all again"); $("#enhance").onclick = () => enhanceAll(null); }
  $("#selinfo").hidden = selected.size === 0; $("#selinfo").innerHTML = `<i class="dot warn"></i>${selected.size} selected · <a href="#" id="selclear">clear</a>`; const sc = $("#selclear"); if (sc) sc.onclick = e => { e.preventDefault(); selected.clear(); for (const a of Object.values(cards)) a.dataset.sig = ""; render(); };

  renderVideo();
  const npick = items.reduce((n, i) => n + i.versions.filter(v => v.pick).length, 0);
  $("#pickstab").textContent = npick ? `Picks · ${npick}` : "Picks";
  $("#pickbar").innerHTML = npick ? `<b>${npick}</b> picked version${npick===1?"":"s"}, also copied to enhanced/picks. Click a thumbnail to jump to its card; unpick from the card to remove it.` : `Nothing picked yet. Press the star on a version to pick it.`;
  const gg = $("#imggrid"); gg.hidden = !(view === "images" && imgmode === "grid");
  if (!gg.hidden) { gg.innerHTML = ""; for (const it of items) { const v = it.versions[it.versions.length - 1]; const el = document.createElement("div"); el.className = "gi" + (selected.has(it.name) ? " sel" : "");
      const st = it.status === "working" || it.status === "queued" ? `<i class="dot live st"></i>` : it.status === "failed" ? `<i class="dot bad st"></i>` : it.status === "ready" ? `<i class="dot warn st"></i>` : "";
      el.innerHTML = `${st}<img src="${v ? `/img/out/${encodeURIComponent(v.file)}` : `/img/raw/${encodeURIComponent(it.source_file)}`}" loading="lazy" alt=""><div class="cap"><b>${esc(it.name)}</b><span>${it.versions.some(x => x.pick) ? "★ " : ""}${it.versions.length ? it.versions.length + " v" : (it.prompt ? "prompt ready" : "raw")}</span></div>`;
      el.addEventListener("click", e => { if (e.shiftKey) { selected.has(it.name) ? selected.delete(it.name) : selected.add(it.name); for (const a of Object.values(cards)) a.dataset.sig = ""; render(); return; }
        imgmode = "detail"; document.body.dataset.imgmode = "detail"; for (const o of document.querySelectorAll("[data-imgmode]")) o.setAttribute("aria-pressed", o.dataset.imgmode === "detail"); api("/api/config", {img_mode: "detail"}); render(); const art = cards[it.name]; if (art) art.scrollIntoView({behavior:"smooth", block:"start"}); });
      gg.appendChild(el); } $("#gridhint").textContent = "Grid shows the latest version of each image. Click to open, shift-click to select."; }
  if (view === "picks") { const g = $("#pickgrid"); g.innerHTML = ""; for (const it of items) it.versions.forEach((v, i) => { if (!v.pick) return; const el = document.createElement("div"); el.className = "pg"; el.innerHTML = `<img src="/img/out/${encodeURIComponent(v.file)}" loading="lazy" alt=""><span>${esc(it.name)} · ${v.angle ? "a" : "v"}${it.versions.slice(0, i+1).filter(y => !!y.angle === !!v.angle).length}</span>`; el.addEventListener("click", () => { const art = cards[it.name]; if (art) { art.dataset.sel = i; art.dataset.sig = ""; render(); art.scrollIntoView({behavior:"smooth", block:"start"}); } }); g.appendChild(el); }); }
  const wrap = $("#cards");
  if (!items.length) { wrap.innerHTML = `<div class="empty"><span class="label">No renders found</span><span>Put PNG or JPG renders in this folder and restart.</span></div>`; return; }
  wrap.style.display = "grid"; wrap.style.gap = "16px";
  items.forEach((it, i) => {
    let art = cards[it.name];
    if (!art) { art = document.createElement("article"); art.tabIndex = -1; art.style.animationDelay = `${Math.min(i,8)*30}ms`; cards[it.name] = art; wrap.appendChild(art); art.dataset.sig = ""; }
    art.classList.toggle("haspick", it.versions.some(v => v.pick)); art.classList.toggle("sel", selected.has(it.name));
    const sig = JSON.stringify([it.status, it.step, it.versions.map(v => v.file + (v.pick ? "*" : "")), it.error, it.prompt, it.notes_used, selected.has(it.name)]);
    if (art.dataset.sig === sig) return;           // only rebuild when something changed
    const ta0 = art.querySelector("textarea");
    const editing = ta0 && document.activeElement === ta0;
    // "shown" is whatever the box was last filled with (a version's prompt or the next-run draft);
    // only a difference from that counts as the user's edit, and edits belong to the next-run draft
    const edited = ta0 && ta0.value !== (art.dataset.shown || "");
    const prevCount = Number(art.dataset.count || 0);
    let sel = Number(art.dataset.sel ?? -1);
    if (it.versions.length !== prevCount || sel < 0 || sel >= it.versions.length) sel = it.versions.length - 1;  // new version: jump to it
    const wasLatest = art.dataset.wasLatest === "1";
    if (edited && wasLatest) art.dataset.draft = ta0.value;           // remember the edit while browsing older versions
    if (it.prompt !== (art.dataset.prompt || "")) delete art.dataset.draft;   // server changed the draft (rewrite, run): drop the stale local edit
    const isLatest = sel === it.versions.length - 1;
    const draft = isLatest && art.dataset.draft != null ? art.dataset.draft : null;
    art.dataset.sig = sig; art.dataset.prompt = it.prompt || ""; art.dataset.count = it.versions.length; art.dataset.sel = sel; art.dataset.wasLatest = isLatest ? "1" : "0";
    const v = it.versions[sel];
    const ar = it.src_size ? `${it.src_size[0]}/${it.src_size[1]}` : "16/9";
    const busyItem = it.status === "working" || it.status === "queued";
    const vlabel = (x, i) => x.angle ? "a" + (it.versions.slice(0, i+1).filter(y => y.angle).length) : "v" + (it.versions.slice(0, i+1).filter(y => !y.angle).length);
    const tabs = it.versions.length > 1 ? `<div class="vseg" role="group" aria-label="Version">${it.versions.map((x,i) => `<button type="button" data-i="${i}" aria-pressed="${i===sel}" title="${esc((x.angle ? "angle · " : "") + (x.character ? "with character · " : "") + (x.made || "") + (x.model ? " · " + x.model : ""))}">${vlabel(x, i)}${x.character ? "·" : ""}${x.pick ? "★" : ""}</button>`).join("")}</div>` : "";
    art.innerHTML = `
      <div class="stage ${v ? "" : "noafter"}" data-mode="${v ? (v.angle ? "after" : mode) : "before"}" style="--ar:${ar}">
        <img class="before" src="/img/raw/${encodeURIComponent(it.source_file)}" alt="" loading="lazy">
        ${v ? `<img class="after" src="/img/out/${encodeURIComponent(v.file)}" alt="" loading="lazy">` : ""}
        <div class="wipe"><input type="range" min="0" max="100" value="50" aria-label="Wipe"><div class="handle"></div></div>
        <span class="tag l label">Raw</span><span class="tag r label">${v ? vlabel(v, sel) : "Enhanced"}</span>
        ${busyItem ? `<div class="working"><span><i class="dot live"></i>${it.step}<button class="btn quiet cancel" type="button">Cancel</button></span></div>` : ""}
      </div>
      <aside>
        <div class="row"><h2><label class="selbox" title="Select for Enhance selected"><input type="checkbox" class="selimg" ${selected.has(it.name) ? "checked" : ""}></label>${esc(it.name)}</h2>${tabs}</div>
        <div class="facts">
          <span>raw</span><b>${it.src_size ? it.src_size.join(" × ") : "–"}</b>
          <span>out</span><b>${v && v.out_size ? v.out_size.join(" × ") + (v.model ? " · " + ((S.models[v.model]||{}).label||v.model).split(" ·")[0] : "") + (v.quality ? " · " + v.quality : "") : "–"}</b>
          <span>run</span><b>${stateLine(it)}</b>
        </div>
        ${it.error ? `<div class="err">${esc(it.error)}</div>` : ""}
        <div class="row"><span class="label">${v && sel < it.versions.length-1 ? "Prompt · " + vlabel(v, sel) : "Prompt · next"}</span>
          <span><button class="btn quiet rewrite" type="button" title="Ask for a fresh prompt using the current style notes">Rewrite</button><button class="btn quiet copy" type="button">Copy</button></span></div>
        <textarea spellcheck="false" placeholder="Prompt appears here once written. Edit it, then Enhance.">${esc(draft ?? (v && !isLatest ? v.prompt : it.prompt))}</textarea>
        <div class="actions">
          ${v ? `<button class="btn quiet compare" type="button" title="Save a side-by-side JPG to enhanced/compare">Before / after</button>
          <button class="btn quiet delver" type="button" title="Move this version to enhanced/trash">Delete</button>
          <button class="btn quiet pick ${v.pick ? "on" : ""}" type="button" title="${v.pick ? "Picked: this version is in enhanced/picks and eligible for video" : "Mark this version as a pick: copies it to enhanced/picks"}"><svg viewBox="0 0 16 16"><path d="M8 1.8l1.9 3.9 4.3.6-3.1 3 .7 4.3L8 11.6l-3.8 2 .7-4.3-3.1-3 4.3-.6z"/></svg>${v.pick ? "Picked" : "Pick"}</button>` : ""}
          <button class="btn regen ${it.status === "ready" ? "solid" : ""}" type="button" ${busyItem ? "disabled" : ""}>${it.versions.length ? "Enhance again" : "Enhance this one"}</button>
          ${v && it.status === "done" ? `<button class="btn angles" type="button" title="New stills of this space from other camera positions, with the current image model. Best from a wide, well-lit view that shows the whole space; partial or steep views invent more. Count is set under Angles per run.">${$("#angles").value} angles</button>
          <button class="btn solid tovideo" type="button" title="Add this version to the video set and open Video">Add to video</button>` : ""}</div>
      </aside>`;
    for (const b of art.querySelectorAll(".vseg button")) b.addEventListener("click", () => { art.dataset.sel = b.dataset.i; art.dataset.sig = ""; render(); });
    $(".rewrite", art).addEventListener("click", () => regen(it.name, true));
    const pk = $(".pick", art); if (pk) pk.addEventListener("click", async () => { await api("/api/pick", {name: it.name, file: v.file}); poll(); });
    const dv = $(".delver", art); if (dv) dv.addEventListener("click", async () => { if (!await ask(`Delete ${it.name} ${vlabel(v, sel)}? It moves to enhanced/trash, not the bin.`, "Delete version", "Delete")) return; const r = await api("/api/delete_version", {name: it.name, file: v.file}); if (r.error) { toast(r.error); return; } frames = frames.filter(f => !(f.name === it.name && f.file === v.file)); saveConfig(); art.dataset.sel = Math.max(0, sel - 1); art.dataset.sig = ""; poll(); });
    const ag = $(".angles", art); if (ag) ag.addEventListener("click", async () => {
      await saveNow();
      const n = Number($("#angles").value), m = S.models[$("#model").value];
      const cost = m.price ? ` · about $${(m.price * (m.mult[$("#resolution").value] || 1) * n).toFixed(2)}` : " · token priced";
      if (!await ask(`Make ${n} new angles of ${it.name} ${vlabel(v, sel)} with ${m.label.split(" ·")[0]}${cost}?`, "Angles", "Make angles")) return;
      const r = await api("/api/angles", {name: it.name, file: v.file}); if (r.need_key) { openKey(false); $("#keyerr").textContent = r.error; $("#keyerr").hidden = false; return; } if (r.error) toast(r.error); poll();
    });
    const tv = $(".tovideo", art); if (tv) tv.addEventListener("click", () => {
      const k = it.name + "|" + v.file; if (!frames.some(f => frameKey(f) === k)) { frames.push({name: it.name, file: v.file}); saveConfig(); }
      setView("video");
    });
    const cp = $(".compare", art); if (cp) cp.addEventListener("click", async () => { cp.textContent = "Saving"; const r = await api("/api/compare", {name: it.name, file: v.file}); cp.textContent = r.error ? "Failed" : "Saved to compare"; setTimeout(() => cp.textContent = "Before / after", 1800); });
    const c = $(".cancel", art); if (c) c.addEventListener("click", async () => { c.disabled = true; c.textContent = "Cancelling"; await api("/api/cancel", {name: it.name}); poll(); });
    const sb = $(".selimg", art); if (sb) sb.addEventListener("change", () => { sb.checked ? selected.add(it.name) : selected.delete(it.name); render(); });
    const ta = $("textarea", art); art.dataset.shown = ta.value; const fit = () => { ta.style.height = "auto"; ta.style.height = Math.max(150, ta.scrollHeight + 2) + "px"; };
    ta.addEventListener("input", () => { fit(); if (art.dataset.wasLatest === "1") art.dataset.draft = ta.value; }); requestAnimationFrame(fit);
    const stage = $(".stage", art), range = $("input[type=range]", art);
    range.addEventListener("input", () => stage.style.setProperty("--cut", range.value + "%"));
    $(".copy", art).addEventListener("click", async e => { try { await navigator.clipboard.writeText($("textarea", art).value); e.target.textContent = "Copied"; setTimeout(() => e.target.textContent = "Copy", 1400); } catch {} });
    $(".regen", art).addEventListener("click", () => regen(it.name, false));
    if (editing) $("textarea", art).focus();
  });
}

// ---------------- video
function setView(v){
  view = v; document.body.dataset.view = v;
  for (const b of document.querySelectorAll("[data-view]")) b.setAttribute("aria-pressed", b.dataset.view === v);
  $("#videoview").hidden = v !== "video";
  if (v === "picks") { for (const [name, art] of Object.entries(cards)) { const it = S.items.find(i => i.name === name); const i = it ? it.versions.findIndex(x => x.pick) : -1; if (i >= 0) { art.dataset.sel = i; art.dataset.sig = ""; } } render(); }
  if (v === "video") renderVideo();
  window.scrollTo({top:0, behavior:"smooth"});
}
function frameKey(f){ return f.name + "|" + f.file; }
function frameLabel(f){ const it = S.items.find(i => i.name === f.name); if (!it) return f.name; if (f.file === it.source_file) return `${f.name} · raw`; const i = it.versions.findIndex(v => v.file === f.file); if (i < 0) return f.name; const x = it.versions[i]; const k = it.versions.slice(0, i+1).filter(y => !!y.angle === !!x.angle).length; return `${f.name} · ${x.angle ? "a" : "v"}${k}`; }
function frameSrc(f){ const it = S.items.find(i => i.name === f.name); return (it && f.file === it.source_file) ? `/img/raw/${encodeURIComponent(f.file)}` : `/img/out/${encodeURIComponent(f.file)}`; }
function toggleFrame(f){ const k = frameKey(f); const i = frames.findIndex(x => frameKey(x) === k); if (i >= 0) frames.splice(i,1); else frames.push({name: f.name, file: f.file}); saveConfig(); renderVideo(); }
function moveFrame(k, d){ const i = frames.findIndex(x => frameKey(x) === k); const j = i + d; if (i < 0 || j < 0 || j >= frames.length) return; const [f] = frames.splice(i,1); frames.splice(j,0,f); saveConfig(); renderVideo(); }
function vprice(){
  if (vmode === "take") return S.video.models.seedance.price[$("#vres").value] || 0;
  const m = S.video.models[$("#vmodel").value]; if (!m) return 0;
  return m.price[$("#vres").value] ?? m.price[$("#vaudio").value === "1" ? "audio" : "silent"] ?? Object.values(m.price)[0] ?? 0;
}
function vestimate(){
  const price = vprice(), n = frames.length;
  if (!n) return "";
  if (vmode === "take") { const d = Number($("#tdur").value); return `1 take · ${n} frames · ${d}s · about $${(price*d).toFixed(2)}`; }
  const d = Number($("#vdur").value); return `${n} clip${n===1?"":"s"} · ${d}s each · about $${(price*d*n).toFixed(2)}`;
}
function renderVideo(){
  if (!S || !S.video) return;
  const valid = new Set(); for (const it of S.items) { valid.add(it.name + "|" + it.source_file); for (const v of it.versions) valid.add(it.name + "|" + v.file); }
  frames = frames.filter(f => valid.has(frameKey(f)));
  const done = S.items.filter(i => i.versions.length).length;
  $("#videotab").textContent = frames.length ? `Video · ${frames.length}` : "Video";
  if (view !== "video") return;
  $("#vmakepanel").dataset.vmode = vmode; $("#vmakepanel").dataset.vmodel = $("#vmodel").value;
  if (vmode === "take") { $("#vmakepanel").dataset.nores = "0"; if (!S.video.res[$("#vres").value]) fill($("#vres"), S.video.res, "480p"); }
  else syncVideoModel();
  const n = frames.length, sh = Number($("#shots").value);
  $("#vexplain").textContent = !n ? "Add frames in Step 1 first."
    : vmode === "take" ? `You'll get 1 video, ${$("#tdur").value}s long, that travels through all ${n} frame${n===1?"":"s"} in the order shown. Experimental: the model recreates the spaces rather than reproducing them.`
    : sh === 1 ? `You'll get ${n} separate video${n===1?"":"s"}, ${$("#vdur").value}s each. Each one starts exactly on its frame and holds one slow camera move.`
    : `You'll get ${n} separate video${n===1?"":"s"}, ${$("#vdur").value}s each. Each starts exactly on its frame, then cuts to ${sh-1} more angle${sh===2?"":"s"} of the same space, like a mini edit.`;
  // ---- step 1: frames grid, versions stacked per image
  const grid = $("#framegrid"); grid.innerHTML = "";
  for (const it of S.items) {
    const fr = document.createElement("div"); fr.className = "frame";
    let nv = 0, na = 0; const vers = it.versions.map(v => ({file: v.file, label: v.angle ? `a${++na}` : `v${++nv}`, pick: v.pick, raw: false}));
    vers.push({file: it.source_file, label: "raw", pick: false, raw: true});
    fr.innerHTML = `<div class="name">${esc(it.name)}<span>${it.versions.length} version${it.versions.length===1?"":"s"}</span></div><div class="stack"></div>`;
    const st = $(".stack", fr);
    for (const v of vers) {
      const k = it.name + "|" + v.file, ord = frames.findIndex(f => frameKey(f) === k);
      const el = document.createElement("div"); el.className = "ver" + (ord >= 0 ? " on" : "") + (v.raw ? " raw" : ""); el.title = ord >= 0 ? "Remove from video set" : "Add to video set";
      el.innerHTML = `<img src="${v.raw ? `/img/raw/${encodeURIComponent(v.file)}` : `/img/out/${encodeURIComponent(v.file)}`}" alt="" loading="lazy"><span class="tag">${v.label}</span>${v.pick ? `<span class="star">★</span>` : ""}${ord >= 0 ? `<span class="ord">${ord+1}</span>` : ""}`;
      el.addEventListener("click", () => toggleFrame({name: it.name, file: v.file}));
      st.appendChild(el);
    }
    grid.appendChild(fr);
  }
  if (!S.items.length) grid.innerHTML = `<span class="hint">No renders in this folder.</span>`;
  $("#framecount").innerHTML = frames.length ? `<i class="dot ok"></i>${frames.length} in the set` : `<i class="dot"></i>nothing selected`;
  // ---- step 2: set strip + controls
  const strip = $("#pickstrip"); strip.innerHTML = "";
  frames.forEach((f, i) => {
    const el = document.createElement("div"); el.className = "pk on";
    el.innerHTML = `${vmode === "take" ? `<span class="ord">${i+1}</span>` : ""}<img src="${frameSrc(f)}" alt=""><div class="cap"><b>${esc(frameLabel(f))}</b><span class="mv"><button type="button" title="Earlier">◀</button><button type="button" title="Later">▶</button></span></div>`;
    el.title = "Remove from set"; el.addEventListener("click", e => { if (e.target.tagName === "BUTTON") return; toggleFrame(f); });
    const [bl, br] = el.querySelectorAll(".mv button"); bl.addEventListener("click", () => moveFrame(frameKey(f), -1)); br.addEventListener("click", () => moveFrame(frameKey(f), 1));
    strip.appendChild(el);
  });
  if (!frames.length) strip.innerHTML = `<span class="hint" style="color:var(--em-ink-dim)">Empty. Add frames in Step 1.</span>`;
  $("#vestimate").textContent = vestimate();
  const clips = (S.clips || []).filter(c => c.kind !== "reel"), reels = (S.clips || []).filter(c => c.kind === "reel");
  const busy = (S.clips || []).filter(c => c.status === "queued" || c.status === "working").length;
  const ready = clips.filter(c => c.status === "ready" || c.status === "failed").length;
  const readyTake = clips.some(c => (c.status === "ready" || c.status === "failed") && c.kind === "take");
  const reviewMode = $("#review").value === "1";
  $("#vprompts").hidden = !reviewMode; $("#vprompts").disabled = busy > 0 || frames.length === 0;
  $("#vclear").hidden = ready === 0 || busy > 0;
  $("#vexport").hidden = !clips.some(c => c.prompt);
  $("#vprompts").textContent = vmode === "take" ? "Write take prompt" : `Write ${frames.length} motion prompt${frames.length===1?"":"s"}`;
  $("#vprompts").classList.toggle("solid", reviewMode && ready === 0 && frames.length > 0);
  if (reviewMode) { $("#vmake").hidden = ready === 0; $("#vmake").textContent = readyTake && ready === 1 ? "Make the take" : `Make ${ready} ${ready===1?"clip":"clips"}`; $("#vmake").disabled = busy > 0; }
  else { $("#vmake").hidden = false; $("#vmake").textContent = vmode === "take" ? "Make the take" : `Make ${frames.length} clip${frames.length===1?"":"s"}`; $("#vmake").disabled = busy > 0 || frames.length === 0; }
  renderClipCards(clips, $("#clips"), clipEls, true);
  // ---- step 3: reel
  renderClipCards(reels, $("#reels"), reelEls, false);
  updateStitch();
}
function renderClipCards(list, wrap, els, withStitchBox){
  const seen = new Set();
  for (const c of list) {
    seen.add(c.id); let el = els[c.id];
    if (!el) { el = document.createElement("div"); el.className = "clip"; els[c.id] = el; wrap.appendChild(el); el.dataset.sig = ""; }
    const sig = JSON.stringify([c.status, c.step, c.file, c.error, c.prompt, [...stitchSel].indexOf(c.id)]); if (el.dataset.sig === sig) continue;
    const ta0 = el.querySelector("textarea"); const draft = ta0 && ta0.value !== (el.dataset.prompt || "") ? ta0.value : null;
    el.dataset.sig = sig; el.dataset.prompt = c.prompt || "";
    const busyItem = c.status === "queued" || c.status === "working";
    const src = c.kind === "reel" ? null : c.sources[0];
    const title = c.kind === "reel" ? "Reel" : c.kind === "take" ? `Take · ${c.sources.length} frames` : (src ? esc(frameLabel(src)) : "Clip");
    const shots = (c.kind === "clip" && Number(c.shots || 1) > 1 ? ` · ${c.shots} shots` : "") + (c.vmodel && c.kind === "clip" ? " · " + (((S.video.models[c.vmodel] || {}).label || c.vmodel).split(" ·")[0]) : "");
    const dims = c.out_size ? ` · ${c.out_size[0]}×${c.out_size[1]}` : (c.resolution ? ` · ${c.resolution}` : "");
    const state = busyItem ? `<i class="dot live"></i>${esc(c.step)}` : c.status === "done" ? `<i class="dot ok"></i>${c.duration}s${dims}${shots}` : c.status === "failed" ? `<i class="dot bad"></i>failed` : `<i class="dot warn"></i>prompt ready · not sent`;
    el.innerHTML = `
      <div class="media">${c.file ? `<video src="/vid/${encodeURIComponent(c.file)}" ${src ? `poster="${frameSrc(src)}"` : ""} controls preload="metadata" loop muted></video>` : src ? `<img src="${frameSrc(src)}" alt="">` : ""}
        ${withStitchBox && c.status === "done" ? `<label class="inreel ${stitchSel.has(c.id) ? "on" : ""}" title="Include this clip in the reel. Order is the order you tick."><input type="checkbox" class="stitchsel" ${stitchSel.has(c.id) ? "checked" : ""}><span>${stitchSel.has(c.id) ? `<b class="ord">${[...stitchSel].indexOf(c.id) + 1}</b> In reel` : "Add to reel"}</span></label>` : ""}
        ${busyItem ? `<div class="working"><span><i class="dot live"></i>${esc(c.step)}<button class="btn quiet vcancel" type="button">Cancel</button></span></div>` : ""}</div>
      <div class="body">
        <div class="top"><label>${title}</label><span>${state}</span></div>
        ${c.error ? `<div class="err">${esc(c.error)}</div>` : ""}
        ${c.kind === "reel" ? `<div class="hint" style="font-family:var(--em-font-mono);font-size:11px;color:var(--em-ink-dim)">${esc(c.prompt)}</div>` : `<textarea spellcheck="false" placeholder="Motion prompt appears here once written.">${esc(draft ?? c.prompt)}</textarea>`}
        <div class="actions"><span class="r">${c.file ? `<a class="btn quiet" href="/vid/${encodeURIComponent(c.file)}" target="_blank" rel="noopener">Open</a><a class="btn quiet" href="/vid/${encodeURIComponent(c.file)}" download="${esc(c.file)}">Download</a>` : ""}${!busyItem ? `<button class="btn quiet vremove" type="button" title="Remove from this list (keeps the file)">Remove</button>` : ""}</span>
          <span class="r">${c.kind !== "reel" && !busyItem ? `<button class="btn vmake1 ${c.status === "ready" ? "solid" : ""}" type="button">${c.status === "done" ? "Make again" : "Make clip"}</button>` : ""}</span></div>
      </div>`;
    const ta = el.querySelector("textarea"); if (ta) { const fit = () => { ta.style.height = "auto"; ta.style.height = Math.max(64, ta.scrollHeight + 2) + "px"; }; ta.addEventListener("input", fit); requestAnimationFrame(fit); }
    const cb = el.querySelector(".stitchsel"); if (cb) cb.addEventListener("change", () => { cb.checked ? stitchSel.add(c.id) : stitchSel.delete(c.id); el.dataset.sig = ""; renderVideo(); });
    const vc = el.querySelector(".vcancel"); if (vc) vc.addEventListener("click", async () => { vc.disabled = true; await api("/api/video/cancel", {id: c.id}); poll(); });
    const rm = el.querySelector(".vremove"); if (rm) rm.addEventListener("click", async () => { await api("/api/video/remove", {id: c.id}); el.remove(); delete els[c.id]; stitchSel.delete(c.id); poll(); });
    const mk = el.querySelector(".vmake1"); if (mk) mk.addEventListener("click", async () => { await saveNow(); const r = await api("/api/video/make", {ids: [c.id], prompts: {[c.id]: el.querySelector("textarea").value}}); if (r.error) toast(r.error); poll(); });
  }
  for (const id of Object.keys(els)) if (!seen.has(id)) { els[id].remove(); delete els[id]; }
}
function updateStitch(){
  const done = (S.clips || []).filter(c => c.status === "done" && c.kind !== "reel");
  const m = $("#music"); if (!m.dataset.wired) { m.dataset.wired = "1"; m.addEventListener("change", updateStitch); } const cur = m.value; m.innerHTML = `<option value="">None</option>` + (S.video.music || []).map(f => `<option value="${esc(f)}">${esc(f)}</option>`).join(""); m.value = cur;
  $("#musichint").hidden = (S.video.music || []).length > 0;
  $("#mstartwrap").hidden = !m.value;
  const ok = S.video.ffmpeg && stitchSel.size >= 2;
  $("#stitch").disabled = !ok;
  $("#stitchhint").innerHTML = !S.video.ffmpeg ? `<i class="dot bad"></i>ffmpeg missing in this build` : done.length < 2 ? `<i class="dot"></i>needs two finished clips` : stitchSel.size < 2 ? `<i class="dot warn"></i>add ${2 - stitchSel.size} more clip${stitchSel.size === 1 ? "" : "s"} to the reel` : `<i class="dot ok"></i>${stitchSel.size} clips, in the order ticked`;
  $("#stitch").textContent = ok ? `Stitch ${stitchSel.size} clips` : "Stitch";
}
async function videoPrompts(){
  await saveNow();
  if (!frames.length) return;
  const r = await api("/api/video/prompts", {mode: vmode, picks: frames});
  if (r.need_key) { openKey(false); $("#keyerr").textContent = r.error; $("#keyerr").hidden = false; return; }
  if (r.error) toast(r.error); poll();
}
async function videoMake(){
  await saveNow();
  const reviewMode = $("#review").value === "1";
  if (!reviewMode) { const est = vestimate(); if (!await ask(`This will generate video now: ${est}.`, "Make video", "Generate")) return; return videoPrompts(); }
  const prompts = {}; for (const [id, el] of Object.entries(clipEls)) { const ta = el.querySelector("textarea"); if (ta) prompts[id] = ta.value; }
  const ids = (S.clips || []).filter(c => c.status === "ready" || c.status === "failed").map(c => c.id);
  const price = vprice(); const secs = ids.reduce((n, id) => n + Number((S.clips.find(c => c.id === id) || {}).duration || 0), 0);
  if (!await ask(`Generate ${ids.length} clip${ids.length===1?"":"s"}: ${secs}s of video, about $${(price*secs).toFixed(2)}.`, "Make clips", "Generate")) return;
  const r = await api("/api/video/make", {ids, prompts}); if (r.error) toast(r.error); poll();
}
function reelOrder(){ return [...stitchSel].filter(id => (S.clips || []).some(c => c.id === id && c.status === "done")); }   // tick order, as shown on the badges
async function stitch(){
  await saveNow();
  const order = reelOrder();
  const r = await api("/api/video/stitch", {ids: order, music: $("#music").value || null, music_start: Number($("#mstart").value || 0)}); if (r.error) toast(r.error); poll();
}

for (const b of document.querySelectorAll(".seg button[data-mode]")) b.addEventListener("click", () => {
  mode = b.dataset.mode;
  for (const o of document.querySelectorAll(".seg button")) o.setAttribute("aria-pressed", o === b);
  for (const s of document.querySelectorAll(".stage:not(.noafter)")) { const art = s.closest("article"); const it = art && S.items.find(i => i.name === Object.keys(cards).find(k => cards[k] === art)); const v = it && it.versions[Number(art.dataset.sel)]; s.dataset.mode = v && v.angle && mode === "wipe" ? "after" : mode; }
});
let cur = -1;
function jump(d){ const c = [...document.querySelectorAll("article")]; if (!c.length) return; cur = Math.max(0, Math.min(c.length-1, cur+d)); c[cur].scrollIntoView({behavior:"smooth",block:"start"}); c[cur].focus({preventScroll:true}); }
window.addEventListener("scroll", () => document.body.classList.toggle("scrolled", window.scrollY > 200), {passive:true});
["dragenter","dragover"].forEach(ev => window.addEventListener(ev, e => { if ([...e.dataTransfer.types].includes("Files")) { e.preventDefault(); document.body.classList.add("dropping"); } }));
["dragleave","drop"].forEach(ev => window.addEventListener(ev, e => { if (ev === "dragleave" && e.relatedTarget) return; document.body.classList.remove("dropping"); }));
window.addEventListener("drop", async e => {
  const files = [...(e.dataTransfer.files || [])].filter(f => /\.(png|jpe?g|webp)$/i.test(f.name)); if (!files.length) return; e.preventDefault();
  const payload = await Promise.all(files.map(f => new Promise(res => { const rd = new FileReader(); rd.onload = () => res({name: f.name, data: rd.result}); rd.readAsDataURL(f); })));
  const r = await api("/api/add_images", {files: payload}); if (r.error) { toast(r.error); return; } toast(`Added ${r.added} render${r.added === 1 ? "" : "s"} to the folder`, "ok", 4000); poll();
});
window.addEventListener("pagehide", () => { try { navigator.sendBeacon("/api/bye", "{}"); } catch {} });
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") poll(); });
document.addEventListener("keydown", e => {
  if (e.metaKey || e.ctrlKey || ["INPUT","TEXTAREA","SELECT"].includes(e.target.tagName)) return;
  const m = {"1":"before","2":"wipe","3":"after"};
  if (m[e.key]) $(`.seg button[data-mode=${m[e.key]}]`).click();
  else if (e.key === "j" || e.key === "ArrowDown") { e.preventDefault(); jump(1); }
  else if (e.key === "k" || e.key === "ArrowUp") { e.preventDefault(); jump(-1); }
});
boot();
