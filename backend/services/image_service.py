import asyncio
import base64
import logging
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


async def call_image_api(
    prompt: str,
    api_key: str,
    base_url: str,
    model_name: str,
    size: str = "2048x2048",
    reference_image_path: Optional[str] = None,
    n: int = 1,
) -> str:
    """Call OpenAI-compatible image generation API. Returns image URL(s).
    Supports optional reference image for image-to-image generation."""
    url = f"{base_url.rstrip('/')}/images/generations"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {"model": model_name, "prompt": prompt, "n": n, "size": size, "response_format": "url"}

    # Include reference image for img2img if available
    if reference_image_path:
        try:
            if reference_image_path.startswith("http"):
                # Remote URL (e.g. previously generated image)
                body["image"] = reference_image_path
                logger.info(f"[ImageAPI] img2img mode, remote URL, model={model_name}")
            else:
                # Local file path
                img_b64 = _encode_image(reference_image_path)
                img_mime = _get_image_mime(reference_image_path)
                body["image"] = f"data:{img_mime};base64,{img_b64}"
                logger.info(f"[ImageAPI] img2img mode, local file, model={model_name}")
        except Exception as e:
            logger.warning(f"[ImageAPI] Failed to encode ref image, text2img fallback: {e}")

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


async def _generate_one(prompt: str, cfg: dict, image_path: Optional[str], n: int = 1) -> list:
    """Generate image(s) with a single model, return list of result dicts."""
    name = cfg.get("config_name", cfg["model_name"])
    try:
        result = await call_image_api(
            prompt=prompt,
            api_key=cfg["api_key"],
            base_url=cfg["base_url"],
            model_name=cfg["model_name"],
            reference_image_path=image_path,
            n=n,
        )
        if isinstance(result, list):
            return [{"model_name": name, "image_url": url, "error": None} for url in result]
        return [{"model_name": name, "image_url": result, "error": None}]
    except Exception as e:
        return [{"model_name": name, "image_url": None, "error": str(e)}]


async def generate_image_stream(
    prompt: str,
    optimize: bool,
    image_path: Optional[str],
    chat_config: dict,
    image_configs: Optional[List[dict]] = None,
    history: Optional[list] = None,
    n: int = 1,
):
    """
    Async generator that yields status dicts during image generation.
    chat_config: {"api_key", "base_url", "model_name"} for prompt optimization
    image_configs: list of {"api_key", "base_url", "model_name", "config_name"} for image generation
    """
    result = {"optimized_prompt": None, "image_url": None, "image_results": []}

    # Build chat LLM
    llm_kwargs = {"api_key": chat_config["api_key"], "model": chat_config["model_name"]}
    if chat_config.get("base_url"):
        llm_kwargs["base_url"] = chat_config["base_url"]
    llm = ChatOpenAI(**llm_kwargs, temperature=0.7)

    # Step 1: Optimize prompt with conversation history
    if optimize:
        model_name = chat_config.get("model_name", "unknown")
        yield {"step": "optimizing", "message": f"正在用 {model_name} 优化提示词..."}
        logger.info(f"[Optimize] Using model={model_name}, has_image={bool(image_path)}")

        messages = [SystemMessage(content=SYSTEM_PROMPT)]
        if history:
            messages.extend(history)

        # Build user message: include image if uploaded (for vision models)
        if image_path:
            try:
                img_b64 = _encode_image(image_path)
                img_mime = _get_image_mime(image_path)
                user_msg = HumanMessage(content=[
                    {"type": "text", "text": f"商品描述：{prompt}\n\n请分析这张参考图片并结合描述生成优化提示词。"},
                    {"type": "image_url", "image_url": {"url": f"data:{img_mime};base64,{img_b64}"}},
                ])
                logger.info(f"[Optimize] Image included, mime={img_mime}, b64_len={len(img_b64)}")
            except Exception as e:
                logger.error(f"[Optimize] Failed to encode image: {e}")
                user_msg = HumanMessage(content=f"商品描述：{prompt}")
        else:
            user_msg = HumanMessage(content=f"商品描述：{prompt}")

        messages.append(user_msg)

        try:
            response = await llm.ainvoke(messages)
            optimized = response.content.strip()
            result["optimized_prompt"] = optimized
            logger.info(f"[Optimize] Success, prompt={optimized[:100]}...")
            yield {"step": "optimized", "message": "提示词优化完成", "optimized_prompt": optimized}
        except Exception as e:
            logger.error(f"[Optimize] LLM call failed: {e}", exc_info=True)
            optimized = prompt
            result["optimized_prompt"] = f"[优化失败，使用原始提示词] {prompt}"
            yield {"step": "optimize_failed", "message": f"提示词优化失败: {e}，使用原始提示词"}
    else:
        optimized = prompt

    # Step 2: Generate images (supports multiple models in parallel)
    if image_configs:
        model_names = [c.get("config_name", c["model_name"]) for c in image_configs]
        yield {"step": "generating", "message": f"正在用 {len(image_configs)} 个模型并行生成图片: {', '.join(model_names)}"}

        # Run all models in parallel
        tasks = [_generate_one(optimized, cfg, image_path, n=n) for cfg in image_configs]
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
