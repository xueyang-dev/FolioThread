const PW = process.env.FOLIO_PLAYWRIGHT_CORE;
const CHROME = process.env.FOLIO_CHROME;
const { chromium } = require(PW);
const [url, out] = process.argv.slice(2);

const MEASURE = () => {
  const q = (s) => document.querySelector(s);
  const r = (el) => { if (!el) return null; const b = el.getBoundingClientRect();
    return { top: +b.top.toFixed(1), bottom: +b.bottom.toFixed(1), h: +b.height.toFixed(1) }; };
  const mb = (el) => (el ? getComputedStyle(el).marginBottom : null);

  const headRow = q('[class*="st-key-la_head_row"]');
  const headEl = q('.la-head');
  const list = q('[class*="st-key-la_list"]');
  const row = q('[class*="st-key-la_row_"]');
  const rowHead = row ? row.querySelector('.la-term') || row.querySelector('[class*="la-"]') : null;

  // 表头线位置
  const bw = headRow ? parseFloat(getComputedStyle(headRow).borderBottomWidth) : 0;
  const hr = r(headRow);
  const lineY = hr ? +(hr.bottom - bw / 2).toFixed(1) : null;
  const ht = r(headEl);

  // 行内：容器高度 vs 内容高度（判断行是否也被 -16px 压塌）
  const rr = r(row);
  const rowMd = row ? row.querySelector('[data-testid="stMarkdownContainer"]') : null;
  const rowContent = r(rowHead);

  return {
    headRow: hr,
    headRowPadBottom: headRow ? getComputedStyle(headRow).paddingBottom : null,
    headText: ht,
    headMdMarginBottom: headEl ? mb(headEl.parentElement) : null,
    lineY,
    lineVsTextBottom: (lineY != null && ht) ? +(lineY - ht.bottom).toFixed(1) : null,
    list: r(list),
    // 表头文字底部 vs 列表容器顶部：>0 说明表头文字压在列表/首行上
    headTextBottomVsListTop: (ht && r(list)) ? +(ht.bottom - r(list).top).toFixed(1) : null,
    firstRow: rr,
    firstRowMdMarginBottom: mb(rowMd),
    firstRowCell: rowContent,
    // 行高 47 vs 内容高度：判断行有没有被压塌
    firstRowHeightVsContent: (rr && rowContent) ? +(rr.h - rowContent.h).toFixed(1) : null,
    rowCellMarginBottom: rowHead ? mb(rowHead.parentElement) : null,
  };
};

(async () => {
  const browser = await chromium.launch({ executablePath: CHROME,
    args: ['--no-sandbox', '--disable-gpu'] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2 });
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForSelector('[data-testid="stAppViewContainer"]', { timeout: 30000 });
  await page.waitForTimeout(4000);
  await page.locator('[data-testid="stSidebar"] button',
    { hasText: '术语与翻译记忆' }).first().click();
  await page.waitForTimeout(4500);

  console.log(JSON.stringify(await page.evaluate(MEASURE), null, 1));

  // 截表头 + 前两行，放大看线是否切字
  const headRow = page.locator('[class*="st-key-la_head_row"]').first();
  const box = await headRow.boundingBox();
  if (box && out) {
    await page.screenshot({ path: out,
      clip: { x: box.x - 10, y: box.y - 26, width: box.width + 20, height: box.height + 150 } });
  }
  await browser.close();
})().catch((e) => { console.error('FAILED', e.message); process.exit(1); });
