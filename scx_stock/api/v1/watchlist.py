"""
@description 关注列表 API：增删改查，持久化到 DB watchlist 表。

替代前端 localStorage，定时任务分析的数据来源。
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

from scx_stock.schema.common import ApiResponse, ok
from scx_stock.storage import repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/watchlist", tags=["关注列表"])


class WatchlistItem(BaseModel):
    """关注列表条目。"""

    code: str = Field(..., description="证券代码")
    name: str = Field("", description="简称")
    sort_order: int = Field(0, description="排序序号")


class WatchlistAddRequest(BaseModel):
    """添加关注请求体。"""

    code: str = Field(..., description="证券代码")
    name: str = Field("", description="简称")


class WatchlistReplaceRequest(BaseModel):
    """整体替换关注列表请求体。"""

    items: list[WatchlistItem] = Field(default_factory=list, description="关注列表")


@router.get("", response_model=ApiResponse, summary="获取关注列表")
async def get_watchlist() -> dict[str, object]:
    """返回全部关注列表，按 sort_order 升序。

    :returns: 统一响应，data 为 WatchlistItem 列表。
    """
    models = await repo.list_watchlist()
    items = [
        {"code": m.code, "name": m.name, "sort_order": m.sort_order}
        for m in models
    ]
    return ok(items)


@router.post("", response_model=ApiResponse, summary="添加关注")
async def add_to_watchlist(body: WatchlistAddRequest) -> dict[str, object]:
    """添加关注标的。已存在则更新名称。

    :param body: 添加请求。
    :returns: 统一响应。
    """
    # 从 stock 表补全名称（若前端未提供）
    name = body.name
    if not name:
        try:
            all_stocks = await repo.load_all_stocks()
            for s in all_stocks:
                if s.code == body.code:
                    name = s.name
                    break
        except Exception as e:  # noqa: BLE001
            logger.warning("补全名称失败 %s: %s", body.code, e)

    # sort_order 取当前列表长度
    existing = await repo.list_watchlist()
    sort_order = len(existing)
    await repo.add_watchlist(body.code, name=name, sort_order=sort_order)
    logger.info("添加关注: %s %s", body.code, name)
    return ok({"code": body.code, "name": name})


@router.delete("/{code}", response_model=ApiResponse, summary="移除关注")
async def remove_from_watchlist(code: str) -> dict[str, object]:
    """移除关注标的。

    :param code: 证券代码。
    :returns: 统一响应。
    """
    deleted = await repo.remove_watchlist(code)
    logger.info("移除关注: %s (删除 %d 条)", code, deleted)
    return ok({"deleted": deleted})


@router.put("", response_model=ApiResponse, summary="整体替换关注列表")
async def replace_watchlist(body: WatchlistReplaceRequest) -> dict[str, object]:
    """整体替换关注列表（先清空再批量写入）。

    供前端批量同步使用。

    :param body: 替换请求。
    :returns: 统一响应。
    """
    items = [
        {"code": it.code, "name": it.name, "sort_order": idx}
        for idx, it in enumerate(body.items)
    ]
    count = await repo.replace_watchlist(items)
    logger.info("替换关注列表: %d 条", count)
    return ok({"count": count})
