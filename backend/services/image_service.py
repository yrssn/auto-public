import asyncio
import base64
import logging
import re
import httpx
from typing import Optional, List
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, AIMessage, SystemMessage

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是一个AI图片生成提示词专家，支持多轮对话。你的任务是根据用户的需求，生成最适合图片生成模型的英文提示词。

核心原则：**忠实理解用户的真实意图，不要自作主张改变需求。**

场景判断：
1. 如果用户要求"修改图片中的文字"（如改成英文、日文等），生成的提示词应明确要求保持原图的设计、布局、颜色不变，只替换文字内容和语言
2. 如果用户要求"换背景"、"调光线"等编辑操作，提示词应描述原图内容+具体修改要求
3. 如果用户描述商品要生成新图片，才使用电商摄影风格的提示词（白底图、场景图等）
4. 如果用户的需求不明确，根据上下文合理推断

要求：
- 如果有参考图片，仔细分析图片内容（文字、布局、产品、颜色等）
- 生成的提示词要精确反映用户的修改意图
- 参考之前的对话内容，理解迭代需求
- 只输出最终的英文提示词，不要解释"""

MULTI_PROMPT_SYSTEM = """你是一个电商产品摄影提示词专家。用户需要一套产品照片，每张是独立的单张照片（不是合成图/拼图/详情页布局）。

你需要根据用户的需求，生成 {n} 条不同的英文提示词。每条提示词只描述一张独立的照片，而不是一个包含多个模块的页面布局。

重要约束：
- 每条提示词描述的是一张独立的产品摄影照片
- 绝对不要生成"页面布局""多模块合成图""详情页设计"类的提示词
- 每张照片只有一个拍摄主题和构图

照片类型示例（根据用户需求选取）：
- KV主图：模特全身穿搭照，简洁背景，产品为视觉焦点
- 卖点特写：突出面料质感/版型剪裁的近景照片
- 细节微距：材质纹理、缝线、标签、纽扣等局部特写
- 外出场景：模特穿着产品在城市街道/咖啡馆等场景
- 旅行场景：模特穿着产品在自然/度假场景
- 日常场景：模特穿着产品在家居/办公等日常场景
- 颜色展示：不同颜色的产品平铺或挂拍对比
- 搭配展示：模特穿着产品搭配不同配饰/鞋包
- 背面展示：产品背面细节照片
- 平铺图：产品平放展示的俯拍照片

要求：
- 每条提示词只描述一张照片的拍摄内容、角度、光线、背景
- 不同提示词之间要有明显的拍摄角度/场景/用途差异
- 如果有参考图片，基于图片中的实际产品外观来描述
- 保持统一的摄影风格和色调
- 每条提示词前用 [类型] 标注，如 [KV主图]
- 用 --- 分隔每条提示词
- 只输出提示词，不要解释"""

ANALYZE_IMAGE_PROMPT = """请详细分析这张商品图片，描述以下内容：
1. 产品类型和名称
2. 颜色、材质、造型特征
3. 拍摄角度和背景
4. 产品卖点和适用场景

用户补充说明：{prompt}

请用中文详细描述。"""


def _encode_image(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _get_image_mime(image_path: str) -> str:
    ext = image_path.rsplit(".", 1)[-1].lower()
    mime_map = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp"}
    return mime_map.get(ext, "image/png")


def build_history_messages(tasks) -> list:
    """Build LangChain message history from previous tasks in the conversation."""
    messages = []
    for t in tasks:
        content = t.prompt
        if t.optimized_prompt:
            messages.append(HumanMessage(content=content))
            messages.append(AIMessage(content=t.optimized_prompt))
        else:
            messages.append(HumanMessage(content=content))
    return messages


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
    base = base_url.rstrip('/')
    if base.endswith('/images/generations'):
        url = base
    else:
        url = f"{base}/images/generations"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {"model": model_name, "prompt": prompt, "n": n, "size": size, "response_format": "url"}

    # Include reference images for img2img if available
    if reference_image_paths:
        try:
            if len(reference_image_paths) == 1:
                # Single image: use "image" field
                body["image"] = _encode_image_or_url(reference_image_paths[0])
                logger.info(f"[ImageAPI] img2img mode, 1 ref image, model={model_name}")
            else:
                # Multiple images: use "image" as array (API dependent)
                body["image"] = [_encode_image_or_url(p) for p in reference_image_paths]
                logger.info(f"[ImageAPI] img2img mode, {len(reference_image_paths)} ref images, model={model_name}")
        except Exception as e:
            logger.warning(f"[ImageAPI] Failed to encode ref images, text2img fallback: {e}")

    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(url, json=body, headers=headers)
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


def _clean_prompt_for_api(prompt: str) -> str:
    """Clean prompt before sending to image API: remove type labels, add single-photo constraint."""
    # Remove [类型] labels like [KV Main], [KV主图] etc.
    cleaned = re.sub(r'\[[\w\s/\u4e00-\u9fff]+\]\s*', '', prompt).strip()
    # Add single-photo constraint to prevent composite layouts
    if "single photo" not in cleaned.lower() and "single product" not in cleaned.lower():
        cleaned += ". Single standalone photograph, not a collage, not a page layout, not a composite image."
    return cleaned


async def _generate_one(prompt: str, cfg: dict, image_paths: Optional[List[str]], n: int = 1) -> list:
    """Generate image(s) with a single model, return list of result dicts.
    First tries n parameter; if API only returns 1, falls back to parallel single calls."""
    name = cfg.get("config_name", cfg["model_name"])
    prompt = _clean_prompt_for_api(prompt)
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
            results = [{"model_name": name, "image_url": url, "error": None} for url in result]
        else:
            results = [{"model_name": name, "image_url": result, "error": None}]

        # If API ignored n and only returned 1, do parallel calls for the rest
        if len(results) < n and n > 1:
            remaining = n - len(results)
            logger.info(f"[Generate] {name} returned {len(results)}/{n}, making {remaining} extra calls")
            extra_tasks = [
                call_image_api(
                    prompt=prompt,
                    api_key=cfg["api_key"],
                    base_url=cfg["base_url"],
                    model_name=cfg["model_name"],
                    reference_image_paths=image_paths if image_paths else None,
                    n=1,
                )
                for _ in range(remaining)
            ]
            extra_results = await asyncio.gather(*extra_tasks, return_exceptions=True)
            for r in extra_results:
                if isinstance(r, Exception):
                    results.append({"model_name": name, "image_url": None, "error": str(r)})
                elif isinstance(r, list):
                    results.append({"model_name": name, "image_url": r[0], "error": None})
                else:
                    results.append({"model_name": name, "image_url": r, "error": None})
        return results
    except Exception as e:
        return [{"model_name": name, "image_url": None, "error": str(e)}]


FALLBACK_PHOTO_TYPES = [
    ("KV Main", "Professional e-commerce hero shot, single product photo, model wearing the item, full body, clean minimal background, soft natural lighting, fashion photography, 800x800px"),
    ("Detail Close-up", "Close-up detail shot of fabric texture and stitching quality, macro photography, soft lighting, single product photo, clean background, 800x800px"),
    ("Outdoor Scene", "Fashion lifestyle photo, model wearing the item walking on a city street, natural daylight, candid style, single photo, 800x800px"),
    ("Travel Scene", "Lifestyle photo, model wearing the item at a scenic travel destination, natural background, warm sunlight, single photo, 800x800px"),
    ("Daily Scene", "Casual lifestyle photo, model wearing the item in a cozy cafe or home setting, relaxed pose, natural indoor lighting, single photo, 800x800px"),
    ("Color Variation", "Flat lay product photo showing different color options of the same item side by side, clean white background, overhead shot, 800x800px"),
    ("Back View", "Back view of model wearing the item, showing back design details, clean background, fashion photography, 800x800px"),
    ("Coordination", "Full outfit coordination photo, model wearing the item with matching accessories bags and shoes, lifestyle fashion photography, 800x800px"),
    ("Fabric Detail", "Extreme close-up of fabric material and texture, showing breathability and softness, studio macro photography, 800x800px"),
    ("Selling Point", "Product feature highlight photo, showing the slim-fit silhouette design, model posing to demonstrate the flattering cut, clean background, 800x800px"),
    ("Flat Lay", "Overhead flat lay of the neatly folded product on white background, minimalist style, studio photography, 800x800px"),
    ("Size Reference", "Model wearing the item with height and measurement reference, clean background, showing how the item fits on body, 800x800px"),
    ("Casual Outdoor", "Model wearing the item in a park or garden, natural greenery background, relaxed walking pose, golden hour lighting, 800x800px"),
    ("Shopping Scene", "Model wearing the item in a shopping district, modern urban background, stylish walking pose, natural daylight, 800x800px"),
    ("Comfort Focus", "Close-up of model comfortably wearing the item, focus on comfortable movement and stretch, natural indoor lighting, 800x800px"),
]


def _build_fallback_prompts(user_prompt: str, n: int) -> list:
    """Build n different photo-type prompts as fallback when LLM optimization fails."""
    # Extract product keywords from user prompt (rough extraction)
    product_hint = user_prompt[:100] if user_prompt else "fashion dress"
    prompts = []
    for i in range(min(n, len(FALLBACK_PHOTO_TYPES))):
        label, base = FALLBACK_PHOTO_TYPES[i]
        prompts.append(f"[{label}] {base}, product: {product_hint}")
    # If n > available types, cycle
    while len(prompts) < n:
        idx = len(prompts) % len(FALLBACK_PHOTO_TYPES)
        label, base = FALLBACK_PHOTO_TYPES[idx]
        prompts.append(f"[{label} v2] {base}, product: {product_hint}, different angle")
    return prompts


async def generate_image_stream(
    prompt: str,
    optimize: bool,
    scene_paths: Optional[List[str]],
    product_paths: Optional[List[str]],
    chat_config: dict,
    image_configs: Optional[List[dict]] = None,
    history: Optional[list] = None,
    n: int = 1,
):
    """
    Async generator that yields status dicts during image generation.
    chat_config: {"api_key", "base_url", "model_name"} for prompt optimization
    image_configs: list of {"api_key", "base_url", "model_name", "config_name"} for image generation
    scene_paths: list of scene/template image paths
    product_paths: list of product image paths (to be inserted into scenes)
    """
    result = {"optimized_prompt": None, "image_url": None, "image_results": []}

    # Build chat LLM
    llm_kwargs = {"api_key": chat_config["api_key"], "model": chat_config["model_name"]}
    if chat_config.get("base_url"):
        llm_kwargs["base_url"] = chat_config["base_url"]
    llm = ChatOpenAI(**llm_kwargs, temperature=0.7)

    # Combine all images for vision model
    all_image_paths = (scene_paths or []) + (product_paths or [])
    has_images = bool(all_image_paths)

    # Step 1: Optimize prompt with conversation history
    multi_prompts = []  # For n>1 set generation
    if optimize:
        model_name = chat_config.get("model_name", "unknown")
        yield {"step": "optimizing", "message": f"正在用 {model_name} 优化提示词..."}
        logger.info(f"[Optimize] Using model={model_name}, scenes={len(scene_paths or [])}, products={len(product_paths or [])}")

        # Use multi-prompt system when n > 1
        if n > 1:
            sys_prompt = MULTI_PROMPT_SYSTEM.replace("{n}", str(n))
        else:
            sys_prompt = SYSTEM_PROMPT

        messages = [SystemMessage(content=sys_prompt)]
        if history:
            messages.extend(history)

        # Build user message: include images if uploaded (for vision models)
        if has_images:
            try:
                if product_paths and scene_paths:
                    text = f"任务：{prompt}\n\n以下是场景图（模板），后面是产品图。请生成将产品替换到场景中的提示词。"
                elif scene_paths:
                    text = f"商品描述：{prompt}\n\n请分析这些场景图片并结合描述生成优化提示词。"
                else:
                    text = f"商品描述：{prompt}\n\n请分析这些产品图片并生成优化提示词。"
                if n > 1:
                    text += f"\n\n请生成 {n} 条不同用途的提示词，用 --- 分隔。"
                content_parts = [{"type": "text", "text": text}]
                for img_path in all_image_paths:
                    img_data = _encode_image_or_url(img_path)
                    content_parts.append({"type": "image_url", "image_url": {"url": img_data}})
                user_msg = HumanMessage(content=content_parts)
                logger.info(f"[Optimize] {len(all_image_paths)} images included")
            except Exception as e:
                logger.error(f"[Optimize] Failed to encode images: {e}")
                user_msg = HumanMessage(content=f"商品描述：{prompt}")
        else:
            user_msg = HumanMessage(content=f"商品描述：{prompt}")
            if n > 1:
                user_msg = HumanMessage(content=f"商品描述：{prompt}\n\n请生成 {n} 条不同用途的提示词，用 --- 分隔。")

        messages.append(user_msg)

        try:
            response = await llm.ainvoke(messages)
            optimized = response.content.strip()
            result["optimized_prompt"] = optimized
            logger.info(f"[Optimize] Success, prompt={optimized[:100]}...")
            yield {"step": "optimized", "message": "提示词优化完成", "optimized_prompt": optimized}

            # Parse multiple prompts if n > 1
            if n > 1 and "---" in optimized:
                multi_prompts = [p.strip() for p in optimized.split("---") if p.strip()]
                logger.info(f"[Optimize] Parsed {len(multi_prompts)} distinct prompts for set generation")
        except Exception as e:
            logger.error(f"[Optimize] LLM call failed: {e}", exc_info=True)
            optimized = prompt
            result["optimized_prompt"] = f"[优化失败，使用原始提示词] {prompt}"
            yield {"step": "optimize_failed", "message": f"提示词优化失败: {e}，使用原始提示词"}
            # Fallback: generate varied prompts locally when LLM fails and n > 1
            if n > 1:
                multi_prompts = _build_fallback_prompts(prompt, n)
                logger.info(f"[Optimize] Using {len(multi_prompts)} fallback prompts")
    else:
        optimized = prompt

    # Step 2: Generate images (supports multiple models in parallel)
    if image_configs:
        model_names = [c.get("config_name", c["model_name"]) for c in image_configs]

        if multi_prompts:
            # Set generation: each prompt generates 1 image per model
            total = len(multi_prompts) * len(image_configs)
            yield {"step": "generating", "message": f"正在生成 {len(multi_prompts)} 张不同用途的图片 x {len(image_configs)} 个模型 (共 {total} 张)"}
            tasks = []
            for p in multi_prompts:
                for cfg in image_configs:
                    tasks.append(_generate_one(p, cfg, all_image_paths if all_image_paths else None, n=1))
            nested_results = await asyncio.gather(*tasks)
        else:
            yield {"step": "generating", "message": f"正在用 {len(image_configs)} 个模型并行生成图片: {', '.join(model_names)}"}
            # Run all models in parallel (pass all images for img2img)
            tasks = [_generate_one(optimized, cfg, all_image_paths if all_image_paths else None, n=n) for cfg in image_configs]
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
        result["error"] = "未配置图片生成模型，仅返回优化提示词"
        yield {"step": "no_image_model", "message": "未配置图片生成模型，仅返回优化提示词"}

    yield {"step": "done", "message": "完成", "result": result}
