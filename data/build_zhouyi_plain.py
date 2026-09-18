# -*- coding: utf-8 -*-
"""构建 api/zhouyi_plain.py —— 把 data/zhouyi_plain_p1..p4.py 合并、校验后落盘。

为什么要有这个脚本（而不是直接手写 api/zhouyi_plain.py）：
  · 白话由人工分批撰写（data/zhouyi_plain_pN.py），必须与 api/zhouyi.py 的
    **卦名与爻序严格对齐**，逐条核对不可靠 —— 交给脚本做集合/长度/字串校验；
  · 校验不过就**不写文件**，避免半成品混进后端。

用法：
    python data/build_zhouyi_plain.py          # 校验并生成
    python data/build_zhouyi_plain.py --check   # 只校验，不写文件
"""

import argparse
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
API = os.path.join(ROOT, 'api')

MIN_GUA = 20   # 卦级白话最少字数
MIN_YAO = 8    # 爻级白话最少字数


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def collect():
    """合并 4 批白话，返回 {卦名: {gua, yao}}。"""
    merged = {}
    dupes = []
    for i in (1, 2, 3, 4):
        p = os.path.join(HERE, 'zhouyi_plain_p%d.py' % i)
        if not os.path.exists(p):
            raise SystemExit('缺少 %s' % p)
        mod = _load(p, '_plain_p%d' % i)
        for k, v in mod.PLAIN.items():
            if k in merged:
                dupes.append(k)
            merged[k] = v
    if dupes:
        raise SystemExit('重复条目：%s' % '、'.join(dupes))
    return merged


def validate(merged, gua_text):
    errs = []
    miss = [k for k in gua_text if k not in merged]
    extra = [k for k in merged if k not in gua_text]
    if miss:
        errs.append('缺少 %d 卦：%s' % (len(miss), '、'.join(miss)))
    if extra:
        errs.append('多出 %d 卦：%s' % (len(extra), '、'.join(extra)))

    for name, d in gua_text.items():
        p = merged.get(name)
        if not p:
            continue
        g = (p.get('gua') or '').strip()
        if len(g) < MIN_GUA:
            errs.append('%s: 卦级白话过短（%d 字）' % (name, len(g)))
        ys = p.get('yao') or []
        src = d.get('yao') or []
        if len(ys) != len(src):
            errs.append('%s: 爻白话 %d 条，原文 %d 条，对不上' % (name, len(ys), len(src)))
            continue
        for i, t in enumerate(ys):
            t = (t or '').strip()
            if len(t) < MIN_YAO:
                errs.append('%s 第%d爻: 白话过短（%d 字）' % (name, i + 1, len(t)))
            # 白话不该整段照抄原文（漏写时的典型症状）
            if t and t == (src[i] or '').strip():
                errs.append('%s 第%d爻: 白话与原文完全相同' % (name, i + 1))
    return errs


def emit(merged, gua_text, out_path):
    lines = []
    lines.append('# -*- coding: utf-8 -*-')
    lines.append('"""周易 64 卦白话义（**由 data/build_zhouyi_plain.py 生成，勿手改**）。')
    lines.append('')
    lines.append('源文件：data/zhouyi_plain_p1..p4.py；原文：api/zhouyi.py。')
    lines.append('白话只做「翻译与意象说明」，不含断语、不判断用户所问之事。')
    lines.append('"""')
    lines.append('')
    lines.append('PLAIN = {')
    for name in gua_text:                     # 依 api/zhouyi.py 的八宫次序，保证 diff 稳定
        d = merged[name]
        lines.append("    %s: {" % _q(name))
        lines.append("        'gua': %s," % _q(d['gua'].strip()))
        lines.append("        'yao': [")
        for t in d['yao']:
            lines.append('            %s,' % _q(t.strip()))
        lines.append('        ],')
        lines.append('    },')
    lines.append('}')
    lines.append('')
    lines.append('')
    lines.append('def self_check():')
    lines.append('    """自查：64 卦齐全、每卦 6 爻、无空串。返回 (ok, 消息)。"""')
    lines.append('    if len(PLAIN) != 64:')
    lines.append("        return False, '卦数 %d，应为 64' % len(PLAIN)")
    lines.append('    for name, d in PLAIN.items():')
    lines.append("        if not (d.get('gua') or '').strip():")
    lines.append("            return False, '%s 卦级白话为空' % name")
    lines.append("        ys = d.get('yao') or []")
    lines.append('        if len(ys) != 6:')
    lines.append("            return False, '%s 爻白话 %d 条，应为 6' % (name, len(ys))")
    lines.append('        for i, t in enumerate(ys):')
    lines.append('            if not (t or "").strip():')
    lines.append("                return False, '%s 第%d爻白话为空' % (name, i + 1)")
    lines.append("    return True, '64 卦 × 6 爻白话齐备'")
    lines.append('')

    with open(out_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines))
    return len(lines)


def _q(s):
    """写成 Python 字符串字面量：单引号、转义反斜杠与单引号。"""
    s = s.replace('\\', '\\\\').replace("'", "\\'")
    return "'" + s + "'"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true', help='只校验，不写文件')
    args = ap.parse_args()

    sys.path.insert(0, API)
    import zhouyi  # noqa: E402

    merged = collect()
    errs = validate(merged, zhouyi.GUA_TEXT)
    if errs:
        print('校验未通过：')
        for e in errs[:40]:
            print('  × ' + e)
        raise SystemExit(1)

    n_gua = len(merged)
    n_yao = sum(len(v['yao']) for v in merged.values())
    print('校验通过：%d 卦 / %d 爻白话，卦名与爻序均与 api/zhouyi.py 对齐' % (n_gua, n_yao))

    if args.check:
        return
    out = os.path.join(API, 'zhouyi_plain.py')
    n = emit(merged, zhouyi.GUA_TEXT, out)
    print('已生成 %s（%d 行）' % (os.path.relpath(out, ROOT), n))


if __name__ == '__main__':
    main()
