"""
@description 内存搜索索引，支持代码 / 简称 / 拼音（全拼 + 首字母）匹配打分。
"""

import logging
import threading
from typing import Literal

from scx_stock.schema.stock import StockInfo

logger = logging.getLogger(__name__)

SearchResultType = Literal["stock", "etf", "index"]


class SearchEntry:
    """索引条目。

    :param code: 证券代码。
    :param name: 简称。
    :param market: 市场。
    :param type: 类型 stock/etf。
    :param pinyin_full: 全拼小写。
    :param pinyin_initials: 首字母小写。
    """

    __slots__ = ("code", "name", "market", "type", "pinyin_full", "pinyin_initials")

    def __init__(
        self,
        code: str,
        name: str,
        market: str,
        type: str,
        pinyin_full: str,
        pinyin_initials: str,
    ) -> None:
        self.code = code
        self.name = name
        self.market = market
        self.type = type
        self.pinyin_full = pinyin_full
        self.pinyin_initials = pinyin_initials


class SearchIndex:
    """内存倒排/前缀索引，线程安全。

    一次构建、多次查询，由 Scheduler 每日全量重建。
    """

    def __init__(self) -> None:
        self._entries: list[SearchEntry] = []
        self._lock = threading.RLock()

    def rebuild(self, items: list[StockInfo]) -> int:
        """全量重建索引。

        :param items: StockInfo 列表（含 pinyin 字段）。
        :returns: 条目数。
        """
        entries: list[SearchEntry] = []
        for it in items:
            full, initials = self._split_pinyin(it.pinyin or "")
            entries.append(
                SearchEntry(
                    code=it.code,
                    name=it.name,
                    market=it.market,
                    type=it.type or "stock",
                    pinyin_full=full,
                    pinyin_initials=initials,
                )
            )

        with self._lock:
            self._entries = entries
            count = len(entries)
        logger.info("search index rebuilt: %d entries", count)
        return count

    def size(self) -> int:
        """返回当前索引条目数。

        :returns: 条目数。
        """
        with self._lock:
            return len(self._entries)

    def search(self, keyword: str, limit: int = 20) -> list[dict[str, object]]:
        """按关键词搜索，返回打分降序的结果。

        打分规则：
          - 代码精确命中：100
          - 代码前缀命中：80
          - 简称精确命中：60
          - 简称包含：40
          - 拼音全拼前缀命中：30
          - 拼音首字母前缀命中：20
        同分按代码升序。

        :param keyword: 关键词（代码/简称/拼音）。
        :param limit: 最大返回数。
        :returns: dict 列表，含 code/name/market/type/score。
        """
        kw = (keyword or "").strip().lower()
        if not kw:
            return []

        scored: list[tuple[int, SearchEntry]] = []
        with self._lock:
            entries = list(self._entries)

        for e in entries:
            score = self._score(e, kw)
            if score > 0:
                scored.append((score, e))

        # 排序：分数降序 → 代码升序
        scored.sort(key=lambda x: (-x[0], x[1].code))
        return [
            {
                "code": e.code,
                "name": e.name,
                "market": e.market,
                "type": e.type,
                "score": score,
            }
            for score, e in scored[:limit]
        ]

    @staticmethod
    def _split_pinyin(pinyin_field: str) -> tuple[str, str]:
        """拆分 'guizhoumaotai|gzmt' 为 (full, initials)。

        :param pinyin_field: 索引存的拼音串。
        :returns: (全拼, 首字母) 元组。
        """
        if "|" in pinyin_field:
            full, initials = pinyin_field.split("|", 1)
            return full, initials
        return pinyin_field, ""

    @staticmethod
    def _score(e: SearchEntry, kw: str) -> int:
        """计算单条目得分，不命中返回 0。

        :param e: 索引条目。
        :param kw: 已小写化的关键词。
        :returns: 得分。
        """
        code_l = e.code.lower()
        name_l = e.name.lower()

        if code_l == kw:
            return 100
        if code_l.startswith(kw):
            return 80
        if name_l == kw:
            return 60
        if name_l.startswith(kw):
            return 50
        if kw in name_l:
            return 40
        if e.pinyin_full and e.pinyin_full.startswith(kw):
            return 30
        if e.pinyin_initials and e.pinyin_initials.startswith(kw):
            return 20
        return 0


# 全局索引单例
_index: SearchIndex | None = None


def get_index() -> SearchIndex:
    """获取全局索引单例。

    :returns: SearchIndex 实例。
    """
    global _index
    if _index is None:
        _index = SearchIndex()
    return _index
