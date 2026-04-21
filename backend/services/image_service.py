from typing import Optional
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage


OPTIMIZE_SYSTEM_PROMPT = """你是一个电商产品图片提示词优化专家。
用户会给你一段关于商品的描述，请将其优化为高质量的图片生成提示词（英文）。
要求：
1. 突出产品卖点和视觉特征
2. 加入专业摄影术语（如光照、构图、背景）
3. 适合电商白底图或场景图
4. 只输出最终的英文提示词，不要解释"""


async def generate_image(
    prompt: str,
    optimize: bool,
    api_key: str,
    base_url: Optional[str],
    model_name: str,
) -> dict:
    """
    Uses LangChain to:
    1. (Optional) Optimize the user prompt via LLM
    2. Call image generation (DALL-E style or return optimized prompt for external use)
    """
    result = {"optimized_prompt": None, "image_url": None}

    llm_kwargs = {"api_key": api_key, "model": model_name}
    if base_url:
        llm_kwargs["base_url"] = base_url

    llm = ChatOpenAI(**llm_kwargs, temperature=0.7)

    # Step 1: Optimize prompt
    if optimize:
        messages = [
            SystemMessage(content=OPTIMIZE_SYSTEM_PROMPT),
            HumanMessage(content=f"商品描述：{prompt}"),
        ]
        response = await llm.ainvoke(messages)
        optimized = response.content.strip()
        result["optimized_prompt"] = optimized
    else:
        optimized = prompt

    # Step 2: Try to generate image via OpenAI DALL-E if available
    try:
        from langchain_community.utilities.dalle_image_generator import DallEAPIWrapper

        dalle = DallEAPIWrapper(api_key=api_key)
        image_url = dalle.run(optimized)
        result["image_url"] = image_url
    except Exception:
        # If DALL-E is not available, return the optimized prompt for manual use
        result["image_url"] = None

    return result
