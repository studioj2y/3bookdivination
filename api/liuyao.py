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

try:                    # 卦爻辞静态数据（通行本）。缺失时降级为不提供，不影响装卦。
    import zhouyi
except Exception:       # pragma: no cover - 仅在数据文件被剔除时触发
    zhouyi = None

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


# ---------------- 进阶规则用表 ----------------
import itertools as _it

# 三合局：三支 -> 所化五行
SANHE = {('申', '子', '辰'): '水', ('亥', '卯', '未'): '木',
         ('寅', '午', '戌'): '火', ('巳', '酉', '丑'): '金'}
# 半合 / 拱合：同一局中任意两支（生地半合、墓地半合、拱合力度递减，此处统一记作「待合」）
BANHE = {}
for _trio, _wx in SANHE.items():
    for _pair in _it.combinations(_trio, 2):
        BANHE[frozenset(_pair)] = _wx
# 半合细分：含「生支」为生地半合，含「墓支」为墓地半合，余为拱合
SANHE_PARTS = {('申', '子', '辰'): ('子', '辰'), ('亥', '卯', '未'): ('卯', '未'),
               ('寅', '午', '戌'): ('午', '戌'), ('巳', '酉', '丑'): ('酉', '丑')}

# 三刑 / 自刑 / 六害
XING_TRIO = (('寅', '巳', '申', '无恩之刑'), ('丑', '戌', '未', '恃势之刑'))
XING_PAIR = {frozenset(('子', '卯')): '无礼之刑'}
ZI_XING = ('辰', '午', '酉', '亥')
HAI_PAIR = {frozenset(p) for p in
            (('子', '未'), ('丑', '午'), ('寅', '巳'), ('卯', '辰'), ('申', '亥'), ('酉', '戌'))}

# 进神 / 退神（动爻化出地支）
JIN = {'亥': '子', '丑': '辰', '寅': '卯', '辰': '未',
       '巳': '午', '未': '戌', '申': '酉', '戌': '丑'}
TUI = {v: k for k, v in JIN.items()}

# 五行墓库（土墓传统有两派：随水在辰 / 随火在戌；此处取通行的「土随水墓辰」）
MU = {'水': '辰', '木': '未', '火': '戌', '金': '丑', '土': '辰'}
# 十二长生之「绝」
JUE = {'木': '申', '火': '亥', '金': '寅', '水': '巳', '土': '巳'}

# ---------------- 神煞（以日支起，三合局定位）----------------
# 驿马：三合局长生位之冲。申子辰马在寅、寅午戌马在申、巳酉丑马在亥、亥卯未马在巳。
YIMA = {}
for _trio, _ma in ((('申', '子', '辰'), '寅'), (('寅', '午', '戌'), '申'),
                   (('巳', '酉', '丑'), '亥'), (('亥', '卯', '未'), '巳')):
    for _z in _trio:
        YIMA[_z] = _ma
# 桃花（咸池）：三合局沐浴位。申子辰在酉、寅午戌在卯、巳酉丑在午、亥卯未在子。
TAOHUA = {}
for _trio, _th in ((('申', '子', '辰'), '酉'), (('寅', '午', '戌'), '卯'),
                   (('巳', '酉', '丑'), '午'), (('亥', '卯', '未'), '子')):
    for _z in _trio:
        TAOHUA[_z] = _th

# 神煞释义与「何类所主」（只陈述传统所指，不作吉凶断言）
SHENSHA_META = {
    '驿马': {'desc': '驿马主动移、出行、奔波与职位迁转。以日支所属三合局取「长生位之冲」，'
                     '如申子辰日马在寅。传统以「用神临马」与出行迁移之事相参。',
             'cats': ('出行迁移',)},
    '桃花': {'desc': '桃花（咸池）主人缘、情缘与外在名声。以日支所属三合局取「沐浴位」，'
                     '如申子辰日桃花在酉。传统以「用神临桃花」与感情、交际之事相参。',
             'cats': ('感情',)},
}


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


def detect_advanced(ben_yao, bian_yao, moving_idx, yue_zhi, ri_zhi, kong, key_pos=None):
    """进阶规则：暗动/日破、入墓、化进退、化回头生克、化墓化绝、三合刑害。

    只标记「卦中确实存在且可核对」的结构，不判吉凶。三条收紧口径：
      · 入墓 —— 只论月建 / 日辰之墓（动而化墓另算），且只看世、应、用神、动爻
      · 三合 —— 必须有动爻参与：二爻动成真局、一爻动为待成、全静仅具其象
      · 六害 —— 只列涉及世、应、用神、动爻的组合，避免满屏噪音
    返回 {'flags': {yid: [flag...]}, 'combos': [...], 'xing': [...], 'hai': [...]}
    """
    flags = {}

    def add(pos, code, name, desc):
        flags.setdefault(int(pos), []).append(
            {'code': code, 'name': name, 'desc': desc})

    kong = tuple(kong or ())
    key_pos = set(key_pos or ())

    # 本卦地支（刑害只论本卦）；本+变（合局可含动爻化出之支）
    ben_zhis = [y['zhi'] for y in ben_yao]
    ben_set = set(z for z in ben_zhis if z)
    all_zhis = list(ben_zhis)
    if bian_yao:
        all_zhis += [y['zhi'] for y in bian_yao]
    zhi_set = set(z for z in all_zhis if z)
    # 该支是否有动爻（三合成局与否的判据）
    zhi_moving = {}
    for y in ben_yao:
        zhi_moving.setdefault(y['zhi'], False)
        if y.get('moving'):
            zhi_moving[y['zhi']] = True
    ext_zhis = {'月建' + yue_zhi: yue_zhi, '日辰' + ri_zhi: ri_zhi}

    for i, y in enumerate(ben_yao):
        zhi, wx = y.get('zhi', ''), y.get('wx', '')

        # ---- 静爻：暗动 / 日破 ----
        if not y.get('moving') and y.get('is_richong'):
            if y.get('wang') in ('旺', '相'):
                add(i, 'andong', '暗动',
                    '%s被日辰%s相冲，爻旺而受冲为「暗动」——静而实动，传统视之为暗中发力、事有突发之象'
                    % (zhi, ri_zhi))
            else:
                add(i, 'ripo', '日破',
                    '%s被日辰%s相冲，爻值%s无力受冲为「日破」——衰极而被冲散，其力难用'
                    % (zhi, ri_zhi, y.get('wang') or ''))

        # ---- 入墓：只论月建 / 日辰之墓，且限于世、应、用神、动爻 ----
        mu = MU.get(wx)
        if mu and i in key_pos:
            src = [lbl for lbl, ez in ext_zhis.items() if ez == mu]
            if src:
                add(i, 'ruMu', '入墓',
                    '%s（%s）墓在%s，今值%s——墓者力藏而不显，须待冲开墓库方得用'
                    % (zhi, wx, mu, '、'.join(src)))

        # ---- 空 + 月破 ----
        if y.get('is_kong') and y.get('is_yuepo'):
            add(i, 'kongpo', '空破',
                '既值旬空又遭月建%s冲破，古称「空破」，其力近乎全失' % yue_zhi)

        # ---- 动爻：化出之爻的诸般变化 ----
        if y.get('moving') and bian_yao and i < len(bian_yao):
            b = bian_yao[i]
            bz, bwx = b.get('zhi', ''), b.get('wx', '')
            if JIN.get(zhi) == bz:
                add(i, 'huajin', '化进',
                    '%s化%s为「进神」——由微向盛，其势方长' % (zhi, bz))
            elif TUI.get(zhi) == bz:
                add(i, 'huatui', '化退',
                    '%s化%s为「退神」——由盛向衰，其势渐消' % (zhi, bz))
            elif bz == zhi:
                add(i, 'fuyin', '化伏吟',
                    '%s化%s为「伏吟」——动而复止，主迟滞、反复、内心不安' % (zhi, bz))
            elif CHONG.get(zhi) == bz:
                add(i, 'fanyin', '化反吟',
                    '%s化%s为「反吟」（相冲）——动而相冲，主反复不定、事有回头' % (zhi, bz))

            if bwx and wx:
                if SHENG.get(bwx) == wx:
                    add(i, 'huitousheng', '回头生',
                        '化出之%s（%s）生本爻%s（%s），为「回头生」——动而得助'
                        % (bz, bwx, zhi, wx))
                elif KE.get(bwx) == wx:
                    add(i, 'huitouke', '回头克',
                        '化出之%s（%s）克本爻%s（%s），为「回头克」——动而自伤，古称「化鬼」'
                        % (bz, bwx, zhi, wx))
                elif SHENG.get(wx) == bwx:
                    add(i, 'huaxie', '化泄',
                        '本爻%s（%s）生化出之%s（%s），为「化泄」——动而泄气，力有减损'
                        % (zhi, wx, bz, bwx))

            if bz and bz == MU.get(wx):
                add(i, 'huamu', '化墓',
                    '动而化入墓库%s——化墓者结局收敛，事虽成而难显' % bz)
            if bz and bz == JUE.get(wx):
                add(i, 'huajue', '化绝',
                    '动而化%s为「化绝」——绝者气尽，古法视之为凶象之一' % bz)
            if bz and bz in kong:
                add(i, 'huakong', '化空',
                    '动而化入旬空%s——化空者结局落空，须待出空' % bz)
            if bz and CHONG.get(bz) == yue_zhi:
                add(i, 'huapo', '化破',
                    '化出之%s遭月建%s冲破——化破者结局破损' % (bz, yue_zhi))

    # ---- 三合局 / 半合 / 拱合（须有动爻参与方成局）----
    def _tag(z):
        if z not in ben_set:
            return z + '（化出）'
        return z + '（动）' if zhi_moving.get(z) else z

    combos = []
    for trio, wx in SANHE.items():
        trio_s = set(trio)
        present = trio_s & zhi_set                       # 卦中实有的支
        n_mv = sum(1 for z in trio_s if zhi_moving.get(z))
        borrowed = None
        if len(present) < 3:
            for lbl, ez in ext_zhis.items():             # 借月建 / 日辰凑足
                if ez in trio_s and (trio_s - {ez}) <= zhi_set:
                    borrowed = lbl
                    break
        complete = (len(present) == 3) or (borrowed is not None)

        if complete and n_mv >= 1:
            where = [_tag(z) for z in trio if z in present]
            tail = '，借%s凑足' % borrowed if borrowed else ''
            if n_mv >= 2:
                level, note = '成局', '动爻会聚，合化有力'
            else:
                level, note = '待成', '仅一爻动，须再动方成真局'
            combos.append({'type': '三合局', 'wx': wx, 'level': level,
                           'desc': '%s 三支%s，合化%s局%s——%s'
                                   % ('·'.join(trio), '、'.join(where), wx, tail, note)})
            continue

        # 未成局：看两支的半合 / 拱合
        for pair in _it.combinations(trio, 2):
            if set(pair) <= zhi_set:
                wang, mu_z = SANHE_PARTS[trio]
                if wang in pair:
                    kind = '生地半合'
                elif mu_z in pair:
                    kind = '墓地半合'
                else:
                    kind = '拱合'
                lacks = (trio_s - set(pair)).pop()
                if n_mv >= 1:
                    tail = '有动爻参与，待%s值时可望成局' % lacks
                    combos.append({'type': kind, 'wx': wx, 'level': '待合',
                                   'desc': '%s·%s 为%s，缺%s一支——%s'
                                           % (_tag(pair[0]), _tag(pair[1]), kind, lacks, tail)})
                # 全静无动的半合 / 拱合：传统「不得作合论」，不输出
                break

    # ---- 三刑 / 自刑（只论本卦）----
    xing = []
    for a, b, c, nm in XING_TRIO:
        if {a, b, c} <= ben_set:
            xing.append({'name': nm, 'desc': '卦中%s·%s·%s 俱全，为「%s」——刑主动伤、纠葛与不顺'
                                             % (a, b, c, nm)})
    for pair, nm in XING_PAIR.items():
        p = set(pair)
        if p <= ben_set:
            xing.append({'name': nm, 'desc': '卦中%s·%s 相见，为「%s」' % (tuple(p)[0], tuple(p)[1], nm)})
    for z in ZI_XING:
        if ben_zhis.count(z) >= 2:
            xing.append({'name': '自刑', 'desc': '卦中%s 两见，为「自刑」——主自我纠结、内耗' % z})

    # ---- 六害（相穿）：只论本卦，且须涉及动爻 ----
    hai = []
    for pair in HAI_PAIR:
        p = set(pair)
        if p <= ben_set and any(y.get('zhi') in p and y.get('moving') for y in ben_yao):
            a, b = tuple(p)
            hai.append({'name': '六害', 'desc': '卦中%s·%s 相害（相穿）——害主暗损、隔阂，其伤隐而不显'
                                                % (a, b)})

    return {'flags': flags, 'combos': combos, 'xing': xing, 'hai': hai}


# ---------------- 飞神 / 伏神 ----------------
FEI_FU_REL = {
    'fly_sheng': ('飞生伏', '飞神生伏神——伏神得飞神之助，出而有力'),
    'fu_sheng': ('伏生飞', '伏神生飞神——伏神泄气于飞神，出而乏力'),
    'fly_ke': ('飞克伏', '飞神克伏神——伏神受制，古法须待冲去飞神之期方显'),
    'fu_ke': ('伏克飞', '伏神克飞神——古称「伏克飞神，伏神得出」'),
    'he': ('飞伏比和', '飞伏同气比和——伏神不受伤，可待时而动'),
}


def fufu_relation(fei_wx, fu_wx):
    """飞神与伏神的五行关系。"""
    if not fei_wx or not fu_wx:
        return None
    if fei_wx == fu_wx:
        return FEI_FU_REL['he']
    if SHENG.get(fei_wx) == fu_wx:
        return FEI_FU_REL['fly_sheng']
    if SHENG.get(fu_wx) == fei_wx:
        return FEI_FU_REL['fu_sheng']
    if KE.get(fei_wx) == fu_wx:
        return FEI_FU_REL['fly_ke']
    if KE.get(fu_wx) == fei_wx:
        return FEI_FU_REL['fu_ke']
    return None


def fushen_note(fei, fu):
    """伏神「能否出现」的传统判据摘要：只陈述规则与卦中实有的事实。"""
    pts = []
    rel = fufu_relation(fei.get('wx'), fu.get('wx'))
    if rel:
        pts.append(rel[0] + '（' + rel[1].split('——')[-1] + '）')
    w = fu.get('wang')
    if w in ('旺', '相'):
        pts.append('伏神' + w + '相、气足易出')
    elif w in ('休', '囚', '死'):
        pts.append('伏神' + w + '、气弱难出')
    if fu.get('is_kong'):
        pts.append('伏神旬空，虽伏亦虚，须待出空')
    if fei.get('is_kong'):
        pts.append('飞神旬空，伏神易透')
    if fei.get('is_yuepo') or fei.get('is_richong'):
        pts.append('飞神受月破／日冲，伏神易出')
    if fu.get('is_yuepo'):
        pts.append('伏神月破，出而无力')
    return '；'.join(pts)


# ---------------- 神煞（以日支起）----------------
def shensha_of(ben_yao, ri_zhi, category=None):
    """以日支查驿马 / 桃花，列出卦中是否有该支之爻。

    只列「卦中确有此支、在第几位」这一可核对的事实，并附传统所指，
    不作吉凶断言。传统亦有以年支起神煞者，此处从六爻常用的日支取法。
    """
    out = []
    for nm, table in (('驿马', YIMA), ('桃花', TAOHUA)):
        z = table.get(ri_zhi)
        if not z:
            continue
        hits = [y for y in ben_yao if y.get('zhi') == z]
        meta = SHENSHA_META[nm]
        out.append({
            'name': nm,
            'zhi': z,
            'from': '日支 ' + ri_zhi,
            'hits': [{'pos': y.get('pos'), 'pos_name': y.get('pos_name', ''),
                      'liuqin': y.get('liuqin', ''), 'ganzhi': y.get('ganzhi', ''),
                      'wx': y.get('wx', ''),
                      'moving': bool(y.get('moving')), 'is_shi': bool(y.get('is_shi')),
                      'is_ying': bool(y.get('is_ying')), 'is_kong': y.get('is_kong'),
                      'is_yuepo': y.get('is_yuepo')}
                     for y in hits],
            'desc': meta['desc'],
            'rel_cat': bool(category and category in meta['cats']),
        })
    return out


# ---------------- 应期线索 ----------------
def yingqi_of(yong, ben_yao, moving_idx, yue_zhi, ri_zhi, kong, fushen=None):
    """应期线索：按传统「值、冲、合、出空、冲墓」的推法列出时点参照。

    严格只做「条件 → 时点」的规则映射，不说「何时必然应验」。
    返回 [{'k': 触发条件, 'v': 时点参照, 'd': 传统推法说明}, ...]
    """
    out = []
    if not yong:
        # 用神不现：给伏神的「出伏」线索（值日值月自透 / 冲开飞神）
        for f in (fushen or []):
            fei = f.get('fei') or {}
            fz, fzhi = fei.get('zhi', ''), fei.get('ganzhi', '')
            out.append({
                'k': '伏神 ' + f['pos_name'] + ' ' + f['liuqin'],
                'v': '逢 %s 值日／值月自透，或逢 %s 日冲去飞神%s'
                     % (f.get('zhi', ''), CHONG.get(fz, '—'), ('（' + fzhi + '）') if fzhi else ''),
                'd': '用神伏藏，传统须待其「值日、值月」而自透，或「冲开飞神」而出。'
                     '飞伏关系：%s' % (f.get('rel_desc') or '—'),
            })
            mu = MU.get(f.get('wx'))
            if mu and mu in (yue_zhi, ri_zhi):
                out.append({
                    'k': '伏神入墓',
                    'v': '逢 %s 日／月冲开墓库' % CHONG.get(mu, '—'),
                    'd': '伏而入墓，须待冲墓之期方显。',
                })
        if not out:
            out.append({
                'k': '用神不现',
                'v': '本卦无此六亲，亦无可取伏神',
                'd': '传统多取世爻兼看应爻为参，不另推应期。',
            })
        return out

    zhi = yong.get('zhi', '')
    wx = yong.get('wx', '')

    if zhi and yong.get('is_kong'):
        out.append({
            'k': '用神旬空',
            'v': '逢 %s 值日／值月为「填实」，或逢 %s 日冲起为「冲空」'
                 % (zhi, CHONG.get(zhi, '—')),
            'd': '空者待实：本支当值之日、当月即填实；被其冲支冲动之日则冲空。'
                 '古法以「空逢填而用、逢冲而实」为出空之候。',
        })
    if zhi and yong.get('is_yuepo'):
        out.append({
            'k': '用神月破',
            'v': '出 %s 月（交下一节气）后即不破，或逢 %s 日合之'
                 % (yue_zhi, HE6.get(zhi, '—')),
            'd': '月破所破在后天（月建）而非自身。出月则破自解；'
                 '古亦有「破而逢合则有用」之说。',
        })
    mu = MU.get(wx)
    if mu and mu in (yue_zhi, ri_zhi):
        out.append({
            'k': '用神入墓',
            'v': '逢 %s 日／月冲开墓库（%s 之冲为 %s）'
                 % (CHONG.get(mu, '—'), mu, CHONG.get(mu, '—')),
            'd': '入墓者力藏不显。传统以「冲墓」之支为出墓之候，'
                 '即墓库之冲支值日、值月之时。',
        })
    if yong.get('moving'):
        out.append({
            'k': '用神发动',
            'v': '逢 %s 值日／值月' % (zhi or '—'),
            'd': '动爻为事之机。古法多以「动爻值日、值月」为其发用之时；'
                 '亦有「动而逢合则应、逢冲则散」两说。',
        })

    yong_pos = yong.get('pos')
    for i in moving_idx:
        if i == yong_pos:
            continue
        y = ben_yao[i]
        out.append({
            'k': '动爻 ' + y['pos_name'],
            'v': '逢 %s（%s）值日／值月' % (y['zhi'], y['liuqin']),
            'd': '动爻为事之发动处，传统以该支值日、值月为事应之候。',
        })

    if not out:
        out.append({
            'k': '用神安静',
            'v': '逢 %s 值日／值月，或逢 %s 日冲动' % (zhi, CHONG.get(zhi, '—')),
            'd': '静爻待动：古法以「静者逢值、逢冲」为应期之候。'
                 '本条仅为传统推法参照，不作断言。',
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
    b_yao = None
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

    yong_cands = []
    if ys_name is None:
        yong = shi_yao
        ys_label = '世爻（' + shi_yao['liuqin'] + '）'
    else:
        cands = [y for y in ben_yao if y['liuqin'] == ys_name]
        if not cands:
            yong = None
            ys_label = ys_name + '（卦中不现，须查伏神）'
        else:
            # 用神两现时的取用次序（传统）：先舍空破取其可用者，次取临世应者，
            # 再取发动者（事之机），末以旺相定之。次序本身即为可核对的判据。
            rank = {'旺': 4, '相': 3, '休': 2, '囚': 1, '死': 0}

            def _ys_rank(y):
                return (0 if (y['is_kong'] or y['is_yuepo']) else 1,
                        1 if (y['is_shi'] or y['is_ying']) else 0,
                        1 if y['moving'] else 0,
                        rank.get(y['wang'], 0))

            cands = sorted(cands, key=_ys_rank, reverse=True)
            yong = cands[0]
            ys_label = ys_name
            if len(cands) > 1:
                yong_cands = [{
                    'pos': y['pos'], 'pos_name': y['pos_name'], 'ganzhi': y['ganzhi'],
                    'liuqin': y['liuqin'], 'wang': y['wang'], 'moving': bool(y['moving']),
                    'is_shi': bool(y['is_shi']), 'is_ying': bool(y['is_ying']),
                    'is_kong': y['is_kong'], 'is_yuepo': y['is_yuepo'],
                    'chosen': (y is yong),
                } for y in cands]

    # 取用理由（只在两现时给出，便于核对为何取此爻）
    yong_reason = ''
    if yong_cands and yong is not None:
        why = []
        if not (yong['is_kong'] or yong['is_yuepo']):
            why.append('不空不破')
        if yong['is_shi']:
            why.append('临世')
        elif yong['is_ying']:
            why.append('临应')
        if yong['moving']:
            why.append('发动')
        why.append('旺衰为「' + (yong['wang'] or '—') + '」')
        yong_reason = ('用神两现（共 %d 处），按「舍空破 → 取临世应 → 取动 → 取旺」'
                       '取 %s %s %s（%s）'
                       % (len(yong_cands), yong['pos_name'], yong['ganzhi'],
                          yong['liuqin'], '、'.join(why)))

    # 伏神：用神不上卦时，取本宫纯卦同六亲之爻为伏（传统「伏神法」）
    # 伏神所在爻位在本卦的对应爻即「飞神」，飞伏生克决定伏神能否透出。
    fushen = []
    if yong is None and ys_name:
        pure = list(TRIGRAMS[gong]) * 2
        pure_yao = zhuang_gua(pure, [False] * 6, gong_wx, yue_zhi, ri_zhi, kong)
        for y in pure_yao:
            if y['liuqin'] == ys_name:
                f = dict(y)
                f['from'] = '本宫' + GONG_NAMES[gong][0]
                f['wang'] = wangshuai_of(f['wx'], ZHI_WX.get(yue_zhi, ''))
                fei = ben_yao[f['pos']]
                f['fei'] = {
                    'pos': fei['pos'], 'pos_name': fei['pos_name'], 'ganzhi': fei['ganzhi'],
                    'zhi': fei['zhi'], 'wx': fei['wx'], 'liuqin': fei['liuqin'],
                    'wang': fei['wang'], 'moving': bool(fei['moving']),
                    'is_shi': bool(fei['is_shi']), 'is_ying': bool(fei['is_ying']),
                    'is_kong': fei['is_kong'], 'is_yuepo': fei['is_yuepo'],
                    'is_richong': fei['is_richong'],
                }
                rel = fufu_relation(fei['wx'], f['wx'])
                f['rel'] = rel[0] if rel else ''
                f['rel_desc'] = rel[1] if rel else ''
                f['note'] = fushen_note(fei, f)
                fushen.append(f)

    # ---- 进阶规则（暗动 / 入墓 / 化进退 / 三合刑害 …）----
    key_pos = {ben['shi'] - 1, ben['ying'] - 1} | set(moving_idx)
    if yong is not None:
        key_pos.add(yong['pos'])
    adv = detect_advanced(ben_yao, b_yao, moving_idx, yue_zhi, ri_zhi, kong, key_pos)
    for i, y in enumerate(ben_yao):
        y['flags'] = adv['flags'].get(i, [])

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
            for fg in (y.get('flags') or []):
                if fg['code'] not in ('ruMu',):
                    fx.append(y['pos_name'] + fg['name'])
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
    # 六冲卦 / 六合卦：初四、二五、三上三组同论
    bz = [ben_yao[i]['zhi'] for i in range(6)]
    if all(CHONG.get(bz[i]) == bz[i + 3] for i in range(3)):
        struct.append('六冲卦：初四、二五、三上皆相冲，主变动急速、事难持久')
    if all(HE6.get(bz[i]) == bz[i + 3] for i in range(3)):
        struct.append('六合卦：初四、二五、三上皆相合，主事体胶着、缠绵难解')

    # 独发 / 独静：动爻个数本身即是可核对的结构事实
    n_mv = len(moving_idx)
    if n_mv == 1:
        i = moving_idx[0]
        struct.append('独发：六爻中唯「%s %s」一爻发动。古法「独发之爻，事之主也」，'
                      '多以此一爻为事机所在' % (ben_yao[i]['pos_name'], ben_yao[i]['liuqin']))
    elif n_mv == 5:
        j = [i for i in range(6) if i not in moving_idx][0]
        struct.append('独静：五爻皆动而唯「%s %s」独静。古法以静者为众动之所归、'
                      '为一卦之定处' % (ben_yao[j]['pos_name'], ben_yao[j]['liuqin']))
    elif n_mv == 6:
        struct.append('六爻皆动（古称「六爻乱动」）：变数极多、事绪纷杂，'
                      '传统多劝静观其变而不骤断')

    # ---- 神煞（驿马 / 桃花）：以日支起 ----
    shensha = shensha_of(ben_yao, ri_zhi, category)
    if yong is not None:
        for s in shensha:
            s['on_yong'] = any(h['pos'] == yong['pos'] for h in s['hits'])

    # ---- 应期线索（只做「条件 → 时点」的规则映射）----
    yingqi = yingqi_of(yong, ben_yao, moving_idx, yue_zhi, ri_zhi, kong, fushen)

    # ---- 卦爻辞（通行本，静态数据；异文从略）----
    text = None
    if zhouyi:
        bt = zhouyi.gua_text(ben['name'])
        if bt:
            text = {
                'name': ben['name'], 'ci': bt['ci'], 'xiang': bt['xiang'],
                'note': bt.get('note', ''),
                'plain': bt.get('plain', ''),
                'yao': bt['yao'],
                'moving_yao': [y for y in bt['yao'] if y['pos'] in moving_idx],
            }
            if bian:
                btx = zhouyi.gua_text(bian['name'])
                if btx:
                    text['bian_name'] = bian['name']
                    text['bian_ci'] = btx['ci']
                    text['bian_plain'] = btx.get('plain', '')

    # 合局 / 刑 / 害由前端独立成卡渲染，此处不并入 struct
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
            'reason': yong_reason,
            'cands': yong_cands,
        },
        'fushen': fushen,
        'facts': facts,
        'struct': struct,
        'advanced': adv,
        'shensha': shensha,
        'yingqi': yingqi,
        'text': text,
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
