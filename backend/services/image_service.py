import asyncio
import base64
import json
import logging
import os
import time
import uuid
import httpx
from typing import Optional, List

logger = logging.getLogger(__name__)

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Persist every relay image API call (request params + response info) to a log
# file so generations can be traced back later. Module loggers don't emit by
# default under uvicorn, so attach our own file + console handlers here.
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
IMAGE_API_LOG = os.path.join(LOG_DIR, "image_api.log")

if not logger.handlers:
    logger.setLevel(logging.INFO)
    _fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    _file_handler = logging.FileHandler(IMAGE_API_LOG, encoding="utf-8")
    _file_handler.setFormatter(_fmt)
    _stream_handler = logging.StreamHandler()
    _stream_handler.setFormatter(_fmt)
    logger.addHandler(_file_handler)
    logger.addHandler(_stream_handler)
    logger.propagate = False

# Instruction appended to the prompt to stop chat-style relay image models
# (e.g. gpt-image-* proxies) from packing several variations into one collage.
SINGLE_IMAGE_HINT = (
    " Generate exactly one single standalone image. "
    "Do not produce a grid, collage, montage, contact sheet, "
    "or multiple panels/variations within one image."
)

# Upper bound on images generated per model in one request. Each image is an
# independent outbound HTTP call, so cap the user-controlled n to avoid spawning
# an unbounded number of concurrent requests (the UI only offers 1/2/4).
MAX_IMAGES_PER_REQUEST = 10




def _encode_image(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _get_image_mime(image_path: str) -> str:
    ext = image_path.rsplit(".", 1)[-1].lower()
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp"}
    return mime_map.get(ext, "image/png")




def _encode_image_or_url(path: str, max_size: int = 1024) -> str:
    """Encode local file as data URL or return remote URL as-is.
    Local images are resized to max_size pixels on longest side to reduce payload."""
    if path.startswith("http"):
        return path
    # Try to compress image before encoding
    try:
        from PIL import Image
        import io
        img = Image.open(path)
        # Convert RGBA to RGB for JPEG
        if img.mode == "RGBA":
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")
        # Resize if too large
        w, h = img.size
        if max(w, h) > max_size:
            ratio = max_size / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
            logger.info(f"[ImageAPI] Resized {path} from {w}x{h} to {img.size}")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        img_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/jpeg;base64,{img_b64}"
    except ImportError:
        # Pillow not available, fall back to raw base64
        img_b64 = _encode_image(path)
        img_mime = _get_image_mime(path)
        return f"data:{img_mime};base64,{img_b64}"
    except Exception as e:
        logger.warning(f"[ImageAPI] Image compression failed, using raw: {e}")
        img_b64 = _encode_image(path)
        img_mime = _get_image_mime(path)
        return f"data:{img_mime};base64,{img_b64}"


async def call_image_api(
    prompt: str,
    api_key: str,
    base_url: str,
    model_name: str,
    size: str = "1024x1024",
    reference_image_paths: Optional[List[str]] = None,
    single_image_hint: bool = True,
) -> str:
    """Call OpenAI-compatible image generation API. Returns image URL(s).
    Supports optional reference images for image-to-image generation.

    Always request a single image per call (n=1). Relay/proxy image models are
    chat-style backends that ignore n>1 and instead return ONE collage/nine-grid
    image; callers that want multiple images should issue multiple calls."""
    req_id = uuid.uuid4().hex[:8]
    url = f"{base_url.rstrip('/')}/images/generations"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    final_prompt = prompt
    if single_image_hint and SINGLE_IMAGE_HINT.strip() not in prompt:
        final_prompt = f"{prompt}{SINGLE_IMAGE_HINT}"
    body = {"model": model_name, "prompt": final_prompt, "n": 1, "size": size}
    # Note: do NOT send response_format - many middleman APIs don't support it and may hang

    # Include reference images for img2img if available
    # Always send as array to match standard: "image": ["string", ...]
    if reference_image_paths:
        try:
            body["image"] = [_encode_image_or_url(p) for p in reference_image_paths]
            logger.info(f"[ImageAPI][{req_id}] img2img mode, {len(reference_image_paths)} ref image(s), model={model_name}")
        except Exception as e:
            logger.warning(f"[ImageAPI][{req_id}] Failed to encode ref images, text2img fallback: {e}")

    body_size = len(json.dumps(body, ensure_ascii=False))
    prompt_preview = final_prompt[:200].replace("\n", " ")
    logger.info(
        f"[ImageAPI][{req_id}] -> POST {url} | model={model_name} size={size} n=1 "
        f"img2img={bool(reference_image_paths)} body_size={body_size} prompt='{prompt_preview}'"
    )

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=30, read=600, write=60, pool=30)) as client:
            resp = await client.post(url, json=body, headers=headers)
    except httpx.RemoteProtocolError as e:
        logger.error(f"[ImageAPI][{req_id}] connection broken: {e}")
        raise ValueError(f"服务端断开连接（可能是请求体过大或模型不支持图片输入）: {e}")
    except httpx.ReadTimeout:
        logger.error(f"[ImageAPI][{req_id}] read timeout after 600s")
        raise ValueError(f"请求超时（600秒），模型处理时间过长")
    except httpx.ConnectError as e:
        logger.error(f"[ImageAPI][{req_id}] connect error: {e}")
        raise ValueError(f"连接失败，请检查 base_url 是否正确: {e}")
    except httpx.HTTPStatusError as e:
        logger.error(f"[ImageAPI][{req_id}] http status error: {e}")
        raise ValueError(f"HTTP 错误: {e}")

    elapsed = time.monotonic() - start
    logger.info(f"[ImageAPI][{req_id}] <- status={resp.status_code} in {elapsed:.1f}s")

    if resp.status_code >= 400:
        try:
            err_detail = resp.json()
        except Exception:
            err_detail = resp.text
        logger.error(f"[ImageAPI][{req_id}] API error {resp.status_code}: {str(err_detail)[:800]}")
        raise ValueError(f"API {resp.status_code}: {err_detail}")
    data = resp.json()
    logger.info(f"[ImageAPI][{req_id}] response keys={list(data.keys())}, preview={str(data)[:800]}")

    # Support multiple API response formats
    images = data.get("data") or data.get("images") or data.get("results") or []
    # Some APIs return single image directly at top level
    if not images and (data.get("url") or data.get("b64_json") or data.get("image_url")):
        images = [data]
    if not images:
        raise ValueError(f"图片生成 API 未返回图片数据, 响应: {str(data)[:1000]}")

    def _resolve_image(img_data: dict) -> str:
        """Return URL; if b64_json, save to file and return file path."""
        url = img_data.get("url") or img_data.get("image_url")
        if url:
            return url
        b64 = img_data.get("b64_json")
        if b64:
            # Save base64 data as file
            img_bytes = base64.b64decode(b64)
            filename = f"{uuid.uuid4().hex}.png"
            filepath = os.path.join(UPLOAD_DIR, filename)
            with open(filepath, "wb") as f:
                f.write(img_bytes)
            logger.info(f"[ImageAPI][{req_id}] Saved b64_json to file: {filename} ({len(img_bytes)} bytes)")
            return f"/uploads/{filename}"
        raise ValueError(f"图片生成 API 未返回 url 或 b64_json, 响应: {img_data}")

    # Each call requests a single image, so return the first one.
    result_url = _resolve_image(images[0])
    logger.info(f"[ImageAPI][{req_id}] done -> image={result_url}")
    return result_url


async def _generate_one(prompt: str, cfg: dict, image_paths: Optional[List[str]], n: int = 1) -> list:
    """Generate n image(s) with a single model, return list of result dicts.

    Issues n independent single-image requests (concurrently) instead of one
    request with n>1. Relay/proxy image models collapse an n>1 request into a
    single collage/nine-grid image, so one request per image is what reliably
    yields n distinct standalone images. n is clamped to MAX_IMAGES_PER_REQUEST."""
    name = cfg.get("config_name", cfg["model_name"])
    count = min(max(1, int(n or 1)), MAX_IMAGES_PER_REQUEST)
    logger.info(f"[ImageAPI] _generate_one: model={name} requested_n={n} -> issuing {count} independent n=1 call(s)")

    async def _single():
        url = await call_image_api(
            prompt=prompt,
            api_key=cfg["api_key"],
            base_url=cfg["base_url"],
            model_name=cfg["model_name"],
            reference_image_paths=image_paths if image_paths else None,
        )
        return {"model_name": name, "image_url": url, "error": None}

    results = await asyncio.gather(*[_single() for _ in range(count)], return_exceptions=True)
    out = []
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"[ImageAPI] _generate_one: model={name} one image failed: {r}")
            out.append({"model_name": name, "image_url": None, "error": str(r)})
        else:
            out.append(r)
    ok = sum(1 for o in out if o.get("image_url"))
    logger.info(f"[ImageAPI] _generate_one done: model={name} {ok}/{count} image(s) succeeded")
    return out


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
