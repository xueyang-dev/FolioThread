/* 24-minimal-workspace · DOM 骨架探测（一次性）
 * 用途：确认 Streamlit 组件的真实结构与 computed 值，再据此写 CSS 选择器。
 *   node probe3.js http://127.0.0.1:8501 '<selector>' [job-query] [open|closed]
 */
const { chromium } = require(process.env.FOLIO_PLAYWRIGHT_CORE);
const CHROME = process.env.FOLIO_CHROME;
const [url, sel, query, expanded] = process.argv.slice(2);

function dump(s, expand) {
  const root = document.querySelector(s);
  if (!root) return 'NOT FOUND ' + s;
  if (expand === 'open') {
    const head = root.querySelector('[data-testid="stExpander"] > div:first-child')
      || root.querySelector('[data-testid="stExpander"] summary');
    if (head) head.click();
  }
  const skel = [];
  const walk = (el, d) => {
    if (d > 7) return;
    const r = el.getBoundingClientRect();
    const cs = getComputedStyle(el);
    const cls = [...el.classList].join(' ');
    skel.push('  '.repeat(d) + '<' + el.tagName.toLowerCase()
      + (el.getAttribute('data-testid') ? ' data-testid=' + el.getAttribute('data-testid') : '')
      + (cls ? ' class="' + cls.slice(0, 70) + '"' : '')
      + '> h=' + Math.round(r.height) + ' w=' + Math.round(r.width)
      + ' top=' + Math.round(r.top)
      + ' minh=' + cs.minHeight
      + ' pad=' + cs.paddingTop + '/' + cs.paddingBottom
      + ' border=' + cs.borderTopWidth);
    for (const c of el.children) walk(c, d + 1);
  };
  walk(root, 0);
  return skel.join('\n');
}

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME,
    args: ['--no-sandbox', '--disable-gpu'] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForSelector('[data-testid="stAppViewContainer"]', { timeout: 30000 });
  await page.waitForTimeout(4500);
  await page.locator('[data-testid="stSidebar"] button', { hasText: '历史任务' })
    .first().click();
  await page.waitForTimeout(3000);
  const input = page.locator('[class*="st-key-history_search"] input').first();
  await input.click(); await input.fill(query || 'audit-clean'); await input.press('Enter');
  await page.waitForTimeout(3000);
  await page.locator('button', { hasText: '打开任务' }).first().click();
  await page.waitForTimeout(3500);
  console.log(await page.evaluate(
    ({ s, e }) => window.__dump(s, e),
    { s: sel, e: expanded || 'closed' })
    .catch(async () => {
      await page.evaluate(`window.__dump = ${dump.toString()}`);
      return page.evaluate(({ s, e }) => window.__dump(s, e),
        { s: sel, e: expanded || 'closed' });
    }));
  await browser.close();
})().catch((e) => { console.error('FAILED', e.message); process.exit(1); });
