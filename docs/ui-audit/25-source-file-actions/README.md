# 25 · 新建任务「输入文件」卡：操作按钮回到右侧、与文件名同高

上传文件后，卡片左下角会多出一行「更换 / 删除」图标按钮：既把卡片从 **82px 撑到 150px**，
也和文件名、`PDF · 10.7 MB · 已上传，等待解析` 这一行不在同一水平线上。
本轮把两个按钮贴到卡片右缘、垂直居中，与文件名 / 元信息**同高**，卡片回到单行高度。

## 结论

| | 之前 | 之后 |
| --- | --- | --- |
| 操作区位置 | 卡片左下角（普通文档流） | 卡片右缘，`right: 12px`，垂直居中 |
| 卡片高度 | 150px（112px 文件块 + 36px 按钮行） | **82px** |
| 按钮与文件名 | 不同高（中心差 ≈33px） | 同高（中心差 ≤1px） |
| 「已就绪」徽标 | 绝对定位在右上角 | 跟到元信息行内（`PDF · 5 KB · 已就绪`） |

**只改了 `app.py` 的 CSS 与 `_source_file_html()` 的徽标位置** —— 上传 / 解析 / 移除的
业务逻辑、session state、按钮 key（`replace_source` / `remove_source`）全部未动。

## 复现步骤

```bash
# 1) 起应用（隔离 CWD，避免污染真实 outputs/）
mkdir -p /tmp/folio-verify && cd /tmp/folio-verify
NO_PROXY='127.0.0.1,localhost' env -u PYTHONPATH \
  /path/to/Folith/venv/bin/streamlit run /path/to/Folith/app.py \
  --server.port 8599 --server.headless true

# 2) 打开「新建任务」并上传一个 PDF，然后量几何 / 截图（本机 playwright-core + Chrome）
```

> 改的是 CSS，**热重载不可靠** —— 截不到新版式时先重启 server 再下结论。

## 截图核对点

- `01-card-before.png`：两个图标按钮在卡片**左下角**，卡片明显偏高；
- `02-task-page-after.png`（1080 视口整页）：按钮在卡片右缘、与文件名同一高度；
- `03-card-after.png`：`更换文件` 与 `删除` 两个 36×36 图标按钮右对齐，卡片 82px 单行；
- `04-card-parsed-after.png`：解析完成后状态收成一行 `PDF · 5 KB · 已就绪`（绿色），
  右上角不再有会和按钮重叠的绝对定位徽标；
- `05-card-760-after.png`：窄屏（760px）下按钮仍保持一行，不上下堆叠。

浏览器实测（Chrome，三档宽度）：

| 视口 | 卡片 | 按钮 | 文件名与按钮 |
| --- | --- | --- | --- |
| 1080 | 780×82 | 36×36 @ y=482 | 零重叠 |
| 900 | 600×82 | 36×36 @ y=482 | 零重叠 |
| 760 | 496×82 | 36×36 @ y=578 | 零重叠 |

## 三个容易踩的坑（都记在案）

1. **`st.container` 的容器子节点也被 `stLayoutWrapper` 包住**，所以
   `.st-key-source_file_card > [data-testid="stElementContainer"]:has(.st-key-source_file_actions)`
   这条 `>` 选择器**一个都不命中** —— 规则存在、格式正确、devtools 里能看到，
   就是永远不生效，按钮因此退回普通文档流。现在两层包装都写。
2. **`stVerticalBlock` 自带 `height: 100%`**：wrapper 设了 `align-items: center` 后子块仍被
   flex-grow 撑满 80px、内容贴顶。要补 `flex: 0 0 auto !important`（内层再加
   `justify-content: center` 双保险）才真正垂直居中。
3. **全局窄屏规则会盖掉作用域规则**：`app.py` 里
   `@media (max-width: 767px) [data-testid="stMainBlockContainer"]:not(:has(.tp-workspace-shell)) [data-testid="stHorizontalBlock"] { display:block !important }`
   的特异性是 (0,3,0)，比作用域选择器高，两边又都是 `!important` —— 窄屏下两个按钮会
   上下堆叠。补一条同特异性的窄屏例外即可；注意此时 computed 的 `flex-direction`
   仍可能是 `row`，真正作恶的是 `display: block`。

回归：`tests/app_boot_test.py`（上传 / 解析中 / 已就绪三态 + 移除流程）。
