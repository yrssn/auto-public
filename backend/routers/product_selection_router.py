import traceback
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional

from auth import get_current_user
from models import User
from services.mcp_service import call_mcp_tool, list_mcp_tools, MCP_TOOLS

router = APIRouter(prefix="/api/product-selection", tags=["选品"])


@router.get("/tools")
async def get_available_tools(current_user: User = Depends(get_current_user)):
    """Return the list of available MCP tools with metadata."""
    return {"tools": MCP_TOOLS}


@router.get("/tools/live")
async def get_live_tools(current_user: User = Depends(get_current_user)):
    """Connect to MCP server and list actual available tools (debug endpoint)."""
    try:
        tools = await list_mcp_tools()
        return {"ok": True, "tools": tools}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/image")
async def search_by_image(
    img_url: str = Query(..., description="图片链接"),
    page: int = Query(1, ge=1, le=10, description="页码，1-10"),
    current_user: User = Depends(get_current_user),
):
    """图片搜索1688商品"""
    result = await call_mcp_tool("imageSearchProduct", {
        "imgUrl": img_url,
        "beginPage": page,
    })
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "MCP调用失败"))
    return result


@router.get("/search/keyword")
async def search_by_keyword(
    keyword: str = Query(..., description="搜索关键词"),
    page: int = Query(1, ge=1, le=10, description="页码，1-10"),
    current_user: User = Depends(get_current_user),
):
    """关键词搜索1688商品"""
    result = await call_mcp_tool("keywordSearchProduct", {
        "keyword": keyword,
        "beginPage": page,
    })
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "MCP调用失败"))
    return result


@router.get("/product/{product_id}")
async def get_product_detail(
    product_id: str,
    current_user: User = Depends(get_current_user),
):
    """查询1688商品详情"""
    result = await call_mcp_tool("productDetailQuery", {
        "productId": product_id,
    })
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "MCP调用失败"))
    return result


@router.get("/rank")
async def get_product_rank(
    category_id: str = Query(..., description="1688目录ID"),
    rank_type: str = Query("complex", description="排行类型: complex/hot/goodPrice"),
    current_user: User = Depends(get_current_user),
):
    """查询1688商品排行"""
    if rank_type not in ("complex", "hot", "goodPrice"):
        raise HTTPException(status_code=400, detail="rank_type 必须为 complex/hot/goodPrice")
    result = await call_mcp_tool("productRankQuery", {
        "categoryId": category_id,
        "rankType": rank_type,
    })
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "MCP调用失败"))
    return result


@router.get("/recommend/{product_id}")
async def get_product_recommend(
    product_id: str,
    page: int = Query(1, ge=1, le=10, description="页码，1-10"),
    current_user: User = Depends(get_current_user),
):
    """推荐1688相关商品"""
    result = await call_mcp_tool("relevantProductRecommend", {
        "productId": product_id,
        "beginPage": page,
    })
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "MCP调用失败"))
    return result


@router.get("/top-keywords")
async def get_top_keywords(
    category_id: str = Query(..., description="1688目录ID"),
    current_user: User = Depends(get_current_user),
):
    """查询1688 Top热搜词"""
    result = await call_mcp_tool("topKeywordQuery", {
        "categoryId": category_id,
    })
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "MCP调用失败"))
    return result
