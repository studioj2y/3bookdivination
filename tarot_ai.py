# -*- coding: utf-8 -*-
"""
塔罗 AI 全盘解读模块。
抽牌完成后，把整套牌阵交给 Agens AI (agnes-2.5-flash) 做整体解读。
- 针对不同牌阵使用不同的解读侧重提示词。
- 解读总字数不超过 400 字（提示词约束 + 后端硬截断双保险）。
- 依赖：标准库 + certifi（用于 HTTPS 证书）。
"""
import json
import os
import re
import ssl
import time
import urllib.request
import urllib.error

import certifi

try:
    import requests
    HAVE_REQUESTS = True
except Exception:
    HAVE_REQUESTS = False

BASE_URL = "https://apihub.agnes-ai.com/v1/chat/completions"
MODEL = "agnes-2.5-flash"

# API Key：优先读环境变量，否则用内置默认（本地工具开箱即用）。
# ⚠️ 发布到 GitHub 前请改为环境变量/配置文件，避免密钥入库。
API_KEY = os.environ.get("AGNES_API_KEY", "sk-pyxzKTbB6NgisqoyMTgOIlkRvEaUNgEsbO4H8h6R6QOEoEQ5")

MAX_CHARS = 400  # 解读总长度上限（字）

# 通用系统提示词：把牌阵当作整体解读，而非逐张复述。
SYSTEM_BASE = (
    "你是一位资深塔罗解读师，擅长把整套牌阵看作一个有机关联的整体。"
    "请用温暖、有洞察、不宿命的中文，做【全盘解读】：抓住牌与牌之间的呼应、核心议题，"
    "并给出 1–2 条可执行的建议。不要逐张复述单牌释义。"
    "使用纯中文，不要使用任何 markdown 格式（不要 # 标题、不要 **加粗**、不要列表符号）。"
    f"总字数控制在 {MAX_CHARS - 20} 字以内（约 350 字左右）。"
)

# 不同牌阵的解读侧重
SPREAD_FOCUS = {
    "three_card": "这是「过去-现在-未来」三张牌阵。请沿时间线解读：趋势如何从起因演变为现状、并走向何方。",
    "celtic_cross": "这是凯尔特十字综合牌阵（10 张）。请整合现状、挑战、潜意识动机、建议与最终结果，给出对议题的完整洞察。",
    "relationship": "这是关系牌阵（5 张）。请分别看待双方状态与关系现状、指出障碍，并给出关系走向的平和参考，保持中立、不作评判。",
    "decision": "这是抉择牌阵（5 张，含两个选项各自的走向与综合建议）。请对比两个选项的态势，给出思考框架与参考建议，而不是替用户做决定。",
    "single": "这是单张指引牌。请聚焦这张牌对当下/今日的核⼼指引，简洁有力。",
}
DEFAULT_FOCUS = "请对这套牌阵做一次整体解读，点明核心议题与可行建议。"

# 当用户提供了自己的问题时，追加到系统提示词，引导模型围绕问题解读
QUESTION_DIRECTIVE = (
    "用户带着一个【具体问题】来占卜。请【紧密结合这个问题】来解读牌阵："
    "先回应这个问题——牌阵如何映照它、给出针对性建议；"
    "若牌面与问题关联不明显，也请如实说明，并保持整体洞察。"
)


def _build_user_content(reading):
    """把抽牌结果整理成人可读的牌面描述，供模型做全盘解读。"""
    cards = reading.get("cards", [])
    parts = []
    for item in cards:
        c = item.get("card", {}) or {}
        orient = "逆位" if item.get("reversed") else "正位"
        long_text = c.get("rev_long") if item.get("reversed") else c.get("up_long")
        if not long_text:
            long_text = c.get("rev") if item.get("reversed") else c.get("up")
        parts.append(
            f"{item.get('position', '')}：{c.get('name_cn', '')}（{orient}）— {long_text or ''}"
        )
    spread_name = reading.get("spread_name", "塔罗牌阵")
    return "牌阵：" + spread_name + "\n" + "\n".join(parts) + "\n\n请基于以上牌面做一次全盘解读。"


def _urllib_post(url, headers, payload, ctx, timeout):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # 401/403 通常是 API Key 无效或被拒——给出明确提示，不再重试
        if e.code in (401, 403):
            raise RuntimeError(
                "API Key 无效或被服务端拒绝（HTTP %d）。请检查 Key 是否正确，"
                "或留空改用默认 Key。" % e.code
            )
        raise


def _post_json(url, headers, payload, timeout=60):
    """POST JSON 并返回解析后的 dict。

    采用「多传输方式 + 重试」策略，规避偶发的 TLS/网络中断
    （如 _ssl.c EOF、连接被重置）。优先用 requests（TLS 处理更稳），
    失败再回退 urllib（certifi 证书 / 系统默认证书）。
    """
    transports = []
    if HAVE_REQUESTS:
        transports.append("requests")
    transports.append("urllib_certifi")
    transports.append("urllib_default")

    last_err = None
    for attempt in range(3):
        for mode in transports:
            try:
                if mode == "requests":
                    resp = requests.post(
                        url,
                        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                        headers=headers,
                        timeout=timeout,
                        verify=certifi.where(),
                    )
                    if resp.status_code in (401, 403):
                        raise RuntimeError(
                            "API Key 无效或被服务端拒绝（HTTP %d）。请检查 Key 是否正确，"
                            "或留空改用默认 Key。" % resp.status_code
                        )
                    resp.raise_for_status()
                    return resp.json()
                elif mode == "urllib_certifi":
                    ctx = ssl.create_default_context(cafile=certifi.where())
                    return _urllib_post(url, headers, payload, ctx, timeout)
                else:
                    ctx = ssl.create_default_context()  # 使用系统默认证书
                    return _urllib_post(url, headers, payload, ctx, timeout)
            except RuntimeError:
                raise  # 认证类错误直接抛出，重试无意义
            except Exception as e:  # 该传输方式失败，换下一种
                last_err = e
                continue
        # 本轮所有方式都失败，退避后重试
        if attempt < 2:
            time.sleep(1.2 * (attempt + 1))

    # 全部失败：给出友好提示（避免把底层 urlopen 错误直接甩给用户）
    raise RuntimeError(
        "网络请求失败（SSL/连接被中断）。请检查网络后重试；"
        "若处于公司/校园网，可能需关闭代理或换网络再试。"
        f"（底层原因：{type(last_err).__name__}: {last_err}）"
    )


def _call_agnes(system_prompt, user_content, api_key=None):
    # key 优先级：调用方传入（用户自填）→ 服务端环境变量 AGNES_API_KEY → 内置默认
    key = api_key or os.environ.get("AGNES_API_KEY") or API_KEY
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": 1000,
        "temperature": 0.7,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + key,
    }
    data = _post_json(BASE_URL, headers, body)
    return data["choices"][0]["message"]["content"]


def _truncate(text, max_chars=MAX_CHARS):
    """硬截断到 max_chars 字内，尽量在句末断句。"""
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    # 在 max_chars 之前找一个句末标点切断
    cut = max_chars
    for i in range(max_chars, max(0, max_chars - 40), -1):
        if text[i - 1] in "。！？\n":
            cut = i
            break
    return text[:cut].rstrip("，、；： ") + "…"


def interpret_reading(reading, user_question=None, api_key=None):
    """对一整套牌阵做 AI 全盘解读。

    reading 为 /api/tarot 返回的结构（含 spread_key / spread_name / cards）。
    user_question 可选：用户自己的问题。若为空 / 过短 / 仅标点（视为无法理解），
    则按通用解读处理。
    api_key 可选：传入则使用调用方（用户自填）的 key；否则回落到服务端环境变量/
    内置默认。这样服务端默认 key 永不进前端代码，用户也能粘贴自己的 key。
    返回 dict: {"interpretation": str, "model": str, "spread_key": str,
                "user_question": str|None}
    """
    if not reading or not reading.get("cards"):
        raise ValueError("缺少牌面数据，无法解读")

    spread_key = reading.get("spread_key", "")
    focus = SPREAD_FOCUS.get(spread_key, DEFAULT_FOCUS)
    system_prompt = SYSTEM_BASE + "\n\n" + focus

    # 轻量"可理解性"过滤：去掉空白与标点后至少 2 个有效字符才视为有效问题
    q = (user_question or "").strip()
    clean = re.sub(r"\W", "", q)
    user_question_clean = q if len(clean) >= 2 else None

    if user_question_clean:
        system_prompt = system_prompt + "\n\n" + QUESTION_DIRECTIVE

    user_content = _build_user_content(reading)
    if user_question_clean:
        user_content = (
            user_content
            + f"\n\n【用户带来的具体问题】：{user_question_clean}\n"
            + "请围绕这个问题对牌阵做针对性解读。"
        )

    raw = _call_agnes(system_prompt, user_content, api_key=api_key)
    return {
        "interpretation": _truncate(raw, MAX_CHARS),
        "model": MODEL,
        "spread_key": spread_key,
        "user_question": user_question_clean,
    }
