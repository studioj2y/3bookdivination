# 超级银河自动算命机高级版II型AI强化式样

一个以「神秘学」为基调的占卜 Web 应用：暗色场景里，魔杖尖端的光与漂浮粒子照亮藏在暗处的三册典籍，
点击进入塔罗功能，可抽取多种牌阵、按仪式感逐张翻牌，并由 AI 做全盘解读。

> 当前版本 **v1.0.0**（首个发布版）。三本书中「塔罗」已完整可用；「八字」「占星」为占位，后续迭代接入。

---

## 功能特性

- **沉浸开场**：WebGL 粒子场 + Canvas2D 魔杖浮层，点击水晶球推进入场。
- **三册典籍**：做旧皮革古籍风格（八字 / 占星 / 塔罗），默认藏在暗处，被粒子与魔杖光照亮。
- **塔罗占卜**：
  - 5 种牌阵（三张牌、凯尔特十字等），支持正/逆位。
  - 按牌阵实际位置摆放，逐张点击「翻开」，有顺序引导与仪式感。
  - 翻牌 3D 翻转动效 + 粒子环绕；全部翻完后播放中心爆炸 + 闪白 + 全屏光粒子终章。
  - 可选填写自己的问题，获得更个性化的解读。
  - 全盘解读（叙事式），限 ≤400 字。

## 技术栈

- 前端：纯 HTML / CSS / JavaScript（无构建步骤），WebGL + Canvas2D + SVG。
- 后端：FastAPI（Python），部署在 Vercel Python Serverless。
- 塔罗数据：`tarot.py`（78 张牌 + 牌阵定义）；AI 解读：`tarot_ai.py`。

## 目录结构

```
api/
  app.py             FastAPI 入口（/api/spreads、/api/tarot_spread、/api/tarot_interpret）
  tarot.py           牌库与牌阵逻辑（纯标准库）
  tarot_ai.py        AI 解读（agnes-ai，key 透传）
index.html            前端单文件（含全部样式与脚本）
tarot_images/         78 张塔罗牌图
requirements.txt      依赖
vercel.json          Vercel 部署配置（/api/* rewrite 到 api/app.py）
```

> Vercel 采用官方 `api/` 目录模式：`api/app.py` 被平台自动识别为 Python Serverless Function；`index.html` 与 `tarot_images/` 留在根目录由平台静态托管。

## 本地运行

需要 Python 3.10+，以及 fastapi / uvicorn / requests / certifi。

```bash
# 推荐使用隔离虚拟环境
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 一条命令同时托管页面、牌图与 API（注意模块路径为 api.app）
uvicorn api.app:app --port 8000
```

然后浏览器打开 **http://127.0.0.1:8000**（不要用双击 `index.html`，否则图片走 file:// 协议）。

> 若 `uvicorn` 不在 PATH，用 `python -m uvicorn api.app:app --port 8000`。

## 部署到 Vercel

本项目采用 Vercel 官方 **`api/` 目录模式**，配置已就绪，无需手动写构建脚本。

### 导入时的配置项

| 配置项 | 选择 | 说明 |
| --- | --- | --- |
| Framework Preset | **Other** | 让 Vercel 完全按仓库的 `vercel.json` 走，避免框架自动探测注入冲突命令 |
| Root Directory | **`.`（仓库根目录）** | `api/`、`index.html`、`tarot_images/`、`vercel.json` 都在根，保持默认 |
| Build Command | **留空** | 无需构建前端，`api/app.py` 由 Vercel 自动识别为 Python 函数 |
| Install Command | **留默认** | Vercel 自动 `pip install -r requirements.txt`（fastapi/requests/certifi，纯 Python） |
| Output Directory | **留空** | 静态文件由平台按根目录托管 |

### 环境变量（可选）

- **`AGNES_API_KEY`**：塔罗解读用的 agnes-ai key。**不填也能跑**，会回落到代码内置的默认 key（已随仓库公开，有调用频率限制，建议自填专属 key 以获得稳定额度）。前端不再提供 key 输入入口。
- **`VERCEL`**：无需设置，平台自动注入（代码据此判断是否走本地静态托管分支）。

### 部署步骤

1. 把本目录推送到 GitHub 仓库。
2. 在 Vercel「New Project」导入该仓库，按上表确认配置（基本可一路默认）。
3. 点击 Deploy，等待构建完成。
4. 部署后：
   - 站点根路径 `/` 提供 `index.html`（书/魔杖/塔罗界面）；
   - `/api/*` 由 `api/app.py` 这个 Serverless Function 处理；
   - `tarot_images/` 由平台静态托管，前端正常加载牌图。

### 验证三处

1. 首页 `https://你的域名/` 能正常加载（不再 404）。
2. `https://你的域名/api/spreads` 浏览器直开返回 JSON 牌阵列表。
3. 抽牌 → 逐张翻完 → 点「✦ AI 全盘解读」能出文字。

> 非 Vercel 环境下（本地），`api/app.py` 通过 `VERCEL` 环境变量判断，自动接管 `/` 与 `/tarot_images` 的静态托管；
> 在 Vercel 上该分支跳过，由平台静态托管接管，函数只处理 `/api/*`。

> 历史上曾因 `vercel.json` 中使用旧的 `builds` + 仅匹配 `/api/*` 的写法，导致根目录 `index.html` 未被托管而 404 / No Production Deployment；
> 现改为 `api/` 目录模式（`builds` 警告也随之消失），该问题已解决。

## API 说明

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/spreads` | 列出所有牌阵（key / 名称 / 牌数 / 简介 / 位置） |
| POST | `/api/tarot_spread` | 请求体 `{spread_key, allow_reversed}` → 返回抽牌结果 |
| POST | `/api/tarot_interpret` | 请求体 `{reading, user_question?, api_key?}` → 返回 AI 解读 |

解读 key 优先级（服务端）：请求头 `X-Agnes-Key` → 服务端环境变量 `AGNES_API_KEY` → 内置默认 key。前端不再发送 `api_key`。

## 后续计划

- 接入「八字」（lunar_python）与「占星」（pymeeus / astronomy-engine）真实功能。
- 桌面离线版（PyInstaller 打包 exe）与 Web 版并行维护。
