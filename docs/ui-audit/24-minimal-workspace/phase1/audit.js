/* 24-minimal-workspace · 第一阶段视觉验收
 *
 * 复现：先起应用（仓库根目录）——`venv/bin/streamlit run app.py`，
 * 再用 `outputs/` 里现成的审计 fixture 逐个打开任务并**实测几何值**
 * （computed style / getBoundingClientRect），不是肉眼看截图。
 *
 *   FOLIO_PLAYWRIGHT_CORE=~/Dev/grok-workspace/node_modules/playwright-core \
 *   FOLIO_CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
 *   node audit.js http://127.0.0.1:8501 .
 *
 * 只读：不改任何任务数据，不调用付费模型。
 * `ui-audit-interrupted` 由同目录 `make_interrupted_fixture.py` 单独生成。
 */
const { chromium } = require(process.env.FOLIO_PLAYWRIGHT_CORE);
const CHROME = process.env.FOLIO_CHROME;
const [url, dir] = process.argv.slice(2);

const MEASURE = () => {
  const q = (s) => document.querySelector(s);
  const box = (el) => { if (!el) return null; const r = el.getBoundingClientRect();
    return { top: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) }; };
  const main = q('[data-testid="stMainBlockContainer"]');
  const rows = [...document.querySelectorAll('[class*="st-key-cat_row_"]')];
  const banner = q('[class*="st-key-workspace_topbar"]');
  const toolbar = q('[class*="st-key-workspace_toolbar"]');
  const chip = q('[class*="st-key-workspace_task_details"] summary');
  // 展开器：Streamlit 1.63 的摘要在 `stExpander > details > summary` 里。
  // 上一版只找 `stExpander > summary`，于是永远数到 0 —— 不能用来断言"没有常驻"。
  const summaries = [...document.querySelectorAll('[data-testid="stExpander"] summary')]
    .map((s) => s.innerText.replace(/\s+/g, ' ').trim());
  const bannerCols = banner
    ? [...banner.querySelectorAll('[data-testid="stColumn"]')].map(box) : [];
  return {
    viewport: { w: window.innerWidth, h: window.innerHeight },
    banner: box(banner),
    bannerCols,
    toolbar: box(toolbar),
    // 验收目标：有段落的翻译页里，首段起始位置应落在视口顶部 360 CSS px 内
    firstRowTop: rows.length ? Math.round(rows[0].getBoundingClientRect().top) : null,
    rowCount: rows.length,
    mainOverflowX: main ? main.scrollWidth > main.clientWidth + 1 : null,
    hasContextColumn: !!q('.st-key-workspace_context_col'),
    verdictChips: document.querySelectorAll('[class*="tp-workspace-verdict"]').length,
    navCanonicalChips: document.querySelectorAll('.tp-nav-canonical').length,
    overviewHero: document.querySelectorAll('.tp-overview-hero').length,
    overlapCards: document.querySelectorAll('.tp-stage-card').length,
    bannerMetrics: [...document.querySelectorAll('.tp-banner-metric')].map(e => e.innerText.trim()),
    runtimeRow: !!q('.tp-banner-runtime'),
    runtimeState: (() => { const e = q('.tp-banner-runtime-state');
      return e ? e.innerText.replace(/\s+/g, ' ').trim() : null; })(),
    runtimeButtons: [...document.querySelectorAll('[class*="st-key-workspace_runtime_actions"] button')]
      .map(b => b.innerText.trim()),
    primaryCta: (() => { const b = q('[class*="st-key-workspace_topbar_cta_"] button');
      return b ? b.innerText.trim() : null; })(),
    navItems: [...document.querySelectorAll('[class*="st-key-workspace_nav_item_"] button')]
      .map(b => b.innerText.trim()),
    emptyBlock: !!q('.tp-empty-block'),
    taskDetailsChip: box(chip),
    // 折叠态展开器：任务详情（工具栏）应当恰好 1 个，且高度 ≤ 32。
    collapsedExpanders: summaries,
  };
};

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME,
    args: ['--no-sandbox', '--disable-gpu'] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2 });
  page.on('pageerror', (e) => console.error('[pageerror]', e.message));
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForSelector('[data-testid="stAppViewContainer"]', { timeout: 30000 });
  await page.waitForTimeout(4500);

  const shot = async (name) => { await page.screenshot({ path: `${dir}/${name}` }); };
  const say = async (label) => console.log(label, JSON.stringify(await page.evaluate(MEASURE)));
  const toHistory = async () => {
    const back = page.locator('button', { hasText: '任务列表' }).first();
    if (await back.count()) { await back.click(); await page.waitForTimeout(2500); }
  };
  const openJob = async (query) => {
    const input = page.locator('[class*="st-key-history_search"] input').first();
    await input.click();
    await input.fill(query);
    await input.press('Enter');
    await page.waitForTimeout(3000);
    await page.locator('button', { hasText: '打开任务' }).first().click();
    await page.waitForTimeout(3500);
  };

  // --- 历史任务（打开任务 = 直接落到翻译工作台）---
  await page.locator('[data-testid="stSidebar"] button', { hasText: '历史任务' })
    .first().click();
  await page.waitForTimeout(3000);
  await shot('01-history.png');

  // --- 1) 已完成任务：Banner 指标 + 主动作 + 首段位置 ---
  await openJob('audit-clean');
  await shot('02-workbench-1440.png');
  await say('1440-clean');

  // --- 2) 真正中断的任务：Banner 内运行区与恢复/重试动作 ---
  await toHistory();
  await openJob('audit-interrupted');
  await shot('03-runtime-interrupted-1440.png');
  await say('1440-interrupted');

  // --- 3) 无段落任务：简短说明，不建右栏 ---
  await toHistory();
  await openJob('audit-new-untranslated');
  await shot('04-unstarted-1440.png');
  await say('1440-empty');

  // --- 4) 窄屏（1024×768）下的同一个已完成任务 ---
  await page.setViewportSize({ width: 1024, height: 768 });
  await toHistory();
  await openJob('audit-clean');
  await shot('05-workbench-1024.png');
  await say('1024-clean');

  // --- 5) 200% 缩放 ---
  // 浏览器缩放在 CSS 像素这一层等价于"物理窗口不变、CSS 视口减半"，所以
  // 1440×900 的窗口放到 200% 就是 720×450 的 CSS 视口（≈ 触到 ≤760px 断点）。
  // 这里只量几何与横向溢出；重排是否可读仍需人眼确认，报告已把这一点列为未覆盖。
  await page.setViewportSize({ width: 720, height: 450 });
  await toHistory();
  await openJob('audit-clean');
  await shot('06-workbench-zoom200.png');
  await say('zoom200-clean');

  console.log('saved to', dir);
  await browser.close();
})().catch((e) => { console.error('FAILED', e.message); process.exit(1); });
