#!/usr/bin/env node
/**
 * 浏览器实测（第二轮）：**运行中**的编辑安全。
 *
 * `audit.js` 验证的是"输入 → 保存 → 刷新"这条直线。真正难的是**并发**：
 * 工作台整体跑在 `@st.fragment(run_every="3s")` 里（`app.py:14426`），也就是说
 * 用户每打两个字，就可能被一次轮询重渲染穿过。这里要回答三个问题，而且只能在
 * 真实浏览器里回答——`AppTest` 没有计时器、没有前端状态机，也拿不到
 * `document.activeElement`：
 *
 *   1. 轮询重渲染时，**还没失焦**的输入会不会被清空 / 回滚 / 抢走焦点？
 *   2. 后台写回（模型/另一个标签页/批量操作）改了磁盘译文时，会不会**覆盖
 *      正在输入的内容**？保存时能不能发现？
 *   3. "保存并下一段"之后，焦点有没有**直接落进下一段的输入框**？
 *   4. 服务端决定"框里该显示什么"时（复制原文到译文 / 采用磁盘上的版本），
 *      已经被敲过字的输入框会不会**跟着换**？
 *
 * 方法与判据：
 *   - "未失焦的输入"用 `page.keyboard.type` 直接打、**不按 Tab**；
 *   - 一次轮询周期是 3s，这里等 9s（≥3 个周期）；
 *   - 判定"没被吞字"读的是 textarea 的 DOM 值，不是服务端 session_state；
 *   - 判定"没被覆盖"读的是磁盘上的 `state.json`（Node 直接读，不经过应用）；
 *   - 后台写回用 Node 原子改写 `state.json` 来模拟，而不是等模型——它和模型写回
 *     在应用眼里是同一件事（下一次轮询读到不同的 target）。
 *
 * 运行（与 `audit.js` 同一约定；`FOLIO_OUTPUT_DIR` 从夹具 stdout 的
 * `FIXTURE_OUTPUT_DIR` 取，磁盘断言需要它）：
 *
 *     FOLIO_PLAYWRIGHT_CORE=~/Dev/grok-workspace/node_modules/playwright-core \
 *     FOLIO_CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
 *     FOLIO_OUTPUT_DIR=<夹具的任务根目录；不设时自动读固定交接文件> \
 *     node docs/ui-audit/25-save-flow/runtime_edit_audit.js http://127.0.0.1:8505 .
 *
 * 环境变量：
 *   FOLIO_URL          目标地址，默认 http://127.0.0.1:8505（位置参数 1 覆盖）
 *   FOLIO_JOB          夹具任务 id，默认 saveflowbrowser01
 *   FOLIO_OUTPUT_DIR   夹具的任务根目录；缺省时跳过全部磁盘断言并**显式标注**
 *   FOLIO_CHROME       系统 Chrome 路径；不设时用 channel=chrome
 *   FOLIO_POLL_WAIT    等待轮询的毫秒数，默认 9000（≥3 个 3s 周期）
 *   SHOT_DIR           截图目录，默认与本脚本同级（位置参数 2 覆盖）
 */
'use strict';

const fs = require('fs');
const path = require('path');
const { chromium } = require(
  process.env.FOLIO_PLAYWRIGHT_CORE || 'playwright-core');

const [argUrl, argDir] = process.argv.slice(2);
const BASE_URL = process.env.FOLIO_URL || argUrl || 'http://127.0.0.1:8505';
const JOB = process.env.FOLIO_JOB || 'saveflowbrowser01';
const SHOT_DIR = process.env.SHOT_DIR || argDir || __dirname;
const SETTLE = Number(process.env.FOLIO_SETTLE || 2600);
const POLL_WAIT = Number(process.env.FOLIO_POLL_WAIT || 9000);

/**
 * 夹具的隔离任务根目录。
 *
 * 优先取 `FOLIO_OUTPUT_DIR`；没设就读 `serve_fixture.py` 留下的固定交接文件。
 * **不要**用 `ls -dt $TMPDIR/folio-save-flow-*` 去猜：机器上留着历次运行的目录，
 * 而本次进程的目录要到第一个会话连上才创建，"最新的那个"既可能是旧的也可能不存在。
 *
 * 读的时机也很重要：交接文件由夹具脚本写出，而夹具脚本要等**第一个会话连上**才
 * 执行。所以在 `main()` 里先删掉旧的交接文件、打开页面、再读——否则读到的是上一次
 * 运行留下的路径，磁盘断言会断言在错误的目录上（而且看起来一切正常）。
 */
const HANDOFF = () => path.resolve(__dirname, '..', '..', '..', '.audit',
  'fixture-output-dir.txt');

function resolveOutputDir() {
  if (process.env.FOLIO_OUTPUT_DIR) return process.env.FOLIO_OUTPUT_DIR;
  try {
    const value = fs.readFileSync(HANDOFF(), 'utf8').trim();
    if (value && fs.existsSync(path.join(value, JOB, 'state.json'))) return value;
  } catch (error) { /* 没有就是没有，下面会跳过磁盘断言并如实标注 */ }
  return '';
}

let OUTPUT_DIR = process.env.FOLIO_OUTPUT_DIR || '';

const POLL_SEGMENT = 0;     // 轮询安全性：第 1 段
const BACKGROUND_SEGMENT = 1;  // 后台写回：第 2 段
const RESET_SEGMENT = 2;    // 输入框复位：第 3 段
const TAB_SEGMENT = 3;      // 双标签页：第 4 段

const SOURCE_RESET = 'Source segment 3 for the browser save-flow audit.';
const TYPED_EARLY = '轮询实测：先提交的内容';
const TYPED_TAIL = '（未失焦追加）';
const MINE = '轮询实测：我这一份草稿';
const THEIRS = '后台写回：别人改过的译文';
const TAB_ONE = '第一页写的第四段';
const TAB_TWO = '第二页写的第四段';

const results = [];
function record(name, ok, detail) {
  results.push({ name, ok });
  console.log(`${ok ? 'ok  ' : 'FAIL'}  ${name}` +
    (detail ? '  — ' + String(detail).slice(0, 190) : ''));
}
function skip(name, why) {
  results.push({ name, ok: null });
  console.log(`跳过  ${name}  — ${why}`);
}

async function shot(page, name) {
  try {
    await page.screenshot({ path: path.join(SHOT_DIR, `${name}.png`), fullPage: true });
  } catch (error) {
    console.log(`（截图 ${name} 失败：${error.message}）`);
  }
}

async function settle(page, ms = SETTLE) {
  await page.waitForTimeout(ms);
  for (let i = 0; i < 25; i += 1) {
    const busy = await page.locator('[data-testid="stStatusWidget"]').count();
    if (!busy) break;
    await page.waitForTimeout(300);
  }
}

// ---------------------------------------------------------------- 磁盘（Node）
function jobFile(name) {
  return path.join(OUTPUT_DIR, JOB, name);
}

function readState() {
  return JSON.parse(fs.readFileSync(jobFile('state.json'), 'utf8'));
}

function readDrafts() {
  try {
    const payload = JSON.parse(fs.readFileSync(jobFile('translation_drafts.json'), 'utf8'));
    return Array.isArray(payload.drafts) ? payload.drafts : [];
  } catch (error) {
    return [];
  }
}

/** 原子改写磁盘译文——模拟"后台写回"。半截文件会让应用读到损坏的 state。 */
function writeDiskTarget(index, text) {
  const state = readState();
  state.pairs[index].target = text;
  const target = jobFile('state.json');
  const tmp = `${target}.audit-tmp`;
  fs.writeFileSync(tmp, JSON.stringify(state, null, 2), 'utf8');
  fs.renameSync(tmp, target);
}

// ---------------------------------------------------------------- DOM helpers
const editorSelector = (index) => `.st-key-cat_editor_${JOB}_${index} textarea`;
const saveButtonSelector = (index) => `.st-key-cat_save_btn_${JOB}_${index} button`;
const saveNextButtonSelector = (index) => `.st-key-cat_save_next_btn_${JOB}_${index} button`;
// 冲突面板按 **widget key** 定位，不按按钮文案——文案会随设计调整，key 是契约。
const conflictKeep = `.st-key-translation_conflict_keep_${JOB} button`;
const conflictTake = `.st-key-translation_conflict_take_${JOB} button`;

async function editorValue(page, index) {
  return page.locator(editorSelector(index)).inputValue();
}

/** 焦点落在哪个段的输入框里（返回容器 key；不在 textarea 上则返回 null）。 */
async function activeEditorKey(page) {
  return page.evaluate(() => {
    const el = document.activeElement;
    if (!el || el.tagName !== 'TEXTAREA') return null;
    const holder = el.closest('[class*="st-key-cat_editor_"]');
    if (!holder) return null;
    return Array.from(holder.classList)
      .find((name) => name.startsWith('st-key-cat_editor_')) || null;
  });
}

async function selectAll(page) {
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+a' : 'Control+a');
  await page.keyboard.press('Backspace');
}

/** 真实输入并**提交**（Tab 失焦 → on_change 的触发时机）。 */
async function retype(page, index, text) {
  const editor = page.locator(editorSelector(index));
  await editor.click();
  await selectAll(page);
  await page.keyboard.type(text, { delay: 12 });
  await page.keyboard.press('Tab');
  await settle(page);
}

/** 真实输入但**不失焦**：模拟"用户正在打字，轮询来了"。 */
async function typeWithoutBlur(page, index, text) {
  const editor = page.locator(editorSelector(index));
  await editor.click();
  await selectAll(page);
  await page.keyboard.type(text, { delay: 12 });
}

async function openPage(browser, label) {
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector(editorSelector(0), { timeout: 60000 });
  await settle(page);
  console.log(`  （${label} 已打开）`);
  return page;
}

async function alertsText(page) {
  return (await page.locator('[data-testid="stAlert"]').allInnerTexts()).join(' | ');
}

// ---------------------------------------------------------------------- 各节
async function pollingSafety(page) {
  console.log('\n[1] 轮询（3s）穿过正在输入的内容');
  await typeWithoutBlur(page, POLL_SEGMENT, TYPED_EARLY);
  await page.keyboard.press('Tab');           // 先提交一次，让草稿层有内容
  await settle(page);
  await page.locator(editorSelector(POLL_SEGMENT)).click();
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+ArrowRight'
                                                          : 'Control+ArrowRight');
  await page.keyboard.type(TYPED_TAIL, { delay: 12 });  // 第二次输入，**不失焦**
  const expected = TYPED_EARLY + TYPED_TAIL;
  const focusBefore = await activeEditorKey(page);

  console.log(`  （等待 ${POLL_WAIT / 1000}s ≈ ${Math.round(POLL_WAIT / 3000)} 个轮询周期，期间不碰页面）`);
  await page.waitForTimeout(POLL_WAIT);

  const afterPoll = await editorValue(page, POLL_SEGMENT);
  record('轮询穿过未失焦的输入后，DOM 内容没有被清空或回滚',
    afterPoll === expected, `实际 ${JSON.stringify(afterPoll)}`);
  const focusAfter = await activeEditorKey(page);
  record('轮询期间没有抢走输入焦点',
    focusAfter === focusBefore && focusBefore !== null,
    `${focusBefore} → ${focusAfter}`);
  await shot(page, '7-polling-typing');

  // Streamlit 的 text_area 只在**失焦 / ⌘+Enter** 时把值交给服务端，所以"未失焦的输入
  // 此刻还不在服务端"是它的提交时机，**不是丢字**。真正要证的是两件事：
  //   (a) 轮询没把它从输入框里抹掉（上面已证）；
  //   (b) 失焦之后它确实落进草稿层 —— 说明轮询没有破坏"输入 → 草稿"这条链路。
  // 这一条原先写成"未失焦的输入已到达服务端"，那是在要求 Streamlit 逐字提交：
  // 一条永远不可能通过的断言，而且会把注意力从 (b) 引开。
  await page.keyboard.press('Tab');
  await settle(page);
  if (!OUTPUT_DIR) {
    skip('失焦后输入落进草稿层', '没有 FOLIO_OUTPUT_DIR，读不到草稿文件');
  } else {
    const drafts = readDrafts();
    const reached = drafts.some(
      (item) => String(item.text || '').includes(TYPED_TAIL));
    record('失焦后输入落进草稿层（轮询没有破坏同步链路）', reached,
      reached ? '' : `草稿文件里没有这段尾巴；当前 ${JSON.stringify(drafts)}`);
  }
  return expected;
}

async function focusAfterSaveAndNext(page, expectedText) {
  console.log('\n[2] 保存并下一段 → 焦点回位');
  const beforeKey = await activeEditorKey(page);
  await page.locator(saveNextButtonSelector(POLL_SEGMENT)).first().click();
  await settle(page);

  if (OUTPUT_DIR) {
    const disk = readState();
    record('保存并下一段把内容写进了磁盘',
      disk.pairs[POLL_SEGMENT].target === expectedText,
      disk.pairs[POLL_SEGMENT].target);
  } else {
    skip('保存并下一段把内容写进了磁盘', '没有 FOLIO_OUTPUT_DIR');
  }
  const nextKey = await activeEditorKey(page);
  record('保存并下一段后焦点直接落进下一段的输入框',
    nextKey === `st-key-cat_editor_${JOB}_${BACKGROUND_SEGMENT}`,
    `${beforeKey} → ${nextKey}`);
  await shot(page, '8-focus-after-save-and-next');
}

async function backgroundWriteback(page) {
  console.log('\n[3] 后台写回 vs 正在输入的内容');
  if (!OUTPUT_DIR) {
    skip('后台写回不覆盖正在输入的内容', '没有 FOLIO_OUTPUT_DIR');
    skip('保存时发现磁盘译文已变并提示', '没有 FOLIO_OUTPUT_DIR');
    return;
  }
  await typeWithoutBlur(page, BACKGROUND_SEGMENT, MINE);
  writeDiskTarget(BACKGROUND_SEGMENT, THEIRS);   // 模拟后台写回
  console.log('  （已模拟后台写回；等待轮询把它读进来）');
  await page.waitForTimeout(POLL_WAIT);

  const stillMine = await editorValue(page, BACKGROUND_SEGMENT);
  record('后台写回后，正在输入的内容没有被覆盖', stillMine === MINE, stillMine);
  await shot(page, '9-background-writeback');

  await page.keyboard.press('Tab');              // 提交 → 草稿记录 baseline
  await settle(page);
  await page.locator(saveButtonSelector(BACKGROUND_SEGMENT)).first().click();
  await settle(page);

  const alerts = await alertsText(page);
  record('保存时发现磁盘译文已变 → 提示而不是静默覆盖',
    alerts.includes('在别处已经改过'), alerts.slice(0, 220));
  const diskDuringConflict = readState().pairs[BACKGROUND_SEGMENT].target;
  record('冲突未解决前，磁盘上仍是对方的版本',
    diskDuringConflict === THEIRS, diskDuringConflict);
  await shot(page, '10-save-conflict');

  await page.locator(conflictKeep).first().click();
  await settle(page);
  const diskAfterChoice = readState().pairs[BACKGROUND_SEGMENT].target;
  record('选择"用我的草稿覆盖"之后才写入我的内容',
    diskAfterChoice === MINE, diskAfterChoice);
}

async function twoTabs(browser, pageOne) {
  console.log('\n[4] 两个真实标签页（两个会话）保存同一段');
  const pageTwo = await openPage(browser, '第二页');
  // 第一页先写：此时第二页的 baseline 仍是"打开时看到的那一份"。
  await retype(pageOne, TAB_SEGMENT, TAB_ONE);
  await pageOne.locator(saveButtonSelector(TAB_SEGMENT)).first().click();
  await settle(pageOne);
  if (OUTPUT_DIR) {
    record('第一页保存写入磁盘',
      readState().pairs[TAB_SEGMENT].target === TAB_ONE,
      readState().pairs[TAB_SEGMENT].target);
  } else {
    skip('第一页保存写入磁盘', '没有 FOLIO_OUTPUT_DIR');
  }

  await retype(pageTwo, TAB_SEGMENT, TAB_TWO);
  await pageTwo.locator(saveButtonSelector(TAB_SEGMENT)).first().click();
  await settle(pageTwo);

  const twoAlerts = await alertsText(pageTwo);
  record('第二页保存时被告知"译文在别处已经改过"',
    twoAlerts.includes('在别处已经改过'), twoAlerts.slice(0, 220));
  if (OUTPUT_DIR) {
    const disk = readState().pairs[TAB_SEGMENT].target;
    record('第二页没有静默覆盖第一页的内容', disk === TAB_ONE, disk);
  } else {
    skip('第二页没有静默覆盖第一页的内容', '没有 FOLIO_OUTPUT_DIR');
  }
  await shot(pageTwo, '11-two-tabs-conflict');

  await pageTwo.locator(conflictTake).first().click();
  await settle(pageTwo);
  const twoEditor = await editorValue(pageTwo, TAB_SEGMENT);
  record('第二页选择"采用磁盘上的版本"后，输入框回到磁盘内容',
    twoEditor === TAB_ONE, twoEditor);
  if (OUTPUT_DIR) {
    record('"采用磁盘上的版本"不改写磁盘',
      readState().pairs[TAB_SEGMENT].target === TAB_ONE,
      readState().pairs[TAB_SEGMENT].target);
  } else {
    skip('"采用磁盘上的版本"不改写磁盘', '没有 FOLIO_OUTPUT_DIR');
  }
  await shot(pageTwo, '12-two-tabs-take-theirs');
  return pageTwo;
}

/**
 * 服务端已经决定"框里该显示什么"时，**前端必须先松手**。
 *
 * 这一节守的是一条真实缺陷：`st.text_area` 的 element id 只由 `(user_key, max_chars)`
 * 决定（`streamlit/elements/lib/utils.py: compute_and_register_element_id`，
 * text_area 传 `key_as_main_identity={"max_chars"}`），**默认值不参与**。
 * 所以"清掉 session_state 的 key、让 widget 用新默认值重建"这条常见做法对
 * **已经被敲过字**的输入框无效：前端组件实例不重挂载，它保留自己的 dirty 值——
 * 用户点了「复制原文到译文」，框里还是自己刚才写的字（「采用磁盘上的版本」「丢弃
 * 未保存的修改」「恢复原译」同理）。修法是换 key 强制重挂载。
 * `AppTest` 没有前端状态机，这条只能在浏览器里证。
 */
async function editorReset(page) {
  console.log('\n[5] 服务端决定内容时，输入框真的换了（复制原文到译文）');
  await retype(page, RESET_SEGMENT, '我自己的草稿');
  const typed = await editorValue(page, RESET_SEGMENT);
  if (typed !== '我自己的草稿') {
    record('复制原文到译文：前置的真实输入就绪', false, JSON.stringify(typed));
    return;
  }
  // 「快捷动作」在行尾的 ⋯ popover 里：**先展开**，内容才进 DOM。
  await page.locator(`.st-key-cat_actions_${JOB}_${RESET_SEGMENT} button`)
    .first().click();
  await settle(page);
  await page.locator(`.st-key-cat_action_copy_${JOB}_${RESET_SEGMENT} button`)
    .first().click();
  await settle(page);
  const after = await editorValue(page, RESET_SEGMENT);
  record('点了复制原文到译文之后，输入框换成原文（而不是留着自己写的字）',
    after === SOURCE_RESET, JSON.stringify(after));
  await shot(page, '13-copy-source-resets-editor');
}

async function main() {
  const chromePath = process.env.FOLIO_CHROME || process.env.CHROME_EXEC;
  const browser = await chromium.launch({
    channel: chromePath ? undefined : 'chrome',
    executablePath: chromePath || undefined,
    headless: true,
  });
  // 先清掉上一次运行留下的交接文件，再打开页面（夹具脚本此时才写新的）。
  try { fs.rmSync(HANDOFF(), { force: true }); } catch (error) { /* 无所谓 */ }
  const page = await openPage(browser, '第一页');
  if (!OUTPUT_DIR) OUTPUT_DIR = resolveOutputDir();
  console.log(OUTPUT_DIR
    ? `  夹具任务目录：${OUTPUT_DIR}`
    : '  注意：拿不到夹具任务目录 —— 全部磁盘断言会被跳过并如实标注。\n');
  const consoleErrors = [];
  page.on('pageerror', (error) => consoleErrors.push(String(error)));

  const expectedAfterPoll = await pollingSafety(page);
  await focusAfterSaveAndNext(page, expectedAfterPoll);
  await backgroundWriteback(page);
  await twoTabs(browser, page);
  await editorReset(page);

  record('浏览器控制台没有未捕获异常', consoleErrors.length === 0,
    consoleErrors.join(' / '));

  await browser.close();

  const failed = results.filter((item) => item.ok === false);
  const skipped = results.filter((item) => item.ok === null);
  console.log('\n' + '='.repeat(72));
  console.log(`检查项 ${results.length - skipped.length} 个，失败 ${failed.length} 个`
    + (skipped.length ? `，跳过 ${skipped.length} 个` : ''));
  if (failed.length) console.log('失败：' + failed.map((item) => item.name).join(', '));
  if (skipped.length) console.log('跳过：' + skipped.map((item) => item.name).join(', '));
  process.exit(failed.length ? 1 : 0);
}

main().catch((error) => {
  console.error('runtime audit 运行失败：', error);
  process.exit(2);
});
