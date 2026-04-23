import jwt
import time
import json
import uuid
import asyncio
import logging
from typing import Optional

import httpx
from httpx_sse import aconnect_sse

from config import settings

logger = logging.getLogger(__name__)

MCP_TOOLS = {
    "imageSearchProduct": {
        "label": "图片搜索1688商品",
        "description": "通过图片链接搜索1688商品，返回商品ID、标题、图片、价格等",
        "params": ["imgUrl", "beginPage"],
    },
    "keywordSearchProduct": {
        "label": "关键词搜索1688商品",
        "description": "通过关键词搜索1688商品列表",
        "params": ["keyword", "beginPage"],
    },
    "productDetailQuery": {
        "label": "查询1688商品详情",
        "description": "通过商品ID查询详情，包含标题、图片列表、SKU信息等",
        "params": ["productId"],
    },
    "productRankQuery": {
        "label": "查询1688商品排行",
        "description": "通过目录ID和排行类型查询商品排行（complex综合/hot热门/goodPrice好价格）",
        "params": ["categoryId", "rankType"],
    },
    "relevantProductRecommend": {
        "label": "推荐1688相关商品",
        "description": "通过商品ID获取相关商品推荐列表",
        "params": ["productId", "beginPage"],
    },
    "topKeywordQuery": {
        "label": "查询1688 Top热搜词",
        "description": "通过目录ID查询1688热搜词列表",
        "params": ["categoryId"],
    },
}


def generate_jwt_token() -> str:
    """Generate JWT token for MCP authentication using AccessKey/SecretKey."""
    now = int(time.time())
    payload = {
        "iss": settings.AOXIA_ACCESS_KEY,
        "exp": now + 1800,   # 30 minutes
        "nbf": now - 5,      # effective 5 seconds ago
    }
    return jwt.encode(payload, settings.AOXIA_SECRET_KEY, algorithm="HS256")


def _get_sse_url() -> str:
    """Build the MCP SSE endpoint URL with JWT token."""
    token = generate_jwt_token()
    return f"{settings.AOXIA_MCP_BASE_URL}/sse?key={token}"


def _jsonrpc_request(method: str, params: Optional[dict] = None) -> dict:
    """Build a JSON-RPC 2.0 request."""
    req = {"jsonrpc": "2.0", "id": str(uuid.uuid4()), "method": method}
    if params is not None:
        req["params"] = params
    return req


async def call_mcp_tool(tool_name: str, arguments: dict) -> dict:
    """
    Connect to the Aoxia MCP server via SSE, call a tool, and return the result.

    MCP SSE protocol flow:
    1. GET /sse?key=JWT → SSE stream, receive 'endpoint' event with message URL
    2. POST initialize to message URL
    3. POST tools/call to message URL
    4. Collect result from SSE 'message' events
    """
    if tool_name not in MCP_TOOLS:
        raise ValueError(f"Unknown MCP tool: {tool_name}")

    sse_url = _get_sse_url()
    logger.info(f"[MCP] Calling tool={tool_name} args={arguments}")

    async with httpx.AsyncClient(timeout=httpx.Timeout(120, connect=15)) as client:
        message_endpoint = None
        result_data = None

        try:
            # Use stream() to check content-type without blocking on SSE
            async with client.stream("GET", sse_url, headers={"Accept": "text/event-stream"}) as resp:
                content_type = resp.headers.get("content-type", "")
                if "text/event-stream" not in content_type:
                    body = await resp.aread()
                    try:
                        err_body = json.loads(body)
                    except Exception:
                        err_body = body.decode(errors="replace")
                    logger.error(f"[MCP] SSE connect failed, got {content_type}: {err_body}")
                    return {"success": False, "error": f"MCP认证失败: {err_body}"}

            # Auth OK, now connect SSE for real
            async with aconnect_sse(client, "GET", sse_url, headers={"Accept": "text/event-stream"}) as event_source:
                # Step 1: Get the message endpoint from the first SSE event
                async for sse_event in event_source.aiter_sse():
                    if sse_event.event == "endpoint":
                        endpoint_path = sse_event.data.strip()
                        if endpoint_path.startswith("http"):
                            message_endpoint = endpoint_path
                        else:
                            base = settings.AOXIA_MCP_BASE_URL.rstrip("/")
                            message_endpoint = f"{base}{endpoint_path}" if endpoint_path.startswith("/") else f"{base}/{endpoint_path}"
                        logger.info(f"[MCP] Got message endpoint: {message_endpoint}")
                        break

                if not message_endpoint:
                    return {"success": False, "error": "未收到MCP message endpoint"}

                # Step 2: Send initialize
                init_req = _jsonrpc_request("initialize", {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "auto-public", "version": "1.0.0"},
                })
                init_resp = await client.post(message_endpoint, json=init_req)
                logger.info(f"[MCP] Initialize response status: {init_resp.status_code}")

                # Wait briefly for SSE events
                await asyncio.sleep(0.3)

                # Step 3: Send initialized notification
                notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
                await client.post(message_endpoint, json=notif)

                # Step 4: Call the tool
                call_req = _jsonrpc_request("tools/call", {
                    "name": tool_name,
                    "arguments": arguments,
                })
                call_id = call_req["id"]
                call_resp = await client.post(message_endpoint, json=call_req)
                logger.info(f"[MCP] tools/call response status: {call_resp.status_code}")

                # Step 5: Collect result from SSE stream
                async for sse_event in event_source.aiter_sse():
                    if sse_event.event == "message":
                        try:
                            msg = json.loads(sse_event.data)
                            if msg.get("id") == call_id:
                                result_data = msg
                                break
                        except json.JSONDecodeError:
                            continue

        except httpx.ReadTimeout:
            return {"success": False, "error": "MCP服务响应超时"}
        except Exception as e:
            logger.error(f"[MCP] Tool call failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    # Parse result
    if result_data is None:
        return {"success": False, "error": "未收到MCP工具调用结果"}

    if "error" in result_data:
        err = result_data["error"]
        return {"success": False, "error": err.get("message", str(err))}

    result = result_data.get("result", {})
    contents = result.get("content", [])

    parsed = []
    for block in contents:
        text = block.get("text", "")
        try:
            parsed.append(json.loads(text))
        except (json.JSONDecodeError, TypeError):
            parsed.append(text)

    return {"success": True, "data": parsed[0] if len(parsed) == 1 else parsed}


async def list_mcp_tools() -> list:
    """Connect to MCP server and list all available tools (for debugging)."""
    sse_url = _get_sse_url()

    async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=15)) as client:
        try:
            # Pre-flight: stream check content-type
            async with client.stream("GET", sse_url, headers={"Accept": "text/event-stream"}) as resp:
                content_type = resp.headers.get("content-type", "")
                if "text/event-stream" not in content_type:
                    body = await resp.aread()
                    try:
                        err_body = json.loads(body)
                    except Exception:
                        err_body = body.decode(errors="replace")
                    logger.error(f"[MCP] list_tools SSE failed: {err_body}")
                    return [{"error": f"MCP认证失败: {err_body}"}]

            async with aconnect_sse(client, "GET", sse_url, headers={"Accept": "text/event-stream"}) as event_source:
                message_endpoint = None
                async for sse_event in event_source.aiter_sse():
                    if sse_event.event == "endpoint":
                        endpoint_path = sse_event.data.strip()
                        if endpoint_path.startswith("http"):
                            message_endpoint = endpoint_path
                        else:
                            base = settings.AOXIA_MCP_BASE_URL.rstrip("/")
                            message_endpoint = f"{base}{endpoint_path}" if endpoint_path.startswith("/") else f"{base}/{endpoint_path}"
                        break

                if not message_endpoint:
                    return []

                # Initialize
                init_req = _jsonrpc_request("initialize", {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "auto-public", "version": "1.0.0"},
                })
                await client.post(message_endpoint, json=init_req)
                await asyncio.sleep(0.3)

                notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
                await client.post(message_endpoint, json=notif)

                # List tools
                list_req = _jsonrpc_request("tools/list", {})
                list_id = list_req["id"]
                await client.post(message_endpoint, json=list_req)

                async for sse_event in event_source.aiter_sse():
                    if sse_event.event == "message":
                        try:
                            msg = json.loads(sse_event.data)
                            if msg.get("id") == list_id:
                                tools = msg.get("result", {}).get("tools", [])
                                return [
                                    {"name": t["name"], "description": t.get("description", ""), "inputSchema": t.get("inputSchema", {})}
                                    for t in tools
                                ]
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            logger.error(f"[MCP] list_tools failed: {e}", exc_info=True)
            return []
    return []
