import base64
import httpx
from typing import Optional, List
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, AIMessage, SystemMessage


SYSTEM_PROMPT = """你是一个电商产品图片提示词优化专家，支持多轮对话。
用户会给你商品描述或参考图片，请根据对话上下文持续优化图片生成提示词。

要求：
1. 如果有参考图片，分析产品特征、颜色、材质、造型
2. 结合用户的文字描述和图片信息
3. 突出产品卖点和视觉特征
4. 加入专业摄影术语（如光照、构图、背景）
5. 适合电商白底图或场景图
6. 参考之前的对话内容，理解用户的迭代需求（如"换个背景"、"更亮一些"）
7. 只输出最终的英文提示词，不要解释"""

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
) -> str:
    """Call OpenAI-compatible image generation API. Returns image URL.
    Supports optional reference image for image-to-image generation."""
    url = f"{base_url.rstrip('/')}/images/generations"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {"model": model_name, "prompt": prompt, "n": 1, "size": size}

    async with httpx.AsyncClient(timeout=120) as client:
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
        if images:
            return images[0].get("url") or images[0].get("b64_json")
        raise ValueError(f"图片生成 API 未返回图片数据, 响应: {data}")


async def generate_image_stream(
    prompt: str,
    optimize: bool,
    image_path: Optional[str],
    chat_config: dict,
    image_config: Optional[dict] = None,
    history: Optional[list] = None,
):
    """
    Async generator that yields status dicts during image generation.
    chat_config: {"api_key", "base_url", "model_name"} for prompt optimization
    image_config: {"api_key", "base_url", "model_name"} for image generation (optional)
    """
    result = {"optimized_prompt": None, "image_url": None}

    # Build chat LLM
    llm_kwargs = {"api_key": chat_config["api_key"], "model": chat_config["model_name"]}
    if chat_config.get("base_url"):
        llm_kwargs["base_url"] = chat_config["base_url"]
    llm = ChatOpenAI(**llm_kwargs, temperature=0.7)

    # Step 1: Optimize prompt with conversation history (text only, no image)
    if optimize:
        yield {"step": "optimizing", "message": "正在优化提示词..."}
        user_content = f"商品描述：{prompt}"
        if image_path:
            user_content += "\n\n（用户上传了参考图片，将直接传给图片生成模型）"

        messages = [SystemMessage(content=SYSTEM_PROMPT)]
        if history:
            messages.extend(history)
        messages.append(HumanMessage(content=user_content))

        response = await llm.ainvoke(messages)
        optimized = response.content.strip()
        result["optimized_prompt"] = optimized
        yield {"step": "optimized", "message": "提示词优化完成", "optimized_prompt": optimized}
    else:
        optimized = prompt

    # Step 2: Generate image if image model is configured
    if image_config:
        yield {"step": "generating", "message": "正在生成图片..."}
        try:
            image_url = await call_image_api(
                prompt=optimized,
                api_key=image_config["api_key"],
                base_url=image_config["base_url"],
                model_name=image_config["model_name"],
                reference_image_path=image_path,
            )
            result["image_url"] = image_url
            yield {"step": "image_done", "message": "图片生成完成"}
        except Exception as e:
            error_msg = str(e)
            result["error"] = f"图片生成失败: {error_msg}"
            yield {"step": "image_failed", "message": f"图片生成失败: {error_msg}"}
    else:
        result["error"] = "未配置图片生成模型，仅返回优化提示词"
        yield {"step": "no_image_model", "message": "未配置图片生成模型，仅返回优化提示词"}

    yield {"step": "done", "message": "完成", "result": result}
