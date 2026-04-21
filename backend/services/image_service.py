import base64
from typing import Optional
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage


OPTIMIZE_SYSTEM_PROMPT = """你是一个电商产品图片提示词优化专家。
用户会给你一段关于商品的描述（可能附带一张参考图片），请将其优化为高质量的图片生成提示词（英文）。
要求：
1. 如果有参考图片，先分析图片中的产品特征、颜色、材质、造型
2. 结合用户的文字描述和图片信息
3. 突出产品卖点和视觉特征
4. 加入专业摄影术语（如光照、构图、背景）
5. 适合电商白底图或场景图
6. 只输出最终的英文提示词，不要解释"""

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


async def generate_image(
    prompt: str,
    optimize: bool,
    image_path: Optional[str],
    api_key: str,
    base_url: Optional[str],
    model_name: str,
) -> dict:
    """
    Uses LangChain to:
    1. If image uploaded: analyze the image via vision model
    2. Optimize the prompt combining image analysis + user description
    3. Return optimized prompt (and image_url if DALL-E available)
    """
    result = {"optimized_prompt": None, "image_url": None}

    llm_kwargs = {"api_key": api_key, "model": model_name}
    if base_url:
        llm_kwargs["base_url"] = base_url

    llm = ChatOpenAI(**llm_kwargs, temperature=0.7)

    # Step 1: If image is provided, analyze it with vision model
    image_analysis = None
    if image_path:
        b64 = _encode_image(image_path)
        mime = _get_image_mime(image_path)
        messages = [
            HumanMessage(content=[
                {"type": "text", "text": ANALYZE_IMAGE_PROMPT.format(prompt=prompt)},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ])
        ]
        response = await llm.ainvoke(messages)
        image_analysis = response.content.strip()

    # Step 2: Optimize prompt
    if optimize:
        user_content = f"商品描述：{prompt}"
        if image_analysis:
            user_content += f"\n\n图片分析结果：\n{image_analysis}"

        messages = [
            SystemMessage(content=OPTIMIZE_SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ]
        response = await llm.ainvoke(messages)
        optimized = response.content.strip()
        result["optimized_prompt"] = optimized
    else:
        optimized = prompt
        if image_analysis:
            result["optimized_prompt"] = image_analysis

    # Step 3: Try to generate image via DALL-E if available
    try:
        from langchain_community.utilities.dalle_image_generator import DallEAPIWrapper
        dalle = DallEAPIWrapper(api_key=api_key)
        image_url = dalle.run(optimized)
        result["image_url"] = image_url
    except Exception:
        result["image_url"] = None

    return result
