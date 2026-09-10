# -*- coding: utf-8 -*-
"""
六爻（纳甲筮法 / 火珠林）计算模块

流水线：起卦 → 装卦（纳甲、六亲、世应、六神）→ 排变卦 → 参断（用神旺衰/空破）

纯 Python，仅依赖 lunar_python（取起卦日干支、节气定月建）。

本模块严格只做两件事：
  1. 装卦 —— 有固定规则、可逐条核对、各派一致（纳甲、世应、六神、旬空）。
  2. 参断中的「事实提取」—— 用神旺相休囚死、是否旬空、是否月破、动爻生克。
不做的：事件吉凶断言（「必破财」「必成」之类），那是解卦人的综合判断，
不同流派与经验差异极大，不适合由程序下结论。
"""
from datetime import datetime

from lunar_python import Solar

# ---------------- 八卦基础 ----------------
# 爻用 1=阳(—)、0=阴(--)；三爻按「初、中、上」顺序
TRIGRAMS = {
    '乾': (1, 1, 1), '兑': (1, 1, 0), '离': (1, 0, 1), '震': (1, 0, 0),
    '巽': (0, 1, 1), '坎': (0, 1, 0), '艮': (0, 0, 1), '坤': (0, 0, 0),
}
TRI_OF = {v: k for k, v in TRIGRAMS.items()}

# 八卦「自然象」（用于显示卦象说明，非断语）
TRI_SYMBOL = {'乾': '天', '兑': '泽', '离': '火', '震': '雷',
              '巽': '风', '坎': '水', '艮': '山', '坤': '地'}

# 纳支：内外卦各三爻，从初爻起（阳卦顺行、阴卦逆行，隔位取）
NA_ZHI = {
    '乾': ('子', '寅', '辰', '午', '申', '戌'),
    '震': ('子', '寅', '辰', '午', '申', '戌'),
    '坎': ('寅', '辰', '午', '申', '戌', '子'),
    '艮': ('辰', '午', '申', '戌', '子', '寅'),
    '坤': ('未', '巳', '卯', '丑', '亥', '酉'),
    '巽': ('丑', '亥', '酉', '未', '巳', '卯'),
    '离': ('卯', '丑', '亥', '酉', '未', '巳'),
    '兑': ('巳', '卯', '丑', '亥', '酉', '未'),
}
# 纳干：(内卦干, 外卦干)
NA_GAN = {'乾': ('甲', '壬'), '坤': ('乙', '癸'), '艮': ('丙', '丙'),
          '兑': ('丁', '丁'), '坎': ('戊', '戊'), '离': ('己', '己'),
          '震': ('庚', '庚'), '巽': ('辛', '辛')}

GONG_WX = {'乾': '金', '兑': '金', '离': '火', '震': '木',
           '巽': '木', '坎': '水', '艮': '土', '坤': '土'}

# 八宫卦名（序：本宫、一世…五世、游魂、归魂）
GONG_NAMES = {
    '乾': ('乾为天', '天风姤', '天山遁', '天地否', '风地观', '山地剥', '火地晋', '火天大有'),
    '兑': ('兑为泽', '泽水困', '泽地萃', '泽山咸', '水山蹇', '地山谦', '雷山小过', '雷泽归妹'),
    '离': ('离为火', '火山旅', '火风鼎', '火水未济', '山水蒙', '风水涣', '天水讼', '天火同人'),
    '震': ('震为雷', '雷地豫', '雷水解', '雷风恒', '地风升', '水风井', '泽风大过', '泽雷随'),
    '巽': ('巽为风', '风天小畜', '风火家人', '风雷益', '天雷无妄', '火雷噬嗑', '山雷颐', '山风蛊'),
    '坎': ('坎为水', '水泽节', '水雷屯', '水火既济', '泽火革', '雷火丰', '地火明夷', '地水师'),
    '艮': ('艮为山', '山火贲', '山天大畜', '山泽损', '火泽睽', '天泽履', '风泽中孚', '风山渐'),
    '坤': ('坤为地', '地雷复', '地泽临', '地天泰', '雷天大壮', '泽天夬', '水天需', '水地比'),
}
GONG_ORDER = ('乾', '兑', '离', '震', '巽', '坎', '艮', '坤')

# 世应：索引 0=本宫 … 7=归魂，值为 (世爻 1-based, 应爻 1-based)
SHI_YING = {0: (6, 3), 1: (1, 4), 2: (2, 5), 3: (3, 6),
            4: (4, 1), 5: (5, 2), 6: (4, 1), 7: (3, 6)}

YAO_NAMES = ('初爻', '二爻', '三爻', '四爻', '五爻', '上爻')

# ---------------- 五行 ----------------
ZHI_WX = {'子': '水', '丑': '土', '寅': '木', '卯': '木', '辰': '土', '巳': '火',
          '午': '火', '未': '土', '申': '金', '酉': '金', '戌': '土', '亥': '水'}
GAN_WX = {'甲': '木', '乙': '木', '丙': '火', '丁': '火', '戊': '土',
          '己': '土', '庚': '金', '辛': '金', '壬': '水', '癸': '水'}
SHENG = {'木': '火', '火': '土', '土': '金', '金': '水', '水': '木'}   # 相生
KE = {'木': '土', '土': '水', '水': '火', '火': '金', '金': '木'}       # 相克
ELES = ('金', '木', '水', '火', '土')

# 六冲 / 六合
CHONG = {'子': '午', '丑': '未', '寅': '申', '卯': '酉', '辰': '戌', '巳': '亥'}
HE6 = {'子': '丑', '寅': '亥', '卯': '戌', '辰': '酉', '巳': '申', '午': '未'}

# 六神（六兽）：按日干从初爻起排
LIUSHEN = ('青龙', '朱雀', '勾陈', '螣蛇', '白虎', '玄武')
LS_WX = {'青龙': '木', '朱雀': '火', '勾陈': '土', '螣蛇': '土', '白虎': '金', '玄武': '水'}
LS_START = {  # 日干 -> 初爻起第几个（LIUSHEN 下标）
    '甲': 0, '乙': 0,      # 青龙
    '丙': 1, '丁': 1,      # 朱雀
    '戊': 2,              # 勾陈
    '己': 3,              # 螣蛇
    '庚': 4, '辛': 4,      # 白虎
    '壬': 5, '癸': 5,      # 玄武
}
# 六亲：以卦宫五行为「我」
LIUQIN = ('父母', '兄弟', '子孙', '妻财', '官鬼')

# 旬空：日干支所在旬 -> 空亡两支
XUNKONG = {
    '甲子': ('戌', '亥'), '甲戌': ('申', '酉'), '甲申': ('午', '未'),
    '甲午': ('辰', '巳'), '甲辰': ('寅', '卯'), '甲寅': ('子', '丑'),
}
GAN_SEQ = '甲乙丙丁戊己庚辛壬癸'
ZHI_SEQ = '子丑寅卯辰巳午未申酉戌亥'

# 十二「节」-> 月建地支（六爻月建以节为界，不用农历初一）
JIE_TO_YUE = (('立春', '寅'), ('惊蛰', '卯'), ('清明', '辰'), ('立夏', '巳'),
              ('芒种', '午'), ('小暑', '未'), ('立秋', '申'), ('白露', '酉'),
              ('寒露', '戌'), ('立冬', '亥'), ('大雪', '子'), ('小寒', '丑'))

# 用神：占事类别 -> 六亲（None 表示看世爻）
YONGSHEN = {
    '求财': ('妻财', '财帛、收益、妻妾，以妻财爻为用'),
    '事业功名': ('官鬼', '官职、上司、功名，以官鬼爻为用'),
    '考试文书': ('父母', '文书、学业、长辈、契约，以父母爻为用'),
    '健康疾病': ('子孙', '医药、福德、无忧，以子孙爻为用'),
    '子女孕育': ('子孙', '子孙、孕育，以子孙爻为用'),
    '出行迁移': (None, '出行以世爻为主、兼看父母（车船文书）'),
    '官司诉讼': ('官鬼', '官司以官鬼为对方、世爻为自己'),
    '寻人失物': ('妻财', '失物一般看妻财（财物）或子孙（人）'),
    '其他': (None, '无明确用神时，以世爻为自身兼看应爻'),
}
# 女问感情用官鬼、男问感情用妻财（传统：男以财为妻，女以官为夫）
YONGSHEN_LOVE = {'男': ('妻财', '男问婚姻感情，以妻财爻为用（妻、女友）'),
                 '女': ('官鬼', '女问婚姻感情，以官鬼爻为用（夫、男友）')}


# ---------------- 卦表构建 ----------------
def _flip(yao, pos):
    y = list(yao)
    y[pos] ^= 1
    return y


def build_gua_table():
    """按「爻变法」由八宫生成 64 卦。
    本宫 → 初至五爻依次变（一世~五世）→ 五世回变四爻（游魂）→ 下卦三爻全变（归魂）。
    返回 {(上卦三爻, 下卦三爻): {name, gong, idx, shi, ying}}"""
    table = {}
    for gong in GONG_ORDER:
        tri = TRIGRAMS[gong]
        base = tuple(tri) + tuple(tri)
        seq = [base]
        cur = list(base)
        for pos in range(5):                 # 一世 ~ 五世
            cur = _flip(cur, pos)
            seq.append(tuple(cur))
        you = _flip(seq[5], 3)               # 游魂：由五世回变四爻
        seq.append(tuple(you))
        gui = list(you)
        for pos in range(3):                 # 归魂：内卦三爻全变
            gui = _flip(gui, pos)
        seq.append(tuple(gui))

        for i, y in enumerate(seq):
            low, up = y[0:3], y[3:6]
            shi, ying = SHI_YING[i]
            table[(up, low)] = {
                'name': GONG_NAMES[gong][i],
                'gong': gong,
                'idx': i,
                'shi': shi,      # 1-based
                'ying': ying,
                'yao': y,
            }
    return table


GUA_TABLE = build_gua_table()


def _bits(yao):
    """归一化六爻为 0/1 列表：兼容 [(阳,动)]、[1/0] 两种输入。"""
    out = []
    for item in yao:
        if isinstance(item, (tuple, list)):
            out.append(1 if item[0] else 0)
        else:
            out.append(1 if item else 0)
    return out


def lookup_gua(yao6):
    """六爻(初→上) -> 卦信息；未命中返回 None。"""
    y = tuple(_bits(yao6))
    if len(y) != 6:
        return None
    return GUA_TABLE.get((y[3:6], y[0:3]))


def trigram_name(tri):
    return TRI_OF.get(tuple(tri), '')


# ---------------- 起卦 ----------------
def coin_toss(rand_fn=None):
    """摇三枚铜钱一次。返回 (背数, 是否阳爻, 是否动爻, 名称)。
    规则：铜钱有字面为「正」、无字面（国徽/满文）为「背」。
      1 背 → 少阳(—)静；2 背 → 少阴(--)静；3 背 → 老阳(—○)动；0 背 → 老阴(--×)动。"""
    import random
    r = rand_fn or random.random
    backs = sum(1 for _ in range(3) if r() < 0.5)
    table = {0: (False, True, '老阴'), 1: (True, False, '少阳'),
             2: (False, False, '少阴'), 3: (True, True, '老阳')}
    yang, moving, name = table[backs]
    return backs, yang, moving, name


def cast(rand_fn=None):
    """摇六次成卦，返回 [(阳, 动), ...]（初爻→上爻）。"""
    return [coin_toss(rand_fn)[1:3] for _ in range(6)]


# ---------------- 月建 / 日辰 ----------------
def _jie_table(center_year):
    """{datetime: 节名}，覆盖 center_year ±1 年。"""
    out = {}
    alias = {'LI_CHUN': '立春', 'JING_ZHE': '惊蛰', 'QING_MING': '清明', 'LI_XIA': '立夏',
             'MANG_ZHONG': '芒种', 'XIAO_SHU': '小暑', 'LI_QIU': '立秋', 'BAI_LU': '白露',
             'HAN_LU': '寒露', 'LI_DONG': '立冬', 'DA_XUE': '大雪', 'XIAO_HAN': '小寒'}
    names = [n for n, _ in JIE_TO_YUE]
    for y in (center_year - 1, center_year, center_year + 1):
        try:
            tb = Solar.fromYmd(y, 6, 1).getLunar().getJieQiTable()
        except Exception:
            continue
        for k, v in tb.items():
            nm = alias.get(k, k)
            if nm not in names:
                continue
            try:
                dt = datetime(v.getYear(), v.getMonth(), v.getDay(),
                              v.getHour(), v.getMinute(), v.getSecond())
            except Exception:
                continue
            out[dt] = nm
    return out


def month_zhi(dt):
    """月建地支：以「节」为界（立春后为寅月…）。"""
    tb = _jie_table(dt.year)
    prev = None
    for d in sorted(tb.keys()):
        if d <= dt:
            prev = d
        else:
            break
    if prev is None:
        return '丑'   # 极端兜底：小寒前属上一年丑月
    return dict(JIE_TO_YUE)[tb[prev]]


def day_ganzhi(dt):
    """起卦日干支（以子时为界，不做早晚子分界）。"""
    lunar = Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, 0).getLunar()
    return lunar.getDayInGanZhi()


def xunkong_of(day_gz):
    """日干支所属旬的旬空两支。"""
    gi = GAN_SEQ.index(day_gz[0])
    zi = ZHI_SEQ.index(day_gz[1])
    # 旬首：找同一旬（天干地支同奇偶配对且干序=支序 mod 10 的起点）
    offset = (zi - gi) % 12
    xun_start = XUN_STARTS.get(offset)
    if not xun_start:
        return ()
    return XUNKONG.get(xun_start, ())


# 旬首对照：由 (支序-干序) mod 12 反推旬首
XUN_STARTS = {}
for _gz, _kk in XUNKONG.items():
    _g = GAN_SEQ.index(_gz[0])
    _z = ZHI_SEQ.index(_gz[1])
    XUN_STARTS[(_z - _g) % 12] = _gz


# ---------------- 装卦 ----------------
def liuqin_of(gong_wx, yao_wx):
    """六亲：以卦宫五行为我。"""
    if yao_wx == gong_wx:
        return '兄弟'
    if SHENG.get(yao_wx) == gong_wx:      # 生我
        return '父母'
    if SHENG.get(gong_wx) == yao_wx:      # 我生
        return '子孙'
    if KE.get(gong_wx) == yao_wx:         # 我克
        return '妻财'
    if KE.get(yao_wx) == gong_wx:         # 克我
        return '官鬼'
    return ''


def wangshuai_of(yao_wx, yue_wx):
    """相对月建的旺相休囚死。"""
    if yao_wx == yue_wx:
        return '旺'
    if SHENG.get(yue_wx) == yao_wx:
        return '相'
    if SHENG.get(yao_wx) == yue_wx:
        return '休'
    if KE.get(yao_wx) == yue_wx:
        return '囚'
    if KE.get(yue_wx) == yao_wx:
        return '死'
    return ''


def zhuang_gua(bit6, moving6, gong_wx, yue_zhi, ri_zhi, kong):
    """给一组六爻装：纳支、纳干、六亲、旺衰、空破。
    bit6 = [1/0]（1 阳）初→上；moving6 = [bool]。"""
    low = trigram_name(bit6[0:3])
    up = trigram_name(bit6[3:6])
    nz = list(NA_ZHI.get(low, ('',) * 6)[0:3]) + list(NA_ZHI.get(up, ('',) * 6)[3:6])
    gan_in, gan_out = NA_GAN.get(low, ('', '')), NA_GAN.get(up, ('', ''))
    yue_wx = ZHI_WX.get(yue_zhi, '')
    out = []
    for i in range(6):
        zhi = nz[i] if i < len(nz) else ''
        gan = gan_in[0] if i < 3 else gan_out[1]
        wx = ZHI_WX.get(zhi, '')
        out.append({
            'pos': i,
            'pos_name': YAO_NAMES[i],
            'yang': bool(bit6[i]),
            'moving': bool(moving6[i]) if i < len(moving6) else False,
            'zhi': zhi,
            'gan': gan,
            'ganzhi': (gan + zhi) if (gan and zhi) else zhi,
            'wx': wx,
            'liuqin': liuqin_of(gong_wx, wx),
            'wang': wangshuai_of(wx, yue_wx),
            'is_kong': zhi in kong,
            'is_yuepo': CHONG.get(zhi) == yue_zhi,
            'is_richong': CHONG.get(zhi) == ri_zhi,
        })
    return out


def compute_liuyao(yao6=None, category='其他', sex=None, dt=None, question=None):
    """主入口：起卦 → 装卦 → 变卦 → 参断（事实提取）。

    :param yao6: [(阳,动)...] 初→上；为 None 时后端自动摇卦
    :param category: 占事类别（见 YONGSHEN）
    """
    dt = dt or datetime.now()
    auto = yao6 is None
    if auto:
        yao6 = cast()
    yao6 = [(bool(a), bool(b)) for a, b in yao6]
    if len(yao6) != 6:
        return {'error': '需要 6 爻数据'}
    bit6 = _bits(yao6)
    moving6 = [bool(b) for _, b in yao6]

    ben = lookup_gua(bit6)
    if not ben:
        return {'error': '卦象解析失败'}

    gong = ben['gong']
    gong_wx = GONG_WX[gong]
    yue_zhi = month_zhi(dt)
    day_gz = day_ganzhi(dt)
    kong = xunkong_of(day_gz)
    ri_zhi = day_gz[1]

    # 本卦装卦
    ben_yao = zhuang_gua(bit6, moving6, gong_wx, yue_zhi, ri_zhi, kong)
    for i, y in enumerate(ben_yao):
        y['is_shi'] = (i + 1) == ben['shi']
        y['is_ying'] = (i + 1) == ben['ying']
    # 六神（按日干，从初爻起）
    start = LS_START.get(day_gz[0], 0)
    for i, y in enumerate(ben_yao):
        y['liushen'] = LIUSHEN[(start + i) % 6]

    # 变卦
    moving_idx = [i for i, m in enumerate(moving6) if m]
    bian = None
    if moving_idx:
        b6 = [(1 - bit6[i]) if m else bit6[i] for i, m in enumerate(moving6)]
        info = lookup_gua(b6)
        if info:
            b_yao = zhuang_gua(b6, [False] * 6, gong_wx, yue_zhi, ri_zhi, kong)  # 六亲仍依本卦宫
            for i, y in enumerate(b_yao):
                y['changed'] = i in moving_idx
                # 变卦传统不另安世应（世应只在主卦），故此处不设 is_shi / is_ying
            bian = {
                'name': info['name'], 'gong': info['gong'],
                'gong_wx': GONG_WX[info['gong']],
                'low': trigram_name(b6[0:3]), 'up': trigram_name(b6[3:6]),
                'low_symbol': TRI_SYMBOL.get(trigram_name(b6[0:3]), ''),
                'up_symbol': TRI_SYMBOL.get(trigram_name(b6[3:6]), ''),
                'yao': b_yao, 'shi': info['shi'], 'ying': info['ying'],
            }

    ben_out = {
        'name': ben['name'], 'gong': gong, 'gong_wx': gong_wx,
        'idx': ben['idx'],
        'low': trigram_name(bit6[0:3]), 'up': trigram_name(bit6[3:6]),
        'low_symbol': TRI_SYMBOL.get(trigram_name(bit6[0:3]), ''),
        'up_symbol': TRI_SYMBOL.get(trigram_name(bit6[3:6]), ''),
        'shi': ben['shi'], 'ying': ben['ying'],
        'yao': ben_yao,
        'is_youhun': ben['idx'] == 6,
        'is_guihun': ben['idx'] == 7,
    }

    # ---- 用神 ----
    if category == '感情':
        key = YONGSHEN_LOVE.get(sex or '男', YONGSHEN_LOVE['男'])
        ys_name, ys_why = key
    else:
        ys_name, ys_why = YONGSHEN.get(category, YONGSHEN['其他'])

    shi_yao = ben_yao[ben['shi'] - 1]
    ying_yao = ben_yao[ben['ying'] - 1]

    if ys_name is None:
        yong = shi_yao
        ys_label = '世爻（' + shi_yao['liuqin'] + '）'
    else:
        cands = [y for y in ben_yao if y['liuqin'] == ys_name]
        if not cands:
            yong = None
            ys_label = ys_name + '（卦中不现，须查伏神）'
        else:
            # 多现取旺相优先、动爻次之、持世再次
            rank = {'旺': 4, '相': 3, '休': 2, '囚': 1, '死': 0}
            cands.sort(key=lambda y: (rank.get(y['wang'], 0), y['moving'], y['is_shi']), reverse=True)
            yong = cands[0]
            ys_label = ys_name

    # 伏神：用神不上卦时，取本宫纯卦同六亲之爻为伏（传统「伏神法」）
    fushen = []
    if yong is None and ys_name:
        pure = list(TRIGRAMS[gong]) * 2
        pure_yao = zhuang_gua(pure, [False] * 6, gong_wx, yue_zhi, ri_zhi, kong)
        for y in pure_yao:
            if y['liuqin'] == ys_name:
                y = dict(y)
                y['from'] = '本宫' + GONG_NAMES[gong][0]
                y['wang'] = wangshuai_of(y['wx'], ZHI_WX.get(yue_zhi, ''))
                fushen.append(y)

    # ---- 事实提取（不断吉凶）----
    facts = []
    facts.append({'k': '月建', 'v': yue_zhi + '月（' + ZHI_WX[yue_zhi] + '）',
                  'd': '月建司一月之权，旺衰判定的第一参照'})
    facts.append({'k': '日辰', 'v': day_gz + '（' + ZHI_WX[ri_zhi] + '）',
                  'd': '日辰司一日之权，可生动爻、可冲实空'})
    if kong:
        facts.append({'k': '旬空', 'v': '、'.join(kong),
                      'd': '此旬中该两支落空；爻值空则力减，出空之日方实'})

    if yong:
        f = []
        f.append('旺衰：' + yong['wang'])
        if yong['is_kong']:
            f.append('旬空')
        if yong['is_yuepo']:
            f.append('月破（与月建' + yue_zhi + '相冲）')
        if yong['is_richong']:
            f.append('日冲')
        if yong['moving']:
            f.append('发动')
        if yong['is_shi']:
            f.append('持世')
        facts.append({'k': '用神（' + ys_label + '）',
                      'v': (yong['pos_name'] + ' ' + yong['ganzhi'] + ' ' + yong['liuqin']),
                      'd': '；'.join(f) or '静而平和'})
    else:
        fk = {'k': '用神（' + ys_label + '）', 'v': '本卦无此六亲',
              'd': '传统须查本宫卦的「伏神」，或用世爻参看'}
        if fushen:
            fk['v'] = '伏 ' + '、'.join(
                x['pos_name'] + ' ' + x['ganzhi'] + ' ' + x['liuqin'] + '（' + x['from'] + '）'
                for x in fushen)
            fk['d'] = '用神伏藏，须待出现（日辰/月建冲开飞神）方显其力'
        facts.append(fk)

    # 世应关系
    rel = _wx_relation(shi_yao['wx'], ying_yao['wx'])
    facts.append({'k': '世 / 应', 'v': shi_yao['pos_name'] + '（' + shi_yao['wx'] + '） / ' +
                  ying_yao['pos_name'] + '（' + ying_yao['wx'] + '）',
                  'd': '世为自己、应为对方或所问之事；二者' + rel})

    if moving_idx:
        mv = [ben_yao[i] for i in moving_idx]
        desc = '、'.join(y['pos_name'] + y['liuqin'] + ('○' if y['yang'] else '×') for y in mv)
        fx = []
        for y in mv:
            r = _wx_relation(y['wx'], yong['wx']) if yong else ''
            if r:
                fx.append(y['liuqin'] + '于用神为「' + r + '」')
        facts.append({'k': '动爻（' + str(len(mv)) + '）', 'v': desc,
                      'd': '；'.join(fx) if fx else '动爻主变化之机，须结合用神看'})
    else:
        facts.append({'k': '动爻', 'v': '无（六静卦）',
                      'd': '静卦主事态平稳、变数少，须待日辰或月建冲动'})

    # 结构提示（可核对的硬事实）
    struct = []
    if ben_out['is_youhun']:
        struct.append('游魂卦：传统主心神不定、事多反复或在外奔波')
    if ben_out['is_guihun']:
        struct.append('归魂卦：传统主事情回归、宜守成而不宜远行')
    if len([y for y in ben_yao if y['is_kong']]) >= 3:
        struct.append('卦中旬空之爻较多，多主人事未定、时机未到')
    # 内外卦六合（卦之六合：天地否? 不，是卦变六合）—— 简化：内外卦天爻地爻相合
    low_t, up_t = yao6[2], yao6[5]
    low_d, up_d = yao6[0], yao6[3]
    # 用六冲卦检测：初四、二五、三上皆冲
    bz = [ben_yao[i]['zhi'] for i in range(6)]
    if all(CHONG.get(bz[i]) == bz[i + 3] for i in range(3)):
        struct.append('六冲卦：初四、二五、三上皆相冲，主变动急速、事难持久')

    return {
        'auto_cast': auto,
        'question': question,
        'category': category,
        'sex': sex,
        'time': dt.strftime('%Y-%m-%d %H:%M'),
        'ben': ben_out,
        'bian': bian,
        'moving': moving_idx,
        'yongshen': {
            'name': ys_name, 'label': ys_label, 'why': ys_why,
            'pos': yong['pos'] if yong else None,
            'ganzhi': yong['ganzhi'] if yong else None,
            'wang': yong['wang'] if yong else None,
            'is_kong': yong['is_kong'] if yong else None,
            'is_yuepo': yong['is_yuepo'] if yong else None,
            'is_shi': yong['is_shi'] if yong else None,
        },
        'fushen': fushen,
        'facts': facts,
        'struct': struct,
        'month_zhi': yue_zhi,
        'day_gz': day_gz,
        'xunkong': list(kong),
    }


def _wx_relation(a, b):
    """a 对 b 的关系（用于描述动爻与用神、世与应）。"""
    if a == b:
        return '比和'
    if SHENG.get(a) == b:
        return '生助'
    if SHENG.get(b) == a:
        return '被生'
    if KE.get(a) == b:
        return '克制'
    if KE.get(b) == a:
        return '被克'
    return ''


if __name__ == '__main__':
    import json
    r = compute_liuyao(category='求财')
    print(json.dumps(r, ensure_ascii=False, indent=2))
