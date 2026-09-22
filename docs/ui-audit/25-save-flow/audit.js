#!/usr/bin/env node
/**
 * 浏览器实测：真实输入 → 保存 → 刷新持久化，以及"切筛选不丢稿"。
 *
 * 为什么必须真开浏览器：`AppTest` 即使走 `set_value`，也仍在同一个 Python
 * 进程里读同一个 `session_state`。它证明不了"前端把刚敲的内容送回服务端、
 * 保存按钮真的出现在用户眼前、刷新之后内容还在"这三件事——而上一轮的缺陷
 * 恰恰是"按钮永远不出现"。
 *
 * 它同时也是**边界**的证据：刷新会重建浏览器会话（`st.session_state` 属于会话），
 * 因此草稿必须是"落在任务目录里的那一份"才能在刷新后回来。第 4 节验证的就是这件事：
 * 刷新之后草稿被恢复、并且明确告知用户"这是恢复回来的草稿"。
 * 只把草稿放进会话是修不掉刷新丢稿的；上一版这里曾断言"刷新后草稿不再存在"，
 * 那条断言在本轮实现之后已经不成立（它描述的是旧实现的限制，不是需求）。
 *
 * 运行（playwright-core 与本仓库解耦，与 24-minimal-workspace/phase1 同一约定：
 * 用 `FOLIO_PLAYWRIGHT_CORE` 指向那个模块目录；未设置时退回 `NODE_PATH` 解析）：
 *
 *     FOLIO_PLAYWRIGHT_CORE=~/Dev/grok-workspace/node_modules/playwright-core \
 *     FOLIO_CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
 *     node docs/ui-audit/25-save-flow/audit.js http://127.0.0.1:8505 .
 *
 * 环境变量：
 *   FOLIO_URL   目标地址，默认 http://127.0.0.1:8505（也可用位置参数 1 覆盖）
 *   FOLIO_JOB   夹具任务 id，默认 saveflowbrowser01
 *   FOLIO_CHROME / CHROME_EXEC  Chrome 可执行文件；都不设时用系统 Chrome（channel=chrome）
 *   SHOT_DIR    截图目录，默认与本脚本同级（也可用位置参数 2 覆盖）
 */
'use strict';

const path = require('path');
const { chromium } = require(
  process.env.FOLIO_PLAYWRIGHT_CORE || 'playwright-core');

const [argUrl, argDir] = process.argv.slice(2);
const BASE_URL = process.env.FOLIO_URL || argUrl || 'http://127.0.0.1:8505';
const JOB = process.env.FOLIO_JOB || 'saveflowbrowser01';
const SHOT_DIR = process.env.SHOT_DIR || argDir || __dirname;
const SETTLE = Number(process.env.FOLIO_SETTLE || 2600);

const ACTIVE_INDEX = 0;      // 打开任务时的当前段落
const TARGET_INDEX = 2;      // 第 3 段（未审校）——用来验证"筛掉再切回来"
const TYPED = '浏览器实测：第三段译文（输入 → 筛切 → 保存 → 刷新）';

const results = [];
function record(name, ok, detail) {
  results.push({ name, ok });
  console.log(`${ok ? 'ok  ' : 'FAIL'}  ${name}${detail ? '  — ' + String(detail).slice(0, 160) : ''}`);
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

const editorSelector = (index) => `.st-key-cat_editor_${JOB}_${index} textarea`;
const saveButtonSelector = (index) => `.st-key-cat_save_btn_${JOB}_${index} button`;

async function editorValue(page, index) {
  return page.locator(editorSelector(index)).inputValue();
}

/** 真实输入：聚焦 → 全选 → 逐字键入 → 失焦（on_change 的触发时机）。 */
async function retype(page, index, text) {
  const editor = page.locator(editorSelector(index));
  await editor.click();
  await editor.press(process.platform === 'darwin' ? 'Meta+a' : 'Control+a');
  await editor.press('Backspace');
  await page.keyboard.type(text, { delay: 12 });
  await page.keyboard.press('Tab');
  await settle(page);
}

async function openPage(browser) {
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector(editorSelector(ACTIVE_INDEX), { timeout: 60000 });
  await settle(page);
  return page;
}

async function clickFilter(page, label) {
  await page.locator('[role="radiogroup"] button[role="radio"]', { hasText: label })
    .first().click();
  await settle(page);
}

async function main() {
  const chromePath = process.env.FOLIO_CHROME || process.env.CHROME_EXEC;
  const browser = await chromium.launch({
    channel: chromePath ? undefined : 'chrome',
    executablePath: chromePath || undefined,
    headless: true,
  });
  const page = await openPage(browser);
  const consoleErrors = [];
  page.on('pageerror', (error) => consoleErrors.push(String(error)));
  await shot(page, '1-initial');

  // --- 1. 初始：只有"当前段落"那一行有保存入口 -----------------------------
  const activeSave = await page.locator(saveButtonSelector(ACTIVE_INDEX)).count();
  const idleSave = await page.locator(saveButtonSelector(TARGET_INDEX)).count();
  record('当前段落常驻保存入口（真实渲染）', activeSave === 1, `找到 ${activeSave} 个`);
  record('未修改的其它段落不常驻保存入口', idleSave === 0, `找到 ${idleSave} 个`);
  record('初始状态没有"未保存"提示',
    (await page.getByText('未保存', { exact: false }).count()) === 0);

  // --- 2. 真实输入 → 服务端算出"未保存" ------------------------------------
  await retype(page, TARGET_INDEX, TYPED);
  const valueAfterTyping = await editorValue(page, TARGET_INDEX);
  record('输入框保留了刚敲的内容', valueAfterTyping === TYPED, valueAfterTyping);
  record('输入后出现"未保存"提示',
    (await page.getByText('未保存', { exact: false }).count()) > 0);
  const saveNow = await page.locator(saveButtonSelector(TARGET_INDEX)).count();
  record('输入后该行出现保存入口（真实输入路径）', saveNow === 1, `找到 ${saveNow} 个`);
  await shot(page, '2-typed');

  // --- 3. 切筛选再切回来：内容不能丢，也不能退回旧译文 ---------------------
  await clickFilter(page, '已审校');
  const hiddenEditor = await page.locator(editorSelector(TARGET_INDEX)).count();
  record('筛掉之后该行不再渲染输入框', hiddenEditor === 0, `找到 ${hiddenEditor} 个`);
  await clickFilter(page, '全部');
  const afterFilter = await editorValue(page, TARGET_INDEX);
  record('切筛选回来仍是自己敲的内容（不是旧译文）', afterFilter === TYPED, afterFilter);
  await shot(page, '3-filter-round-trip');

  // --- 4. 刷新（= 新会话）：草稿必须被恢复回来 -----------------------------
  const banner = await page.locator('[data-testid="stAlert"]').allInnerTexts();
  record('横幅说明草稿不是正式译文、不会获得审校结论',
    banner.join(' ').includes('不是正式译文'), banner.join(' ').slice(0, 220));
  const beforeReload = await page.locator('[data-testid="stAlert"]').allInnerTexts();
  record('刷新前横幅报出未保存处数',
    beforeReload.join(' ').includes('未保存的译文修改'), beforeReload.join(' ').slice(0, 200));

  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForSelector(editorSelector(TARGET_INDEX), { timeout: 60000 });
  await settle(page);
  const afterReloadDraft = await editorValue(page, TARGET_INDEX);
  record('刷新（新会话）后未保存草稿被恢复', afterReloadDraft === TYPED, afterReloadDraft);
  const restoredAlerts = (await page.locator('[data-testid="stAlert"]').allInnerTexts()).join(' ');
  record('恢复必须被明确告知（不能静默恢复）',
    restoredAlerts.includes('已从本机任务目录恢复'), restoredAlerts.slice(0, 220));
  await shot(page, '4-after-reload');

  // --- 5. 输入并保存 → 明确反馈 --------------------------------------------
  await retype(page, TARGET_INDEX, TYPED);
  await page.locator(saveButtonSelector(TARGET_INDEX)).first().click();
  await settle(page);
  const alerts = (await page.locator('[data-testid="stAlert"]').allInnerTexts()).join(' | ');
  record('保存后有成功反馈', alerts.includes('已保存'), alerts.slice(0, 200));
  record('保存后"未保存"提示消失',
    (await page.getByText('未保存', { exact: false }).count()) === 0);
  await shot(page, '5-saved');

  // --- 6. 再刷新：已保存内容必须持久化 -------------------------------------
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForSelector(editorSelector(TARGET_INDEX), { timeout: 60000 });
  await settle(page);
  const afterReloadSaved = await editorValue(page, TARGET_INDEX);
  record('刷新后已保存内容持久化（真落盘）', afterReloadSaved === TYPED, afterReloadSaved);
  record('刷新后没有残留的"未保存"提示',
    (await page.getByText('未保存', { exact: false }).count()) === 0);
  await shot(page, '6-reload-persisted');

  record('浏览器控制台没有未捕获异常', consoleErrors.length === 0,
    consoleErrors.join(' / '));

  await browser.close();

  const failed = results.filter((item) => !item.ok);
  console.log('\n' + '='.repeat(72));
  console.log(`检查项 ${results.length} 个，失败 ${failed.length} 个`);
  if (failed.length) console.log('失败：' + failed.map((item) => item.name).join(', '));
  process.exit(failed.length ? 1 : 0);
}

main().catch((error) => {
  console.error('audit 运行失败：', error);
  process.exit(2);
});
