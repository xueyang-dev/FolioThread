/* 24-minimal-workspace · 第一阶段几何剖析（一次性探测，不是验收脚本）
 *
 * 目的：把任务工作台「工具栏底边 → 首段行」之间的每一层盒模型量出来，找出
 * 是哪些行/间距吃掉了首屏。改动前后的对比靠它，不靠肉眼。
 *
 *   FOLIO_PLAYWRIGHT_CORE=~/Dev/grok-workspace/node_modules/playwright-core \
 *   FOLIO_CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
 *   node probe.js http://127.0.0.1:8501 [selector] [job-query]
 *
 * 不传 selector 时默认 dump `stMainBlockContainer` 下的垂直堆叠。
 */
const { chromium } = require(process.env.FOLIO_PLAYWRIGHT_CORE);
const CHROME = process.env.FOLIO_CHROME;
const [url, selector, query] = process.argv.slice(2);
const root = selector || '[data-testid="stMainBlockContainer"]';

const DUMP = (rootSel) => {
  const main = document.querySelector(rootSel);
  if (!main) return { error: 'no root ' + rootSel };
  const out = [];
  const walk = (el, depth) => {
    if (depth > 11) return;
    for (const child of el.children) {
      const key = [...child.classList].find(c => c.startsWith('st-key-')) || '';
      const testid = child.getAttribute('data-testid') || '';
      const r = child.getBoundingClientRect();
      if (r.height === 0) continue;
      out.push({ depth, key, testid,
                 top: Math.round(r.top), h: Math.round(r.height),
                 text: (child.innerText || '').replace(/\s+/g, ' ').slice(0, 40),
                 cs: (() => {
                   const s = getComputedStyle(child);
                   return [s.display, s.flexWrap, s.fontSize, s.lineHeight,
                           s.marginTop + '/' + s.marginBottom,
                           s.paddingTop + '/' + s.paddingBottom].join(' ');
                 })() });
      if (!child.matches('[class*="st-key-cat_row_"]')) walk(child, depth + 1);
    }
  };
  walk(main, 0);
  const rows = [...document.querySelectorAll('[class*="st-key-cat_row_"]')];
  return {
    viewport: { w: window.innerWidth, h: window.innerHeight },
    rows: rows.length,
    firstRowTop: rows.length ? Math.round(rows[0].getBoundingClientRect().top) : null,
    scrollY: Math.round(window.scrollY),
    stack: out,
  };
};

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME,
    args: ['--no-sandbox', '--disable-gpu'] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForSelector('[data-testid="stAppViewContainer"]', { timeout: 30000 });
  await page.waitForTimeout(4500);
  if (query !== '-') {
    await page.locator('[data-testid="stSidebar"] button', { hasText: '历史任务' })
      .first().click();
    await page.waitForTimeout(3000);
    const input = page.locator('[class*="st-key-history_search"] input').first();
    await input.click(); await input.fill(query || 'audit-clean'); await input.press('Enter');
    await page.waitForTimeout(3000);
    await page.locator('button', { hasText: '打开任务' }).first().click();
    await page.waitForTimeout(3500);
  }
  const data = await page.evaluate(DUMP, root);
  console.log(JSON.stringify(data));
  await browser.close();
})().catch((e) => { console.error('FAILED', e.message); process.exit(1); });
