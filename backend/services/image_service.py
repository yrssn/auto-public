import asyncio
import base64
import logging
import httpx
from typing import Optional, List

logger = logging.getLogger(__name__)




def _encode_image(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _get_image_mime(image_path: str) -> str:
    ext = image_path.rsplit(".", 1)[-1].lower()
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp"}
    return mime_map.get(ext, "image/png")




def _encode_image_or_url(path: str) -> str:
    """Encode local file as data URL or return remote URL as-is."""
    if path.startswith("http"):
        return path
    img_b64 = _encode_image(path)
    img_mime = _get_image_mime(path)
    return f"data:{img_mime};base64,{img_b64}"


async def call_image_api(
    prompt: str,
    api_key: str,
    base_url: str,
    model_name: str,
    size: str = "2048x2048",
    reference_image_paths: Optional[List[str]] = None,
    n: int = 1,
) -> str:
    """Call OpenAI-compatible image generation API. Returns image URL(s).
    Supports optional reference images for image-to-image generation."""
    url = f"{base_url.rstrip('/')}/images/generations"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {"model": model_name, "prompt": prompt, "n": n, "size": size, "response_format": "url"}

    # Include reference images for img2img if available
    # Always send as array to match standard: "image": ["string", ...]
    if reference_image_paths:
        try:
            body["image"] = [_encode_image_or_url(p) for p in reference_image_paths]
            logger.info(f"[ImageAPI] img2img mode, {len(reference_image_paths)} ref image(s), model={model_name}")
        except Exception as e:
            logger.warning(f"[ImageAPI] Failed to encode ref images, text2img fallback: {e}")

    logger.info(f"[ImageAPI] Request: url={url}, model={model_name}, has_image={bool(reference_image_paths)}, size={size}")

    try:
        async with httpx.AsyncClient(timeout=600) as client:
            resp = await client.post(url, json=body, headers=headers)
    except httpx.RemoteProtocolError as e:
        raise ValueError(f"服务端断开连接（可能是请求体过大或模型不支持图片输入）: {e}")
    except httpx.ReadTimeout:
        raise ValueError(f"请求超时（600秒），模型处理时间过长")
    except httpx.ConnectError as e:
        raise ValueError(f"连接失败，请检查 base_url 是否正确: {e}")
    except httpx.HTTPStatusError as e:
        raise ValueError(f"HTTP 错误: {e}")

    logger.info(f"[ImageAPI] Response status={resp.status_code}")

    if resp.status_code >= 400:
        try:
            err_detail = resp.json()
        except Exception:
            err_detail = resp.text
        raise ValueError(f"API {resp.status_code}: {err_detail}")
    data = resp.json()
    # OpenAI format: {"data": [{"url": "..."}]}
    images = data.get("data", [])
    if not images:
        raise ValueError(f"图片生成 API 未返回图片数据, 响应: {data}")
    if n == 1:
        return images[0].get("url") or images[0].get("b64_json")
    # Return list of URLs for n > 1
    return [img.get("url") or img.get("b64_json") for img in images]


async def _generate_one(prompt: str, cfg: dict, image_paths: Optional[List[str]], n: int = 1) -> list:
    """Generate image(s) with a single model, return list of result dicts."""
    name = cfg.get("config_name", cfg["model_name"])
    try:
        result = await call_image_api(
            prompt=prompt,
            api_key=cfg["api_key"],
            base_url=cfg["base_url"],
            model_name=cfg["model_name"],
            reference_image_paths=image_paths if image_paths else None,
            n=n,
        )
        if isinstance(result, list):
            return [{"model_name": name, "image_url": url, "error": None} for url in result]
        return [{"model_name": name, "image_url": result, "error": None}]
    except Exception as e:
        return [{"model_name": name, "image_url": None, "error": str(e)}]


async def generate_image_stream(
    prompt: str,
    product_path: Optional[str],
    image_configs: Optional[List[dict]] = None,
    n: int = 1,
):
    """
    Async generator that yields status dicts during image generation.
    image_configs: list of {"api_key", "base_url", "model_name", "config_name"} for image generation
    product_path: product image path (for img2img)
    """
    result = {"optimized_prompt": None, "image_url": None, "image_results": []}

    image_paths = [product_path] if product_path else None

    # Generate images (supports multiple models in parallel)
    if image_configs:
        model_names = [c.get("config_name", c["model_name"]) for c in image_configs]
        yield {"step": "generating", "message": f"正在用 {len(image_configs)} 个模型并行生成图片: {', '.join(model_names)}"}

        # Run all models in parallel (pass product image for img2img)
        tasks = [_generate_one(prompt, cfg, image_paths, n=n) for cfg in image_configs]
        nested_results = await asyncio.gather(*tasks)
        # Flatten: each model may return multiple images
        image_results = [r for model_results in nested_results for r in model_results]
        result["image_results"] = image_results

        # Set first successful URL for backward compat
        first_ok = next((r for r in image_results if r.get("image_url")), None)
        if first_ok:
            result["image_url"] = first_ok["image_url"]

        ok_count = sum(1 for r in image_results if r.get("image_url"))
        fail_count = len(image_results) - ok_count
        msg = f"图片生成完成: {ok_count} 成功"
        if fail_count:
            msg += f", {fail_count} 失败"
        yield {"step": "image_done", "message": msg}
    else:
        result["error"] = "未配置图片生成模型"
        yield {"step": "no_image_model", "message": "未配置图片生成模型"}

    yield {"step": "done", "message": "完成", "result": result}
