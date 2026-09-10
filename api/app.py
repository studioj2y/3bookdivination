# -*- coding: utf-8 -*-
"""
全自动算命机 · 塔罗后端（B 路线：Vercel Python Serverless Function）

采用 FastAPI 框架式入口（Vercel 原生支持）：
- GET  /api/spreads         列出所有牌阵（key/名称/牌数/简介/位置）
- POST /api/tarot_spread    按牌阵抽牌，返回结构化牌面
- POST /api/tarot_interpret 对牌阵做 AI 全盘解读

AI key 透传设计：
- 前端可随请求带 api_key（用户自填），或 header `X-Agnes-Key`；
- 都不带时回落到服务端环境变量 AGNES_API_KEY（在 Vercel 后台设置，永不进前端代码）。
"""
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os
import sys

# 把本文件所在目录（api/）加入路径，使 `import tarot` / `import tarot_ai` 在
# 本地 `uvicorn api.app:app` 与 Vercel Serverless 两种运行方式下都能解析。
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tarot
import tarot_ai
import bazi
import liuyao

app = FastAPI(title="全自动算命机 API")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))   # 本文件所在目录（api/）
ROOT_DIR = os.path.dirname(BASE_DIR)                       # 项目根目录（index.html / tarot_images 所在）

# 本地开发：用一条 `uvicorn api.app:app` 同时托管前端页面、塔罗图片与 /api。
# Vercel 上由平台静态托管接管（不进此分支，避免覆盖函数路由 / 静态资源）。
if not os.environ.get("VERCEL"):
    @app.get("/")
    def index():
        return FileResponse(os.path.join(ROOT_DIR, "index.html"))
    app.mount(
        "/tarot_images",
        StaticFiles(directory=os.path.join(ROOT_DIR, "tarot_images")),
        name="tarot_images",
    )

# 开发期放开 CORS（本地前端与 API 可能不同端口）；生产环境同域，无影响。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/spreads")
def list_spreads():
    """返回所有可用牌阵的元信息，供前端下拉框使用。"""
    out = []
    for key, s in tarot.SPREADS.items():
        out.append({
            "key": key,
            "name": s["name"],
            "size": s["size"],
            "desc": s["desc"],
            "positions": s["positions"],
        })
    return {"spreads": out}


@app.post("/api/tarot_spread")
async def tarot_spread(req: Request):
    data = await req.json()
    key = data.get("spread_key") or data.get("spread") or "three_card"
    allow_reversed = bool(data.get("allow_reversed", True))
    reading = tarot.draw(key, allow_reversed=allow_reversed)
    # 附带版本标记，便于前端判断
    reading["service"] = "tarot"
    return reading


@app.post("/api/tarot_interpret")
async def tarot_interpret(req: Request):
    data = await req.json()
    reading = data.get("reading")
    question = data.get("user_question") or data.get("question") or None
    # key 透传：请求体 api_key 优先，其次 header X-Agnes-Key
    api_key = data.get("api_key") or req.headers.get("X-Agnes-Key") or None
    try:
        result = tarot_ai.interpret_reading(
            reading, user_question=question, api_key=api_key
        )
        return result
    except Exception as e:  # 网络/密钥无效等：返回结构化错误，前端友好提示
        return {"error": str(e)}


@app.post("/api/bazi")
async def bazi_calc(req: Request):
    """八字排盘 + 解读 + 大运流年（纯本地计算，零 AI、零外部依赖）。

    入参：year, month, day, hour(0-23), minute, sex, lon(出生地经度，可选)
    lon 传入时按「平太阳时 + 均时差」校正为真太阳时。
    可选：dayun_n(大运步数，默认10)、ly_from/ly_to(流年区间，默认当前年 -6 ~ +15)
    """
    data = await req.json()
    try:
        year = int(data.get("year"))
        month = int(data.get("month"))
        day = int(data.get("day"))
        hour = int(data.get("hour", 12))
        minute = int(data.get("minute", 0))
        sex = data.get("sex") or None
        lon = data.get("lon")
        lon = float(lon) if lon not in (None, "", 0) else None

        def _int(v, default=None):
            try:
                return int(v)
            except (TypeError, ValueError):
                return default

        result = bazi.compute_bazi(
            year, month, day, hour, minute, sex=sex, lon=lon,
            dayun_n=_int(data.get("dayun_n"), 10) or 10,
            ly_from=_int(data.get("ly_from")),
            ly_to=_int(data.get("ly_to")),
        )
        result["service"] = "bazi"
        return result
    except Exception as e:
        return {"error": "排盘失败：%s" % e}


@app.post("/api/liuyao")
async def liuyao_calc(req: Request):
    """六爻起卦 / 装卦 / 参断（纯本地计算，零 AI）。

    入参：
      yao     可选，[[阳(bool), 动(bool)], ...] 初爻→上爻；不传则由后端摇卦
      category 占事类别（求财 / 事业功名 / 考试文书 / 健康疾病 / 子女孕育 /
                       出行迁移 / 官司诉讼 / 寻人失物 / 感情 / 其他）
      sex     问卦人性别（category=感情 时用于定用神）
      question 所问之事（原样回传，便于展示）
    只做装卦与事实提取（旺衰/空破/动爻/世应），不断吉凶。
    """
    data = await req.json()
    try:
        yao = data.get("yao")
        if yao:
            yao = [(bool(a), bool(b)) for a, b in yao]
            if len(yao) != 6:
                return {"error": "需要 6 爻数据"}
        result = liuyao.compute_liuyao(
            yao6=yao,
            category=data.get("category") or "其他",
            sex=data.get("sex") or None,
            question=data.get("question") or None,
        )
        if isinstance(result, dict) and "error" in result:
            return result
        result["service"] = "liuyao"
        return result
    except Exception as e:
        return {"error": "起卦失败：%s" % e}
