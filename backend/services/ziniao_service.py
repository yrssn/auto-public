import json
import time
import base64
import httpx

from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import PKCS1_v1_5

from config import settings

def _format_private_key(pk: str) -> str:
    pk = pk.strip()
    if pk.startswith("-----"):
        return pk
    # Raw base64 string (e.g. MIIE...), could be PKCS#8 or PKCS#1
    # Try PKCS#8 first (most common for Ziniao), fallback to PKCS#1
    # Chunk into 64-char lines
    lines = [pk[i:i+64] for i in range(0, len(pk), 64)]
    body = "\n".join(lines)
    # Try PKCS#8 header first
    pem = f"-----BEGIN PRIVATE KEY-----\n{body}\n-----END PRIVATE KEY-----"
    try:
        RSA.importKey(pem)
        return pem
    except Exception:
        pass
    # Fallback to PKCS#1
    pem = f"-----BEGIN RSA PRIVATE KEY-----\n{body}\n-----END RSA PRIVATE KEY-----"
    return pem


def _sign_rsa2(content: str, private_key: str) -> str:
    pk_raw = private_key.strip()
    print(f"[DEBUG] key length={len(pk_raw)}, first20={pk_raw[:20]}, last20={pk_raw[-20:]}")

    # Method 1: If it's already a PEM string, use directly
    if pk_raw.startswith("-----"):
        key = RSA.importKey(pk_raw)
    else:
        # Method 2: Try importing raw base64 as DER bytes directly
        try:
            der_bytes = base64.b64decode(pk_raw)
            key = RSA.import_key(der_bytes)
        except Exception as e1:
            print(f"[DEBUG] DER import failed: {e1}")
            # Method 3: Wrap with PEM headers
            pk_pem = _format_private_key(pk_raw)
            key = RSA.importKey(pk_pem)

    h = SHA256.new(content.encode("utf-8"))
    signer = PKCS1_v1_5.new(key)
    return base64.b64encode(signer.sign(h)).decode("utf-8")


def _get_sign_content(params: dict) -> str:
    parts = []
    for k in sorted(params.keys()):
        v = str(params[k])
        if v:
            parts.append(f"{k}={v}")
    return "&".join(parts)


def _build_params(method: str, biz_content: dict | None = None,
                  app_token: str | None = None, user_token: str | None = None) -> dict:
    params = {
        "app_id": settings.ZINIAO_APP_ID,
        "method": method,
        "charset": "UTF-8",
        "sign_type": "RSA2",
        "timestamp": int(round(time.time() * 1000)),
        "version": "1.0",
        "sdk_version": "1.0",
        "biz_content": json.dumps(biz_content or {}),
        "params_content": json.dumps({}),
    }
    if app_token:
        params["app_auth_token"] = app_token
    if user_token:
        params["user_access_token"] = user_token

    sign_content = _get_sign_content(params)
    params["sign"] = _sign_rsa2(sign_content, settings.ZINIAO_APP_SECRET)
    return params


async def _post(method: str, biz_content: dict | None = None,
                app_token: str | None = None, user_token: str | None = None) -> dict:
    params = _build_params(method, biz_content, app_token, user_token)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            settings.ZINIAO_API_URL,
            json=params,
            headers={"Accept-Encoding": "identity"},
        )
        try:
            return resp.json()
        except Exception:
            resp.raise_for_status()
            return {"error": resp.text}


# ---- 1. 获取应用 token ----
async def get_app_token() -> dict:
    return await _post("/auth/get_app_token")


# ---- 签名 GET 请求（参数放 query string） ----
async def _get(method: str, biz_content: dict | None = None,
               app_token: str | None = None, user_token: str | None = None) -> dict:
    params = _build_params(method, biz_content, app_token, user_token)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            settings.ZINIAO_API_URL,
            params=params,
            headers={"Accept-Encoding": "identity"},
        )
        try:
            return resp.json()
        except Exception:
            resp.raise_for_status()
            return {"error": resp.text}


# ---- 2. 获取公司信息 (companyId) ---- GET + app_token
async def get_company_info(app_token: str) -> dict:
    return await _get("/app/builtin/company", app_token=app_token)


# ---- 3. ERP 员工查询 ---- POST + app_token
async def get_staff_list(app_token: str, company_id: str, page: int = 1, page_size: int = 50) -> dict:
    biz = {"companyId": company_id, "pageNo": page, "pageSize": page_size}
    return await _post("/superbrowser/rest/v1/erp/staff/list", biz_content=biz, app_token=app_token)


# ---- 4. ERP 店铺列表查询 ---- POST + app_token
async def get_store_list(app_token: str, company_id: str, page: int = 1, page_size: int = 50) -> dict:
    biz = {"companyId": company_id, "pageNo": page, "pageSize": page_size}
    return await _post("/superbrowser/rest/v1/erp/store/list", biz_content=biz, app_token=app_token)
