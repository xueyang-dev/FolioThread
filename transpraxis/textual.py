"""文本的 Unicode 语义判定（语言无关）。

只放"这一行是不是文字"这类**与具体语言无关**的判定，供核心层与各领域模块
共用：同一份判定如果在多处各写一遍，就会出现"这里认西里尔、那里不认"的漂移，
而漂移的方向恰好是"真实语言被判成装饰行、原样保留、标成已审校"——静默错误。
"""
from __future__ import annotations

import unicodedata


def has_textual_content(text) -> bool:
    """段落是否含正文内容：任何 Unicode 字母（L*）或数字（N*）即算正文。

    刻意**不**枚举语言区间（拉丁 / 汉字 / 西里尔 / 谚文 / 阿拉伯 …）：按脚本
    列区间永远会漏掉下一个语言，而"这一行是不是文字"本身就是一个 Unicode
    类别问题，不是一个语言清单问题。纯标点、分隔符与装饰符号（Po / Pd / Sm /
    So / Cf …）不是正文，仍然按装饰行原样保留。
    """
    for character in str(text or ""):
        if unicodedata.category(character)[0] in ("L", "N"):
            return True
    return False


def normalize_language(value) -> str:
    """语言标识的比较键（NFKC + 去空白 + casefold）；无法解析时返回空串。

    只吸收"同一种语言写法不同"的排版差异（`Français` / `français` /
    `FrançAIS`），**不做语言识别**：证明不了的语言一律保持空，绝不猜——
    猜错的代价是把一条已审校的错译文复用到另一种语言的任务里。
    """
    if value is None:
        return ""
    return unicodedata.normalize("NFKC", str(value)).strip().casefold()
