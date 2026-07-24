"""
@description 拼音转换工具，生成全拼与首字母，用于搜索索引。
"""

from pypinyin import Style, pinyin


def to_pinyin(text: str) -> tuple[str, str]:
    """把中文文本转为（全拼, 首字母小写）。

    非中文字符原样保留（去除空格）。

    :param text: 原始文本，如 "贵州茅台"。
    :returns: (full, initials) 元组，如 ("guizhoumaotai", "gzmt")。

    :example
    >>> to_pinyin("贵州茅台")
    ('guizhoumaotai', 'gzmt')
    >>> to_pinyin("沪深300ETF")
    ('husanlingyiETF'.lower(), 'h300ETF'.lower())
    """
    if not text:
        return "", ""

    full = pinyin(text, style=Style.NORMAL, errors=lambda x: x)
    initials_py = pinyin(text, style=Style.FIRST_LETTER, errors=lambda x: x)

    full_str = "".join("".join(item) for item in full).replace(" ", "")
    initials_str = "".join("".join(item) for item in initials_py).replace(" ", "")

    return full_str.lower(), initials_str.lower()


def make_pinyin_for_search(name: str) -> str:
    """生成索引用拼音串（全拼 + 首字母用 '|' 分隔），便于单字段索引。

    :param name: 中文名称。
    :returns: 形如 "guizhoumaotai|gzmt" 的串，无拼音时返回空串。

    :example
    >>> make_pinyin_for_search("贵州茅台")
    'guizhoumaotai|gzmt'
    """
    full, initials = to_pinyin(name)
    if not full and not initials:
        return ""
    return f"{full}|{initials}"
