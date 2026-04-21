# 电商选品系统

基于 FastAPI + Vue 3 + LangChain 的电商选品系统。

## 功能模块

- **JWT 认证**：注册 / 登录 / Token 鉴权
- **模型配置**：支持 OpenAI / DeepSeek / 智谱 等多模型配置管理
- **图片生成**：LangChain 驱动的 AI 商品图片生成（提示词优化 + DALL·E）

## 快速启动

### 后端

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env  # 编辑配置
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

浏览器访问 `http://localhost:3000`

## 技术栈

| 层 | 技术 |
|---|------|
| 后端 | FastAPI, SQLAlchemy, python-jose (JWT), Passlib |
| AI | LangChain, langchain-openai |
| 前端 | Vue 3, Vite, Element Plus, Pinia, Vue Router |
| 数据库 | SQLite (可切换 PostgreSQL) |
