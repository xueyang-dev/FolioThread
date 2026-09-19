const PW = process.env.FOLIO_PLAYWRIGHT_CORE;
const CHROME = process.env.FOLIO_CHROME;
const { chromium } = require(PW);
const [url, dir] = process.argv.slice(2);

const MEASURE = () => {
  const q = (s) => document.querySelector(s);
  const rect = (el) => { if (!el) return null; const r = el.getBoundingClientRect();
    return { w: Math.round(r.width), h: Math.round(r.height) }; };
  const main = q('[data-testid="stMainBlockContainer"]');
  const head = q('[class*="st-key-la_head_row"]');
  const cols = head ? [...head.querySelectorAll('[data-testid="stColumn"]')] : [];
  const h1 = q('.tp-title h1');
  return {
    main: rect(main),
    mainOverflowX: main ? main.scrollWidth > main.clientWidth + 1 : null,
    list: rect(q('[class*="st-key-la_list"]')),
    inspector: rect(q('[class*="st-key-la_inspector"]')),
    advancedDisplay: (() => { const a = q('[class*="st-key-la_terms_adv_panel"]');
      return a ? getComputedStyle(a).display : null; })(),
    advancedBox: rect(q('[class*="st-key-la_terms_adv_panel"]')),
    headColumns: cols.map((c) => Math.round(c.getBoundingClientRect().width)),
    headContent: cols.map((c) => {
      const el = c.querySelector('.la-head');
      return el ? { cw: Math.round(el.clientWidth), sw: Math.round(el.scrollWidth),
                    lines: Math.round(el.getBoundingClientRect().height / 15) } : null;
    }),
    headLabels: cols.map((c) => c.innerText.trim()),
    listRowHeight: (() => { const r = q('[class*="st-key-la_row_"]');
      return r ? Math.round(r.getBoundingClientRect().height) : null; })(),
    headerBox: rect(q('.st-key-la_page_header')),
    titleFontSize: h1 ? getComputedStyle(h1).fontSize : null,
    tabs: [...document.querySelectorAll('[class*="st-key-library_tab"] button')]
      .map((b) => b.innerText.trim()),
    tooltipWidths: [...document.querySelectorAll('[data-testid="stTooltipContent"]')]
      .map((t) => Math.round(t.getBoundingClientRect().width)),
    tooltipMaxWidth: (() => { const t = q('[data-testid="stTooltipContent"]');
      return t ? getComputedStyle(t).maxWidth : null; })(),
    newTermBtn: rect(q('[class*="st-key-la_new_term"] button')),
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
  await page.waitForTimeout(4000);

  await page.locator('[data-testid="stSidebar"] button',
    { hasText: '术语与翻译记忆' }).first().click();
  await page.waitForTimeout(4000);

  const shot = async (name) => { await page.screenshot({ path: `${dir}/${name}`, fullPage: true }); };
  const say = async (label) => console.log(label, JSON.stringify(await page.evaluate(MEASURE)));

  await shot('01-terms-1440-default.png');
  await say('1440-default');

  // 高级筛选展开
  await page.locator('[class*="st-key-la_terms_adv_toggle"] button').first().click();
  await page.waitForTimeout(2200);
  await shot('02-terms-1440-filters-open.png');
  await say('1440-filters-open');
  await page.locator('[class*="st-key-la_terms_adv_toggle"] button').first().click();
  await page.waitForTimeout(2200);

  // 打开 Inspector（点击第一个术语名）
  const first = page.locator('[class*="st-key-la_open_"] button').first();
  if (await first.count()) {
    await first.click();
    await page.waitForTimeout(2600);
    await shot('03-terms-1440-inspector.png');
    await say('1440-inspector-open');
    const close = page.locator('[class*="st-key-la_close_inspector"] button').first();
    if (await close.count()) { await close.click(); await page.waitForTimeout(2200); }
    await say('1440-after-close');
  } else {
    console.log('1440-inspector: no term rows on this page');
  }

  // 1280 / 1024
  for (const width of [1280, 1024]) {
    await page.setViewportSize({ width, height: 800 });
    await page.waitForTimeout(1800);
    const firstRow = page.locator('[class*="st-key-la_open_"] button').first();
    if (await firstRow.count()) {
      await firstRow.click();
      await page.waitForTimeout(2400);
      await shot(`04-terms-${width}-inspector.png`);
      await say(`${width}-inspector-open`);
      const close = page.locator('[class*="st-key-la_close_inspector"] button').first();
      if (await close.count()) { await close.click(); await page.waitForTimeout(2000); }
      await shot(`05-terms-${width}-closed.png`);
      await say(`${width}-closed`);
    }
  }

  // 侧栏 tooltip 实测：hover「项目」入口
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.waitForTimeout(1500);
  const proj = page.locator('[class*="st-key-project_section_header"] button').first();
  if (await proj.count()) {
    await proj.hover();
    await page.waitForTimeout(1600);
    await page.screenshot({ path: `${dir}/06-sidebar-tooltip.png` });
    await say('1440-tooltip');
  }
  console.log('saved to', dir);
  await browser.close();
})().catch((e) => { console.error('FAILED', e.message); process.exit(1); });
