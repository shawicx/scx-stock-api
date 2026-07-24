"""
@description 拼音与搜索索引单元测试，不依赖外网与 DB。
"""

from scx_stock.schema.stock import StockInfo
from scx_stock.search.index import SearchIndex
from scx_stock.search.pinyin import make_pinyin_for_search, to_pinyin


def test_to_pinyin_chinese():
    """中文转全拼 + 首字母。"""
    full, initials = to_pinyin("贵州茅台")
    assert full == "guizhoumaotai"
    assert initials == "gzmt"


def test_make_pinyin_for_search_format():
    """索引串格式为 full|initials。"""
    assert make_pinyin_for_search("贵州茅台") == "guizhoumaotai|gzmt"
    assert make_pinyin_for_search("") == ""


def test_index_code_exact_beats_prefix():
    """代码精确命中得分高于前缀。"""
    idx = SearchIndex()
    idx.rebuild(
        [
            StockInfo(code="600519", name="贵州茅台", market="上证", pinyin="guizhoumaotai|gzmt"),
            StockInfo(code="600518", name="A", market="上证", pinyin=""),
        ]
    )
    results = idx.search("600519")
    assert len(results) == 1
    assert results[0]["code"] == "600519"
    assert results[0]["score"] == 100


def test_index_name_contains():
    """简称包含命中。"""
    idx = SearchIndex()
    idx.rebuild(
        [StockInfo(code="600519", name="贵州茅台", market="上证", pinyin="guizhoumaotai|gzmt")]
    )
    assert idx.search("茅台")[0]["code"] == "600519"


def test_index_pinyin_initials():
    """拼音首字母匹配。"""
    idx = SearchIndex()
    idx.rebuild(
        [StockInfo(code="600519", name="贵州茅台", market="上证", pinyin="guizhoumaotai|gzmt")]
    )
    assert idx.search("gzmt")[0]["code"] == "600519"
    assert idx.search("gzm")[0]["code"] == "600519"


def test_index_pinyin_full():
    """拼音全拼前缀匹配。"""
    idx = SearchIndex()
    idx.rebuild(
        [StockInfo(code="600519", name="贵州茅台", market="上证", pinyin="guizhoumaotai|gzmt")]
    )
    assert idx.search("guizhou")[0]["code"] == "600519"


def test_index_limit_and_empty():
    """limit 截断与空关键词。"""
    idx = SearchIndex()
    idx.rebuild(
        [
            StockInfo(code="600519", name="贵州茅台", market="上证", pinyin="guizhoumaotai|gzmt"),
            StockInfo(code="000858", name="五粮液", market="深证", pinyin="wuliangye|wly"),
        ]
    )
    assert len(idx.search("6", limit=1)) == 1
    assert idx.search("") == []
    assert idx.search("不存在的关键词") == []


def test_index_ranking_order():
    """多结果按分数降序、同分按代码升序。"""
    idx = SearchIndex()
    idx.rebuild(
        [
            StockInfo(code="600518", name="A科技", market="上证", pinyin="akeji|ak"),
            StockInfo(code="600519", name="A科技", market="上证", pinyin="akeji|ak"),
            StockInfo(code="000001", name="平安银行", market="深证", pinyin="pinganyinhang|payh"),
        ]
    )
    # 搜索 "60051" → 两条代码前缀命中（80 分），按代码升序
    results = idx.search("60051")
    assert results[0]["code"] == "600518"
    assert results[1]["code"] == "600519"
