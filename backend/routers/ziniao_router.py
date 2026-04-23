import traceback
from fastapi import APIRouter, HTTPException

from services import ziniao_service

router = APIRouter(prefix="/api/ziniao", tags=["ziniao"])


async def _get_app_token() -> str:
    resp = await ziniao_service.get_app_token()
    if str(resp.get("code")) != "0":
        raise HTTPException(status_code=400, detail=f"获取 app_token 失败: {resp}")
    return resp["data"]["appAuthToken"]


@router.get("/test-connection")
async def test_connection():
    """1. 测试连接：获取 app_token"""
    try:
        result = await ziniao_service.get_app_token()
        code = result.get("code")
        if str(code) != "0":
            raise HTTPException(status_code=400, detail=f"API 返回错误: {result}")
        return {"ok": True, "app_token": result.get("data", {}).get("appAuthToken"), "raw": result}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/company")
async def get_company():
    """2. 获取公司信息 (companyId)"""
    try:
        app_token = await _get_app_token()
        resp = await ziniao_service.get_company_info(app_token)
        return {"ok": True, "data": resp, "raw": resp}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/staff")
async def get_staff(page: int = 1, page_size: int = 50):
    """3. ERP 员工查询"""
    try:
        app_token = await _get_app_token()
        company_resp = await ziniao_service.get_company_info(app_token)
        company_id = str(company_resp.get("companyId") or company_resp.get("data", {}).get("companyId", ""))
        if not company_id:
            raise HTTPException(status_code=400, detail=f"无法获取 companyId: {company_resp}")
        resp = await ziniao_service.get_staff_list(app_token, company_id, page, page_size)
        return {"ok": True, "data": resp, "raw": resp}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stores")
async def get_stores(page: int = 1, page_size: int = 50):
    """4. ERP 店铺列表查询"""
    try:
        app_token = await _get_app_token()
        company_resp = await ziniao_service.get_company_info(app_token)
        company_id = str(company_resp.get("companyId") or company_resp.get("data", {}).get("companyId", ""))
        if not company_id:
            raise HTTPException(status_code=400, detail=f"无法获取 companyId: {company_resp}")
        resp = await ziniao_service.get_store_list(app_token, company_id, page, page_size)
        return {"ok": True, "data": resp, "raw": resp}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
