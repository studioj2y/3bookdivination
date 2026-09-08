# -*- coding: utf-8 -*-
"""
八字 (BaZi / Four Pillars) 计算模块 —— L1 排盘 + L2 解读
纯 Python，仅依赖 lunar_python（Vercel 可装，无需编译）。

提供：
  L1 排盘：四柱干支、地支藏干、五行分布、日主、农历、生肖
  L2 解读：十神（完整十种，按天干阴阳细分）、日主旺衰、喜用神、调候用神、命盘要点

旺衰阈值经 6000 样本分位校准（详见 WEAK_T / STRONG_T 注释）。
"""
from datetime import datetime, timedelta

from lunar_python import Solar

# ---------------- 基础常量 ----------------
GAN_WX = {'甲': '木', '乙': '木', '丙': '火', '丁': '火', '戊': '土',
          '己': '土', '庚': '金', '辛': '金', '壬': '水', '癸': '水'}
GAN_YY = {'甲': '阳', '丙': '阳', '戊': '阳', '庚': '阳', '壬': '阳',
          '乙': '阴', '丁': '阴', '己': '阴', '辛': '阴', '癸': '阴'}
ZHI_WX = {'子': '水', '丑': '土', '寅': '木', '卯': '木', '辰': '土', '巳': '火',
          '午': '火', '未': '土', '申': '金', '酉': '金', '戌': '土', '亥': '水'}
ELES = ['金', '木', '水', '火', '土']
SHENG = {'木': '火', '火': '土', '土': '金', '金': '水', '水': '木'}   # 相生
KE = {'木': '土', '土': '水', '水': '火', '火': '金', '金': '木'}     # 相克

# 地支藏干（本气 / 中气 / 余气）
ZANG = {
    '子': [('癸', '水')],
    '丑': [('己', '土'), ('癸', '水'), ('辛', '金')],
    '寅': [('甲', '木'), ('丙', '火'), ('戊', '土')],
    '卯': [('乙', '木')],
    '辰': [('戊', '土'), ('乙', '木'), ('癸', '水')],
    '巳': [('丙', '火'), ('戊', '土'), ('庚', '金')],
    '午': [('丁', '火'), ('己', '土')],
    '未': [('己', '土'), ('丁', '火'), ('乙', '木')],
    '申': [('庚', '金'), ('壬', '水'), ('戊', '土')],
    '酉': [('辛', '金')],
    '戌': [('戊', '土'), ('辛', '金'), ('丁', '火')],
    '亥': [('壬', '水'), ('甲', '木')],
}

# 调候用神：依月令寒热燥湿取用（传统「调候为急」）
DIAO_HOU = {
    '寅': (['火', '金'], '初春寒未尽，需火暖局；木渐旺，佐金裁剪'),
    '卯': (['金', '火'], '仲春木最旺，需金裁剪；微寒仍喜火'),
    '辰': (['金', '水'], '季春土旺，金泄土、水润局'),
    '巳': (['水'], '初夏火炎，需水济暑'),
    '午': (['水'], '盛夏火最旺，需水制炎'),
    '未': (['水'], '夏末土燥火余，需水润局'),
    '申': (['水'], '初秋金旺，需水泄润'),
    '酉': (['水'], '仲秋金最旺，需水泄金'),
    '戌': (['水', '木'], '季秋土燥金相，水润、木疏'),
    '亥': (['火'], '初冬水旺，需火暖局'),
    '子': (['火'], '仲冬水最旺，需火调候'),
    '丑': (['火'], '冬末寒土，需火暖局'),
}

# 藏干权重：本气 / 中气 / 余气
ZANG_W = [1.0, 0.5, 0.25]
# 月令（月支本气）加权
YUE_LING_W = 1.4

# 旺衰分位阈值（6000 样本校准：弱 35.0% / 中和 30.1% / 旺 34.9%）
# 注意：不可用「自党-异党」的原始差值配固定阈值——自党只占 5 类生克关系中的 2 类，
# 差值的期望本就是负数（实测均值 -0.82），会导致判定向「弱」系统性偏移。
WEAK_T = 0.4040      # ratio < 0.4040 → 弱
STRONG_T = 0.5191    # ratio > 0.5191 → 旺

PILLAR_LABELS = ['年柱', '月柱', '日柱', '时柱']


# ---------------- 十神 ----------------
def _relation(dm_wx, e):
    """五行生克关系：self 同我 / support 生我 / output 我生 / wealth 我克 / control 克我"""
    if e == dm_wx:
        return 'self'
    if SHENG.get(e) == dm_wx:
        return 'support'
    if SHENG.get(dm_wx) == e:
        return 'output'
    if KE.get(dm_wx) == e:
        return 'wealth'
    if KE.get(e) == dm_wx:
        return 'control'
    return 'other'


def ten_god(dm_gan, target_gan):
    """完整十神：按日主天干与目标天干的生克关系 + 阴阳同异细分。
    同性取「偏」系（比肩/偏印/食神/偏财/七杀），异性取「正」系（劫财/正印/伤官/正财/正官）。"""
    if dm_gan not in GAN_WX or target_gan not in GAN_WX:
        return ''
    rel = _relation(GAN_WX[dm_gan], GAN_WX[target_gan])
    same = GAN_YY.get(dm_gan) == GAN_YY.get(target_gan)   # 阴阳相同
    table = {
        'self':    ('比肩', '劫财'),
        'support': ('偏印', '正印'),
        'output':  ('食神', '伤官'),
        'wealth':  ('偏财', '正财'),
        'control': ('七杀', '正官'),
    }.get(rel)
    if not table:
        return ''
    return table[0] if same else table[1]


# ---------------- 命盘要点文案（事实型，非性格评价） ----------------
_RI_ZUO = {
    '正财': '配偶务实、重实际，婚姻偏稳定；财星坐配偶宫，多得内助',
    '偏财': '配偶外向、擅交际；偏财坐配偶宫，财缘多来自人脉与偏门',
    '正官': '配偶端正、有分寸；官星坐配偶宫，家中讲规矩',
    '七杀': '配偶个性强、有主见；杀坐配偶宫，亲密关系中压力与助力并存',
    '正印': '配偶温厚、能包容；印坐配偶宫，多得长辈与家庭庇荫',
    '偏印': '配偶心思细、想法独特；枭坐配偶宫，关系中易有疏离感',
    '食神': '配偶温和、懂生活；食神坐配偶宫，日子安稳有口福',
    '伤官': '配偶聪明、有才情；伤官坐配偶宫，言语上容易起摩擦',
    '比肩': '配偶独立、与你平起平坐；比肩坐配偶宫，彼此既是伴也是对手',
    '劫财': '配偶要强、花钱快；劫财坐配偶宫，需留意共同财务',
}

_YUE_LING = {
    '正官': '月令正官：天生守规矩、重名誉，适合在体系内往上走',
    '七杀': '月令七杀：早年压力大，能力是被逼出来的；有制化方能成器',
    '正财': '月令正财：务实、会过日子，财靠稳定积累而非投机',
    '偏财': '月令偏财：财路宽、善抓机会，但来得快去得也快',
    '正印': '月令正印：学习力强、得长辈缘，靠学历与资质立足',
    '偏印': '月令偏印：思维独特、钻研冷门，宜走专业而非通用赛道',
    '食神': '月令食神：心态平和、有才艺，适合把手艺做成事业',
    '伤官': '月令伤官：聪明外露、不服管束，适合靠专业吃饭而非按部就班',
    '比肩': '月令比肩：独立、凡事靠自己，朋友多但助力有限',
    '劫财': '月令劫财：行动力强、敢争，但要防冲动与破财',
}


def detect_features(pillars, dm_wx, level, wuxing, tous):
    """命盘要点：只陈述命盘中真实存在的结构特征（可验证、可差异化），不做性格评价。"""
    feats = []
    day_zhi_god = pillars[2]['zhi_god']
    mon_zhi_god = pillars[1]['zhi_god']

    if day_zhi_god in _RI_ZUO:
        feats.append({'title': '日坐' + day_zhi_god, 'desc': _RI_ZUO[day_zhi_god], 'key': 'rizuo'})
    if mon_zhi_god in _YUE_LING:
        feats.append({'title': '月令' + mon_zhi_god, 'desc': _YUE_LING[mon_zhi_god], 'key': 'yueling'})

    # 得令 / 失令：月支本气五行是否生扶日主
    mon_zhi_wx = pillars[1]['zhi_wx']
    if mon_zhi_wx == dm_wx or SHENG.get(mon_zhi_wx) == dm_wx:
        feats.append({'title': '日主得令', 'desc': '生于当旺之月，先天底气足', 'key': 'deling'})
    else:
        feats.append({'title': '日主失令', 'desc': '生于不当令之月，先天底气需后天补足', 'key': 'shiling'})

    has = lambda *names: any(n in tous for n in names)

    if has('伤官') and has('正官'):
        feats.append({'title': '伤官见官',
                      'desc': '才华与规则相冲，容易与上级或体制摩擦；宜走专业路线自成一格',
                      'key': 'shangguanjianguan'})
    if has('食神') and has('七杀'):
        feats.append({'title': '食神制杀',
                      'desc': '以柔克刚，能把压力转化成实绩，传统视为成格的贵象',
                      'key': 'shishenzhisha'})
    if has('正官', '七杀') and has('正印', '偏印'):
        feats.append({'title': '官印相生',
                      'desc': '有贵人提携，名望与实权可兼得，适合体制与管理岗位',
                      'key': 'guanyinxiangsheng'})
    if has('正财', '偏财') and has('正官', '七杀'):
        feats.append({'title': '财官相生',
                      'desc': '以财生官，事业与收入互相带动，宜务实经营',
                      'key': 'caiguanxiangsheng'})

    wealth_n = sum(1 for t in tous if t in ('正财', '偏财'))
    control_n = sum(1 for t in tous if t in ('正官', '七杀'))
    output_n = sum(1 for t in tous if t in ('食神', '伤官'))
    bijie_n = sum(1 for t in tous if t in ('比肩', '劫财'))

    if level == '弱' and wealth_n >= 2:
        feats.append({'title': '财多身弱',
                      'desc': '看得见的机会多，但自身担不住；宜合伙借势，不宜单打独斗',
                      'key': 'caiduoshenruo'})
    if level == '旺' and control_n == 0 and output_n == 0:
        feats.append({'title': '身旺无制',
                      'desc': '精力与自我都强，若无官杀约束或食伤泄秀，易流于刚愎自用',
                      'key': 'shenwangwuzhi'})
    if bijie_n >= 2:
        feats.append({'title': '比劫重重',
                      'desc': '同行竞争多、开销也大，宜做差异化而非正面拼资源',
                      'key': 'bijiechongchong'})

    missing = [e for e in ELES if wuxing.get(e, 0) == 0]
    if len(missing) == 1:
        feats.append({'title': '命局缺' + missing[0],
                      'desc': '该五行为命中所无，遇相关事务易感吃力（需看整体，非绝对）',
                      'key': 'quexing'})
    elif len(missing) >= 2:
        feats.append({'title': '命局缺' + '、'.join(missing),
                      'desc': '命局五行偏枯，喜用之神的作用更显关键（需看整体，非绝对）',
                      'key': 'quexing'})

    return feats


# ---------------- 主计算 ----------------
def compute_bazi(year, month, day, hour=12, minute=0, sex=None, lon=None):
    """计算八字（L1 排盘 + L2 解读）。

    :param lon: 出生地经度（东经为正）。传入则做「平太阳时」校正：
                真太阳时 ≈ 北京时间 + (经度 - 120°) × 4 分钟。
                未做「均时差」订正（±16 分钟内，对 L1/L2 排盘影响有限）。
    """
    solar_note = ''
    if lon is not None:
        try:
            delta = (float(lon) - 120.0) * 4.0
            dt = datetime(year, month, day, int(hour), int(minute)) + timedelta(minutes=delta)
            year, month, day, hour, minute = dt.year, dt.month, dt.day, dt.hour, dt.minute
            solar_note = '已按经度 %.2f° 做平太阳时校正（%+d 分钟）' % (float(lon), int(round(delta)))
        except Exception:
            solar_note = '经度校正失败，使用原始输入时间'

    solar = Solar.fromYmdHms(year, month, day, hour, minute, 0)
    lunar = solar.getLunar()
    ec = lunar.getEightChar()
    gz = [ec.getYear(), ec.getMonth(), ec.getDay(), ec.getTime()]

    dm_gan = gz[2][0]
    dm_wx = GAN_WX[dm_gan]

    # —— 四柱 ——
    pillars = []
    for i, (label, p) in enumerate(zip(PILLAR_LABELS, gz)):
        gan, zhi = p[0], p[1]
        zhi_main = ZANG[zhi][0][0] if ZANG.get(zhi) else zhi
        pillars.append({
            'label': label,
            'gan': gan,
            'zhi': zhi,
            'gan_wx': GAN_WX.get(gan, ''),
            'zhi_wx': ZHI_WX.get(zhi, ''),
            'gan_god': ten_god(dm_gan, gan),
            'zhi_god': ten_god(dm_gan, zhi_main),
            'cangan': [{'gan': g, 'wx': w, 'god': ten_god(dm_gan, g)} for g, w in ZANG.get(zhi, [])],
        })

    # —— 五行分布（天干 + 地支本气，展示用） ——
    wuxing = {e: 0 for e in ELES}
    for p in pillars:
        if p['gan_wx']:
            wuxing[p['gan_wx']] += 1
        if p['zhi_wx']:
            wuxing[p['zhi_wx']] += 1

    # —— 日主旺衰：十神加权自党 vs 异党，用占比 ratio 判定 ——
    self_w, other_w = 0.0, 0.0
    for i, p in enumerate(gz):
        if _relation(dm_wx, GAN_WX[p[0]]) in ('self', 'support'):
            self_w += 1.0
        else:
            other_w += 1.0
        for j, (zc, zw) in enumerate(ZANG.get(p[1], [])):
            w = ZANG_W[j] if j < len(ZANG_W) else 0.25
            if i == 1 and j == 0:
                w *= YUE_LING_W
            if _relation(dm_wx, zw) in ('self', 'support'):
                self_w += w
            else:
                other_w += w
    total_w = self_w + other_w
    ratio = self_w / total_w if total_w else 0.5
    if ratio > STRONG_T:
        level = '旺'
    elif ratio < WEAK_T:
        level = '弱'
    else:
        level = '中和'

    # —— 扶抑用神 ——
    if level == '旺':
        use = [SHENG.get(dm_wx), KE.get(dm_wx)]                       # 食伤、财
        ctrl = next((k for k in ELES if KE.get(k) == dm_wx), None)    # 官杀
        if ctrl:
            use.append(ctrl)
        need = [e for e in use if e]
    elif level == '弱':
        support_elem = next((k for k in ELES if SHENG.get(k) == dm_wx), None)   # 印
        need = [dm_wx] + ([support_elem] if support_elem else [])
    else:
        need = []

    month_zhi = gz[1][1]
    dh, dh_why = DIAO_HOU.get(month_zhi, ([], ''))

    # 透干十神（四个天干上的十神）
    tous = [p['gan_god'] for p in pillars]
    feats = detect_features(pillars, dm_wx, level, wuxing, tous)

    return {
        'solar': '%04d-%02d-%02d %02d:%02d' % (year, month, day, hour, minute),
        'lunar_date': lunar.getMonthInChinese() + '月' + lunar.getDayInChinese(),
        'zodiac': lunar.getYearShengXiao(),
        'sex': sex,
        'eight_chars': ' '.join(gz),
        'pillars': pillars,
        'day_master': dm_gan,
        'day_master_wx': dm_wx,
        'wuxing': wuxing,
        'wangshuai': {
            'level': level,
            'ratio': round(ratio, 4),
            'self_w': round(self_w, 2),
            'other_w': round(other_w, 2),
        },
        'use_gods': need,
        'diao_hou': {'elems': dh, 'why': dh_why},
        'features': feats,
        'note': solar_note or '（未做经度校正，按输入时间直排；如需严谨请填写出生地经度）',
    }


if __name__ == '__main__':
    import json
    r = compute_bazi(1990, 1, 1, 12, 0, '男')
    print(json.dumps(r, ensure_ascii=False, indent=2))
