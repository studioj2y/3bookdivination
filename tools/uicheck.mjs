// 占卜站 UI 真机回归（Chrome CDP，零依赖）
// 用法：
//   1) 起服务   python -m uvicorn api.app:app --port 8011 --host 127.0.0.1
//   2) 起 Chrome chrome --headless=new --disable-gpu --remote-debugging-port=9222 --user-data-dir=<临时目录>
//   3) node tools/uicheck.mjs
// 退出码 0=全部 PASS，1=有 FAIL；截图输出到 ../_shots/。可用 UI_BASE / UI_CDP 覆盖地址。
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.join(ROOT, "_shots");
const BASE = process.env.UI_BASE || "http://127.0.0.1:8011";
const CDP  = process.env.UI_CDP  || "http://127.0.0.1:9222";
fs.mkdirSync(OUT, { recursive: true });
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function getTarget(){
  for (let i = 0; i < 60; i++){
    try{ const l = await (await fetch(CDP + "/json/list")).json();
      const p = l.find(t => t.type === "page"); if (p && p.webSocketDebuggerUrl) return p; }catch(e){}
    await sleep(250);
  }
  throw new Error("no cdp target");
}
const t = await getTarget();
const ws = new WebSocket(t.webSocketDebuggerUrl);
let id = 0, loaded = false; const pend = new Map(); const errors = [];
ws.addEventListener("message", ev => {
  const m = JSON.parse(typeof ev.data === "string" ? ev.data : ev.data.toString());
  if (m.id && pend.has(m.id)){ pend.get(m.id)(m); pend.delete(m.id); }
  if (m.method === "Page.loadEventFired") loaded = true;
  if (m.method === "Runtime.exceptionThrown") errors.push((m.params.exceptionDetails.exception && m.params.exceptionDetails.exception.description || m.params.exceptionDetails.text).split("\n")[0]);
});
await new Promise(r => ws.addEventListener("open", r));
function send(method, params = {}, ms = 20000){
  return new Promise(res => { const i = ++id; pend.set(i, res);
    ws.send(JSON.stringify({ id: i, method, params }));
    setTimeout(() => { if (pend.has(i)){ pend.delete(i); res({ __t: 1 }); } }, ms); });
}
async function js(expr){
  const r = await send("Runtime.evaluate", { expression: `(function(){${expr}})()`, returnByValue: true, awaitPromise: true });
  if (r.__t) return "__TIMEOUT__";
  if (r.result && r.result.exceptionDetails) return "__ERR__";
  return r.result && r.result.result ? r.result.result.value : undefined;
}
async function rect(sel){ return js(`var e=document.querySelector(${JSON.stringify(sel)}); if(!e) return null;
  var r=e.getBoundingClientRect(); return {x:r.left+r.width/2,y:r.top+r.height/2,w:r.width,h:r.height,left:r.left,right:r.right};`); }
async function clickAt(x, y){
  await send("Input.dispatchMouseEvent", { type:"mousePressed", x, y, button:"left", clickCount:1, buttons:1 });
  await sleep(40);
  await send("Input.dispatchMouseEvent", { type:"mouseReleased", x, y, button:"left", clickCount:1, buttons:0 });
}
// 点击：若元素不在视口内先 scrollIntoView 再点。
// ⚠ 教训：早先直接拿 getBoundingClientRect 的中心去点，长页面里「折叠下方」的元素坐标在屏外，
//   点击会静默落空（而 display:none 的元素 rect 全 0，点 (0,0) 同样静默失败）⇒ 回归结果随机飘。
//   已可见的元素不做任何延时，保证 B10「首击即生效」这类时序断言不被削弱。
async function clickSel(sel){
  const st = await js(`var e=document.querySelector(${JSON.stringify(sel)}); if(!e) return null;
    var r=e.getBoundingClientRect();
    var vis = r.width>0 && r.height>0 && r.top>=0 && r.bottom<=innerHeight && r.left>=0 && r.right<=innerWidth;
    if(!vis) e.scrollIntoView({block:'center', inline:'center'});
    return {vis:vis};`);
  if (!st) return false;
  if (!st.vis) await sleep(140);
  const r = await rect(sel);
  if (!r || r.w < 1 || r.h < 1) return false;   // 0×0 ⇒ display:none，明确算失败而不是乱点
  await clickAt(r.x, r.y); return true;
}
async function waitFor(expr, ms = 6000, step = 100){ const t0 = Date.now();
  while (Date.now() - t0 < ms){ if (await js(`return !!(${expr})`)) return Date.now() - t0; await sleep(step); } return -1; }
async function shot(name){
  const r = await send("Page.captureScreenshot", { format:"jpeg", quality:82, captureBeyondViewport:false });
  if (!r.result || !r.result.data){ console.log("  shot FAILED " + name); return; }
  fs.writeFileSync(path.join(OUT, name + ".jpg"), Buffer.from(r.result.data, "base64"));
  console.log("  shot -> " + name + ".jpg");
}
const results = [];
const check = (name, pass, detail) => { results.push({ name, pass: !!pass, detail: detail === undefined ? "" : String(detail) });
  console.log((pass ? "PASS " : "FAIL ") + name + (detail !== undefined ? "   " + detail : "")); };

const PANELS = `var on=[]; ['baziPanel','tarotPanel','liuyaoPanel'].forEach(function(i){
  var e=document.getElementById(i); if(e && e.classList.contains('show')) on.push(i); }); return on;`;

await send("Page.enable"); await send("Runtime.enable");

// ==================== 桌面 1440x900 ====================
console.log("--- 桌面 1440x900 ---");
await send("Emulation.setDeviceMetricsOverride", { width:1440, height:900, deviceScaleFactor:1, mobile:false });
loaded = false; await send("Page.navigate", { url:BASE + "/" });
for (let i = 0; i < 120 && !loaded; i++) await sleep(100);
await waitFor("window.phase==='intro'", 5000);

check("A7 引导期光标挂在 body（#gl 无 pointer-events 时仍生效）",
  await js("return document.body.style.cursor === 'pointer'"), "body.cursor=" + await js("return document.body.style.cursor || '(空)'"));

await clickSel("#skip");
check("A9 跳过引导后首屏提示被清掉",
  await waitFor("+getComputedStyle(document.getElementById('hint')).opacity === 0", 2500) > 0,
  "hint.opacity=" + await js("return getComputedStyle(document.getElementById('hint')).opacity"));

await waitFor("document.getElementById('books').classList.contains('show')", 5000);
const atShow = await js(`var b=document.getElementById('books'), w=document.querySelector('.bookWrap');
  return {ready:b.classList.contains('ready'), pe:getComputedStyle(w).pointerEvents};`);
check("A2 书现身瞬间仍不可点", atShow.pe === "none" && atShow.ready === false, JSON.stringify(atShow));

const rTarot = await rect('.book[data-idx="2"]');
await clickAt(rTarot.x, rTarot.y); await sleep(400);
const early = await js("return {func:document.body.classList.contains('func'), fp:document.getElementById('funcpage').classList.contains('show')};");
check("A2 入场期点书无效（防盲点误触）", early.func === false && early.fp === false, JSON.stringify(early));

const rdyMs = await waitFor("document.getElementById('books').classList.contains('ready')", 6000);
const peReady = await js("return getComputedStyle(document.querySelector('.bookWrap')).pointerEvents");
check("A2 入场结束后放开点击", rdyMs > 0 && peReady === "auto", "ready 用时 " + rdyMs + "ms, pe=" + peReady);

const astro = await js(`var b=document.querySelector('.book[data-idx="1"]'), bd=b.querySelector('.badge'), r=bd.getBoundingClientRect();
  return {locked:b.classList.contains('locked'), badge:bd.textContent, badgeVisible:(r.width>0&&r.height>0),
    filter:getComputedStyle(b).filter.slice(0,30)};`);
check("A3 占星书 = 未开放态（locked + 角标 + 蒙灰）",
  astro.locked && astro.badge === "未开放" && astro.badgeVisible && /brightness\(0\.3/.test(astro.filter), JSON.stringify(astro));
await shot("01-books-desktop");

const rAstro = await rect('.book[data-idx="1"]');
await clickAt(rAstro.x, rAstro.y); await sleep(500);
const ac = await js(`return {func:document.body.classList.contains('func'), fp:document.getElementById('funcpage').classList.contains('show'),
  shown:document.getElementById('toast').classList.contains('show'), text:document.getElementById('toast').textContent};`);
check("A3 点未开放书 → 只弹提示、不进死页",
  !ac.func && !ac.fp && ac.shown && /占星/.test(ac.text), JSON.stringify(ac));
await shot("02-toast-astrology");

const z = await js(`return {ver:+getComputedStyle(document.getElementById('ver')).zIndex,
  page:+getComputedStyle(document.getElementById('funcpage')).zIndex};`);
check("B1 版本号降层（ver 7 < funcpage 8）", z.ver === 7 && z.page === 8 && z.ver < z.page, JSON.stringify(z));
check("C8 五行配色常量已合并", await js("return typeof LY_WX!=='undefined' && LY_WX === WX_COLOR"), "LY_WX===WX_COLOR");

// 六爻端到端
await clickSel('.book[data-idx="3"]');
await waitFor("document.getElementById('liuyaoPanel').classList.contains('show')", 4000);
check("B9 进入六爻后只有一个功能页可见（无面板叠加）",
  JSON.stringify(await js(PANELS)) === '["liuyaoPanel"]', JSON.stringify(await js(PANELS)));

const pre = await js(`var e=document.querySelector('#lyStart'), r=e.getBoundingClientRect();
  var h=document.elementFromPoint(r.left+r.width/2, r.top+r.height/2);
  return {rect:Math.round(r.width)+'x'+Math.round(r.height)+'@'+Math.round(r.left)+','+Math.round(r.top),
    hit:(h?h.tagName+'#'+h.id:'null'), askDisp:getComputedStyle(document.getElementById('lyAsk')).display,
    castDisp:getComputedStyle(document.getElementById('lyCast')).display};`);
console.log("  #lyStart 前置状态 " + JSON.stringify(pre));
// B10：面板刚打开时的「首击」必须立即生效（此前会被已隐去的书吃掉）
await clickSel("#lyStart"); await sleep(400);
const opened = (await js("return getComputedStyle(document.getElementById('lyCast')).display")) !== "none";
check("B10 面板刚打开时首击即生效（不再被隐去的书吞掉）", opened === true,
  "点 1 次后 #lyCast 展开=" + opened);

async function tossOnce(i){
  const before = await js("return lyYaos.length");
  await clickSel("#lyToss");
  const t0 = Date.now();
  while (Date.now() - t0 < 1600){ if (await js("return lyYaos.length") > before) return true; await sleep(120); }
  console.log("   ⚠ 第 " + (i + 1) + " 爻点击未生效：#lyInfo='" +
    await js("return document.getElementById('lyInfo').textContent") + "' disabled=" +
    await js("return document.getElementById('lyToss').disabled"));
  return false;
}
// ---------- 六爻 C4：先把卦局定下来，再驱动 UI，彻底去掉随机性 ----------
// UI 的每一爻由 lyRand()（3 枚铜钱）决定：0背=老阴(动) 1背=少阳 2背=少阴 3背=老阳(动)。
// 所以任意目标卦局都能反推出一串 18 次 lyRand 布尔值 ⇒ 可以确定性地摇出指定卦。
const coinsFor = (yang, moving) => moving ? (yang ? [true,true,true] : [false,false,false])
                                          : (yang ? [true,false,false] : [true,true,false]);
const LY_CAT = await js("return (typeof lyCategory !== 'undefined' && lyCategory) ? lyCategory.value : ''");
const LY_SEX = await js("return (typeof lySex !== 'undefined' && lySex) ? lySex.value : ''");
async function pickCast(){
  const mk = s => Array.prototype.map.call(s, ch =>
    ch === 'M' ? [false,true] : ch === 'Y' ? [true,true] : ch === 'y' ? [true,false] : [false,false]);
  // 已实测过标记产量的候选（2026-09-16 实测：乾为天 8、水火既济 8+4 组合、坤为地 5）
  const cands = [
    ['全老阳·乾为天（六爻皆动）', mk('YYYYYY')],
    ['阴阳交替动·水火既济', mk('YmYmYm')],
    ['全老阴·坤为地（六爻皆动）', mk('MMMMMM')],
    ['初爻老阳·地雷复', mk('Yiiiii')],
    ['二爻老阳·地水师', mk('iYiiii')],
    ['三爻老阳·地山谦', mk('iiYiii')],
    ['四爻老阳·雷地豫', mk('iiiYii')],
    ['六爻老阳·山地剥', mk('iiiiiY')],
  ];
  const tried = [];
  for (const [label, yao] of cands){
    const res = await fetch(BASE + "/api/liuyao", { method:"POST", headers:{ "Content-Type":"application/json" },
      body: JSON.stringify({ yao, category:LY_CAT, sex:LY_SEX, question:null }) });
    const j = await res.json();
    // ⚠ 标记挂在 ben.yao[].flags（顶层没有 yao 字段），变卦另算
    const nf = (j && j.ben && j.ben.yao)
      ? j.ben.yao.reduce((s, x) => s + ((x.flags || []).length), 0) : -1;
    const ncb = (j && j.bian && j.bian.yao)
      ? j.bian.yao.reduce((s, x) => s + ((x.flags || []).length), 0) : 0;
    tried.push(label + "=" + nf + (ncb ? "+" + ncb : ""));
    if (nf > 0) return { label, yao, tried, seq: [].concat.apply([], yao.map(y => coinsFor(y[0], y[1]))) };
  }
  return { tried };
}
const pick = await pickCast();
console.log("  进阶卦局探测（name=标记数）" + JSON.stringify(pick.tried));

async function tossSix(){
  let done = 0;
  for (let i = 0; i < 6; i++){ if (await tossOnce(i)) done++; await sleep(120); }
  return done;
}

// (1) 先摇一局「六爻皆静」⇒ 必然无进阶标记，用来覆盖「再摇一卦」复位路径
//     （这条路径此前被点的其实是屏外的按钮，静默失效 ⇒ 测试假红）
await js(`var _sq=[true,false,false], _i=0; window.__lyRandReal = lyRand;
  lyRand = function(){ return _sq[(_i++) % 3]; }; return 1;`);
const dA = await tossSix();
const rowsA = await waitFor("document.querySelector('#lyResult').children.length > 2", 12000);
await sleep(300);
const nfA = await js("return document.querySelectorAll('.ly-flag').length");
const clickedAgain = await clickSel("#lyAgain");
await sleep(500);
const re = await js(`return {cast:getComputedStyle(document.getElementById('lyCast')).display !== 'none',
  dis:document.getElementById('lyToss').disabled, yao:lyYaos.length,
  rows:document.getElementById('lyResult').children.length};`);
check("C4 六爻「再摇一卦」能复位重摇（不再卡死在已装卦态）",
  dA === 6 && rowsA > 0 && nfA === 0 && clickedAgain && re.cast && re.dis === false && re.yao === 0 && re.rows === 0,
  "静卦 flags=" + nfA + " 复位后 " + JSON.stringify(re));

// (2) 注入后端确认过「必带标记」的卦局，验 C4 标记本体
let flags = null;
if (pick.seq){
  await js(`var _s=${JSON.stringify(pick.seq)}, _j=0;
    lyRand = function(){ return _s[(_j++) % _s.length]; }; return 1;`);
  const dB = await tossSix();
  const rowsB = await waitFor("document.querySelector('#lyResult').children.length > 2", 12000);
  await sleep(400);
  const gotYao = await js("return JSON.stringify(lyYaos)");
  const wantYao = JSON.stringify(pick.yao);
  flags = await js(`var f=document.querySelector('.ly-flag'); if(!f) return null;
    return {tag:f.tagName, name:f.dataset.name, desc:f.dataset.desc, n:document.querySelectorAll('.ly-flag').length,
      adv:document.querySelectorAll('.ly-adv .ai').length, rows:document.querySelector('#lyResult').children.length};`);
  check("C4 进阶标记渲染为 <button> 且带 data-desc",
    dB === 6 && rowsB > 0 && gotYao === wantYao && !!flags && flags.tag === "BUTTON" && !!flags.desc,
    "卦局「" + pick.label + "」摇出=" + gotYao + (gotYao === wantYao ? "" : "（期望 " + wantYao + "）") + " " + JSON.stringify(flags));
} else {
  check("C4 进阶标记渲染为 <button> 且带 data-desc", false,
    "后端对候选卦局都没返回 flag：" + JSON.stringify(pick.tried));
}
if (flags){
  await clickSel(".ly-flag"); await sleep(400);
  const ft = await js("return {shown:document.getElementById('toast').classList.contains('show'), text:document.getElementById('toast').textContent};");
  check("C4 点进阶标记 → 弹出释义（移动端唯一可读路径）",
    ft.shown && ft.text.indexOf("：") > 0 && ft.text.length > 6, JSON.stringify(ft));
}
await js("lyRand = window.__lyRandReal; return 1");
// 翻牌/终章之外：确认返回书架会收起面板
await clickSel("#fpBack"); await sleep(600);
check("B9 返回书架收起全部功能页",
  JSON.stringify(await js(PANELS)) === '[]' && await js("return !document.getElementById('funcpage').classList.contains('show')"),
  JSON.stringify(await js(PANELS)));
await shot("03-liuyao-result");

// ==================== 手机 390x844 ====================
console.log("\n--- 手机 390x844 ---");
await send("Emulation.setDeviceMetricsOverride", { width:390, height:844, deviceScaleFactor:1, mobile:true });
await send("Emulation.setTouchEmulationEnabled", { enabled:true, maxTouchPoints:1 });
loaded = false; await send("Page.navigate", { url:BASE + "/" });
for (let i = 0; i < 120 && !loaded; i++) await sleep(100);
await waitFor("window.phase==='intro'", 5000);
await clickSel("#skip");
await waitFor("document.getElementById('books').classList.contains('ready')", 9000);

const geo = await js(`var vw=innerWidth, out=[];
  document.querySelectorAll('.book').forEach(function(b){ var r=b.getBoundingClientRect();
    out.push({idx:+b.dataset.idx, left:Math.round(r.left), right:Math.round(r.right), w:Math.round(r.width), inside:(r.left>=-0.5 && r.right<=vw+0.5)}); });
  var bk=document.getElementById('books');
  return {vw:vw, books:out, scrollW:bk.scrollWidth, clientW:bk.clientWidth};`);
check("B8 手机端四本书全在屏内（可点）",
  geo.books.length === 4 && geo.books.every(b => b.inside) && geo.scrollW <= geo.clientW + 1, JSON.stringify(geo));
await shot("05-mobile-books");

await js("mouse.active = false; return 1");
await send("Input.dispatchTouchEvent", { type:"touchStart", touchPoints:[{ x:120, y:500 }] });
await sleep(250);
const ts = await js("return {active:mouse.active, x:Math.round(mouse.x), y:Math.round(mouse.y)};");
check("D8 移动端触摸驱动指尖光（window 监听生效）",
  ts.active === true && Math.abs(ts.x - 120) < 6 && Math.abs(ts.y - 500) < 6, JSON.stringify(ts));
await send("Input.dispatchTouchEvent", { type:"touchEnd", touchPoints:[] });

await clickSel('.book[data-idx="0"]');
await waitFor("document.getElementById('baziPanel').classList.contains('show')", 4000);
check("B9 进入八字后只有一个功能页可见", JSON.stringify(await js(PANELS)) === '["baziPanel"]', JSON.stringify(await js(PANELS)));

await js("document.getElementById('bzDate').value='1990-05-15'; document.getElementById('bzHour').value='10'; return 1;");
await clickSel("#bzGo");
const gotBz = await waitFor("document.querySelector('#bzResult .bz-pillar')", 12000);
await sleep(900);

const mob = await js(`var fp=document.getElementById('funcpage'), bp=document.getElementById('baziPanel');
  var cs=getComputedStyle(bp);
  var go=document.getElementById('bzGo').getBoundingClientRect(), back=document.getElementById('fpBack').getBoundingClientRect();
  var nav=document.querySelector('.bz-lynav button'), nr=nav?nav.getBoundingClientRect():null;
  return {panelMaxH:cs.maxHeight, panelOvY:cs.overflowY, innerScroll:(bp.scrollHeight-bp.clientHeight) > 2,
    pageScroll:(fp.scrollHeight-fp.clientHeight) > 2, pageOvY:getComputedStyle(fp).overflowY,
    goH:Math.round(go.height), backH:Math.round(back.height), navH:nr?Math.round(nr.height):null};`);
check("B2 手机端八字面板不再内滚（单层滚动）",
  mob.panelMaxH === "none" && mob.panelOvY === "visible" && mob.innerScroll === false,
  JSON.stringify({ maxH:mob.panelMaxH, ovY:mob.panelOvY, 内滚:mob.innerScroll, 已排盘:gotBz > 0 }));
check("B2 #funcpage 承担唯一纵向滚动", mob.pageScroll === true, "overflowY=" + mob.pageOvY);
check("B4 触控目标 ≥44px",
  mob.goH >= 44 && mob.backH >= 44 && (mob.navH === null || mob.navH >= 44),
  JSON.stringify({ 排盘:mob.goH, 流年翻页:mob.navH, 返回书架:mob.backH }));
await shot("04-mobile-bazi");

// B3 安全区：先查 CSSOM 里确实写了 env()，再用 CDP 注入真实安全区看是否生效
const cssEnv = await js(`var hit=[]; for(var i=0;i<document.styleSheets.length;i++){
    var rs=document.styleSheets[i].cssRules||[];
    for(var j=0;j<rs.length;j++){ var t=rs[j].cssText||''; if(t.indexOf('env(safe-area-inset')>=0) hit.push(rs[j].selectorText||rs[j].media&&rs[j].media.mediaText||'(rule)'); } }
  return hit;`);
const ins = await send("Emulation.setSafeAreaInsetsOverride", { insets:{ top:44, bottom:34, left:0, right:0 } });
if (ins && ins.error){
  console.log("  （CDP 不支持 setSafeAreaInsetsOverride：" + ins.error.message + "）改用 CSSOM 断言");
  check("B3 固定元素接入安全区 env(safe-area-inset-*)（CSSOM 证据）",
    Array.isArray(cssEnv) && cssEnv.length >= 2, JSON.stringify(cssEnv));
} else {
  await sleep(400);
  const real = await js(`return {ver:getComputedStyle(document.getElementById('ver')).bottom,
    skip:getComputedStyle(document.getElementById('skip')).top, hint:getComputedStyle(document.getElementById('hint')).bottom};`);
  check("B3 注入 44/34 安全区后固定元素让位正确",
    Math.abs(parseFloat(real.ver) - 42) < 1.5 && Math.abs(parseFloat(real.skip) - 58) < 1.5,
    JSON.stringify(real) + "  CSSOM命中 " + JSON.stringify(cssEnv));
  await shot("06-mobile-safearea");
  await send("Emulation.setSafeAreaInsetsOverride", { insets:{ top:0, bottom:0, left:0, right:0 } });
}

const fail = results.filter(r => !r.pass);
console.log("\n===== 汇总：" + (results.length - fail.length) + " PASS / " + fail.length + " FAIL =====");
for (const f of fail) console.log("FAIL " + f.name + "  " + f.detail);
if (errors.length){ console.log("\n运行期 JS 异常："); for (const e of errors) console.log("  - " + e); }
else console.log("无运行期 JS 异常");
ws.close();
process.exit(fail.length ? 1 : 0);
