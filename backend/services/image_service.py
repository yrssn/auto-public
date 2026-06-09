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




# Max pixel size for reference images. Smaller = smaller payload = fewer disconnects.
# 512px is usually sufficient for gpt-image-2 to understand the product.
REF_IMAGE_MAX_SIZE = 512
REF_IMAGE_QUALITY = 70  # JPEG quality (0-100)


def _encode_image_or_url(path: str, max_size: int = REF_IMAGE_MAX_SIZE) -> str:
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
        img.save(buf, format="JPEG", quality=REF_IMAGE_QUALITY)
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


async def expand_prompts(
    base_prompt: str,
    n: int,
    text_cfg: dict,
    has_reference: bool = False,
) -> List[str]:
    """Use a chat/LLM model to expand one description into n distinct, complementary
    image-generation prompts (e.g. KV主图 / 卖点 / 细节 / 场景 for a 详情页).

    Returns a list of exactly n prompt strings. On any failure, falls back to
    repeating base_prompt n times so generation never breaks because of this step."""
    fallback = [base_prompt] * n
    if n <= 1 or not text_cfg:
        return fallback

    req_id = uuid.uuid4().hex[:8]
    url = f"{text_cfg['base_url'].rstrip('/')}/chat/completions"
    model_name = text_cfg["model_name"]
    ref_note = (
        "用户还提供了一张参考产品图，N 个提示词必须全部基于这同一件实拍商品（同一主体），"
        "不得替换成其它款式或颜色。"
        if has_reference
        else ""
    )
    # The user wants N images to form ONE cohesive set (一套) of the SAME single
    # product, decomposed into N complementary sections/shots — NOT N independent
    # full pages of different products. So we (1) lock a single product identity
    # that every sub-prompt must repeat, and (2) split the set into N distinct
    # sections that progress KV主图 → 卖点 → 细节 → 场景.
    system_prompt = (
        "你是电商详情页视觉策划＋提示词专家。用户会给你【一套】商品图的整体描述，"
        f"以及需要的张数 N={n}。你的任务是把这一套图拆解成 N 个互补的「章节/分镜」提示词，"
        "让这 N 张图合起来构成同一套、同一件商品的完整视觉物料。\n"
        "硬性规则：\n"
        "1) 一致性最重要：N 张必须是【同一件商品】——同款式、同颜色、同面料、同一位模特、"
        "同一种色调与画面风格。先从原始描述中提炼该商品的核心固定属性（品类/颜色/材质/廓形/"
        "模特与风格/色调/尺寸），并把这组固定属性【原样写进每一个提示词】，确保不串成不同的衣服。\n"
        f"{ref_note}"
        "2) 互补不重复：按 N 把这套图拆成不同章节，每个提示词只聚焦【一个】章节/视角，"
        "覆盖顺序优先级为 KV主图(整体正面主视觉) → 卖点说明 → 细节特写(领口/版型/面料等) → "
        "场景/穿搭展示(日常生活场景)。N=2 时取『KV主图整体』+『场景穿搭或细节』；"
        "N=4 时分别为 KV主图 / 卖点 / 细节特写 / 场景展示；其它 N 同理按此优先级取前 N 个互补章节。\n"
        "3) 每个提示词都要自包含、具体、可直接喂给图片生成模型，并保留原描述的语言"
        "（原文是日语就用日语）、风格、800×800 等尺寸要求。\n"
        "4) 严格只输出一个 JSON 数组（形如 [\"prompt1\", \"prompt2\"]），数组长度正好为 N，"
        "不要输出任何额外文字、解释或 markdown。"
    )
    user_prompt = (
        f"这一套商品图的整体描述如下：\n{base_prompt}\n\n"
        f"请把它拆解成正好 {n} 个互补章节的提示词，要求是【同一件商品】的不同分镜，合起来是一套。"
    )
    body = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.8,
    }
    headers = {"Authorization": f"Bearer {text_cfg['api_key']}", "Content-Type": "application/json"}
    logger.info(
        f"[ImageAPI][{req_id}] expand_prompts -> POST {url} | text_model={model_name} "
        f"n={n} base_prompt='{base_prompt[:120].replace(chr(10), ' ')}'"
    )
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(connect=30, read=120, write=30, pool=30)) as client:
            resp = await client.post(url, json=body, headers=headers)
        elapsed = time.monotonic() - start
        logger.info(f"[ImageAPI][{req_id}] expand_prompts <- status={resp.status_code} in {elapsed:.1f}s")
        if resp.status_code >= 400:
            logger.error(f"[ImageAPI][{req_id}] expand_prompts API error {resp.status_code}: {resp.text[:500]}")
            return fallback
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        logger.error(f"[ImageAPI][{req_id}] expand_prompts failed, falling back to base prompt: {e}")
        return fallback

    prompts = _parse_prompt_list(content)
    if not prompts:
        logger.error(f"[ImageAPI][{req_id}] expand_prompts could not parse model output, falling back. raw={content[:500]}")
        return fallback

    # Normalize to exactly n prompts (pad with base_prompt, truncate extras).
    if len(prompts) < n:
        prompts = prompts + [base_prompt] * (n - len(prompts))
    prompts = prompts[:n]
    for i, p in enumerate(prompts):
        logger.info(f"[ImageAPI][{req_id}] expand_prompts result[{i}]='{p[:160].replace(chr(10), ' ')}'")
    return prompts


def _parse_prompt_list(content: str) -> List[str]:
    """Best-effort parse of an LLM response into a list of prompt strings.
    Handles raw JSON arrays, ```json fenced blocks, and falls back to line splitting."""
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    # Try to locate a JSON array inside the text.
    lb, rb = text.find("["), text.rfind("]")
    if lb != -1 and rb != -1 and rb > lb:
        try:
            arr = json.loads(text[lb:rb + 1])
            items = [str(x).strip() for x in arr if str(x).strip()]
            if items:
                return items
        except (json.JSONDecodeError, TypeError):
            pass
    # Fallback: split non-empty lines, stripping list markers.
    lines = []
    for ln in text.splitlines():
        s = ln.strip().lstrip("-*0123456789.、) ").strip()
        if s:
            lines.append(s)
    return lines


async def call_image_api(
    prompt: str,
    api_key: str,
    base_url: str,
    model_name: str,
    size: str = "1024x1024",
    reference_image_paths: Optional[List[str]] = None,
    single_image_hint: bool = True,
    quality: str = "auto",
    n: int = 1,
) -> List[str]:
    """Call OpenAI-compatible image generation API. Returns list of image URLs.
    Supports optional reference images for image-to-image generation.

    When n>1, the API generates multiple related images in a single call,
    ensuring strong consistency between images (same style, same subject).

    gpt-image-2 parameters:
    - quality: 'low' | 'medium' | 'high' | 'auto' (default 'auto')
    - size: supports flexible sizes like '1024x1024', '1536x1024', '1024x1536', 'auto'
    - n: number of images to generate in one call (1-10)
    """
    req_id = uuid.uuid4().hex[:8]
    url = f"{base_url.rstrip('/')}/images/generations"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    final_prompt = prompt
    # Only add single-image hint when n=1 to prevent collages
    if n == 1 and single_image_hint and SINGLE_IMAGE_HINT.strip() not in prompt:
        final_prompt = f"{prompt}{SINGLE_IMAGE_HINT}"
    body = {"model": model_name, "prompt": final_prompt, "n": n}
    # Only include size if explicitly specified (relay APIs may not need it)
    if size and size != "auto":
        body["size"] = size
    # gpt-image-2 quality parameter
    if quality and quality != "auto":
        body["quality"] = quality
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
        f"[ImageAPI][{req_id}] -> POST {url} | model={model_name} size={body.get('size', 'auto')} n={n} "
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
        url_val = img_data.get("url") or img_data.get("image_url")
        if url_val:
            return url_val
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

    # Resolve all returned images
    result_urls = [_resolve_image(img) for img in images]
    logger.info(f"[ImageAPI][{req_id}] done -> {len(result_urls)} image(s)")
    return result_urls


async def _generate_one(
    prompts: List[str],
    cfg: dict,
    image_paths: Optional[List[str]],
    quality: str = "auto",
    size: str = "auto",
) -> list:
    """Generate one image per prompt with a single model, SEQUENTIALLY.

    Issues len(prompts) independent n=1 API calls one at a time (not parallel).
    Sequential execution avoids overwhelming relay APIs and stops early on failure
    to prevent wasting money on calls that will also fail.

    Each call uses its own prompt (from expand_prompts) but the same reference
    images, ensuring the images form a coherent set."""
    name = cfg.get("config_name", cfg["model_name"])
    prompts = prompts[:MAX_IMAGES_PER_REQUEST] or [""]
    count = len(prompts)
    logger.info(
        f"[ImageAPI] _generate_one: model={name} -> {count} sequential n=1 call(s) "
        f"quality={quality} size={size}"
    )

    out = []
    for idx, p in enumerate(prompts):
        try:
            urls = await call_image_api(
                prompt=p,
                api_key=cfg["api_key"],
                base_url=cfg["base_url"],
                model_name=cfg["model_name"],
                size=size,
                reference_image_paths=image_paths if image_paths else None,
                quality=quality,
                n=1,
            )
            out.append({"model_name": name, "image_url": urls[0] if urls else None, "error": None, "prompt": p, "index": idx})
            logger.info(f"[ImageAPI] _generate_one: model={name} image #{idx+1}/{count} OK")
        except Exception as e:
            logger.error(f"[ImageAPI] _generate_one: model={name} image #{idx+1}/{count} failed: {e}")
            out.append({"model_name": name, "image_url": None, "error": str(e), "prompt": p, "index": idx})
            # Stop early on failure to avoid wasting money
            logger.warning(f"[ImageAPI] _generate_one: stopping early after failure on image #{idx+1}")
            break

    ok = sum(1 for o in out if o.get("image_url"))
    logger.info(f"[ImageAPI] _generate_one done: model={name} {ok}/{count} image(s) succeeded")
    return out


async def generate_image_stream(
    prompt: str,
    product_paths: Optional[List[str]] = None,
    image_configs: Optional[List[dict]] = None,
    n: int = 1,
    text_config: Optional[dict] = None,
    quality: str = "auto",
    size: str = "auto",
):
    """
    Async generator that yields status dicts during image generation.
    image_configs: list of {"api_key", "base_url", "model_name", "config_name"} for image generation
    text_config: optional {"api_key", "base_url", "model_name", "config_name"} chat model used
                 to expand the description into n complementary sub-prompts (KV/卖点/细节/场景)
    product_paths: list of product image paths (for img2img, supports multiple reference images)
    n: number of images to generate (each as a separate n=1 call, sequentially)
    quality: 'low' | 'medium' | 'high' | 'auto' (gpt-image-2 quality setting)
    size: image size e.g. '1024x1024', '1536x1024', 'auto'
    """
    result = {"optimized_prompt": None, "image_url": None, "image_results": []}

    image_paths = product_paths if product_paths else None

    # Generate images
    if image_configs:
        count = min(max(1, int(n or 1)), MAX_IMAGES_PER_REQUEST)

        # When more than one image is requested, use the chat model to expand the
        # single description into N distinct, complementary prompts (分镜).
        # This ensures images form a coherent SET (KV主图/卖点/细节/场景) with the
        # SAME product identity locked across all sub-prompts.
        if count > 1 and text_config:
            yield {"step": "expanding", "message": f"正在用文字模型 {text_config.get('config_name', text_config['model_name'])} 拆解为 {count} 个分镜提示词…"}
            prompts = await expand_prompts(prompt, count, text_config, has_reference=bool(image_paths))
            if len({p for p in prompts}) <= 1:
                model_label = text_config.get("config_name", text_config["model_name"])
                warn = (
                    f"⚠ 文字模型 {model_label} 拆解失败（可能是 API Key / 接口地址无效），"
                    f"已回退为用同一描述生成 {count} 张，关联性可能较弱。请检查模型配置。"
                )
                result["optimized_prompt"] = warn
                yield {"step": "expand_failed", "message": warn, "optimized_prompt": warn}
        else:
            prompts = [prompt] * count

        # Surface the per-image prompts so the user can see what was generated.
        if len({p for p in prompts}) > 1:
            result["optimized_prompt"] = "\n".join(f"{i+1}. {p}" for i, p in enumerate(prompts))
            yield {"step": "prompts_ready", "message": "分镜提示词已生成", "optimized_prompt": result["optimized_prompt"]}

        model_names = [c.get("config_name", c["model_name"]) for c in image_configs]
        yield {"step": "generating", "message": f"正在用 {len(image_configs)} 个模型顺序生成 {count} 张图片: {', '.join(model_names)}"}

        # Run each model sequentially (not parallel) to avoid overwhelming relay API
        # Each model generates count images sequentially (one at a time)
        image_results = []
        for cfg in image_configs:
            model_results = await _generate_one(prompts, cfg, image_paths, quality=quality, size=size)
            image_results.extend(model_results)
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
