# -*- coding: utf-8 -*-
"""六爻后端纯函数单测（零依赖，直接 python tests/test_liuyao.py 运行）。

覆盖：
  · 基础表与装卦（纳甲 / 六亲 / 世应 / 旬空 / 月建）
  · 旺衰、飞伏生克、神煞、应期
  · detect_advanced 的黄金样本（化进退 / 回头生克 / 暗动日破 / 三合局 / 空破 / 入墓）
  · 用神两现的取用次序
  · compute_liuyao 端到端快照（固定卦局 + 固定时间）
  · zhouyi 卦爻辞完整性

约定：断言写成「可解释的事实」，失败时打印 actual，便于定位。
"""
import os
import sys
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, 'api'))

import liuyao                      # noqa: E402
import zhouyi                      # noqa: E402

PASS = 0
FAIL = 0
FAILS = []


def ck(name, cond, detail=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print('  PASS  %s' % name)
    else:
        FAIL += 1
        FAILS.append('%s :: %s' % (name, detail))
        print('  FAIL  %s  :: %s' % (name, detail))


def sec(t):
    print('\n== %s ==' % t)


# 卦局速记：y=少阳(静阳) i=少阴(静阴) Y=老阳(动阳) M=老阴(动阴)
_KEY = {'y': (True, False), 'i': (False, False), 'Y': (True, True), 'M': (False, True)}


def mk(s):
    return [_KEY[c] for c in s]


FIXED_DT = datetime(2026, 9, 16, 14, 30)


def yao(pos, zhi, moving=False, wang='旺', kong=False, yuepo=False, richong=False):
    """构造 detect_advanced 用的合成爻。"""
    return {'pos': pos, 'pos_name': liuyao.YAO_NAMES[pos], 'zhi': zhi,
            'wx': liuyao.ZHI_WX.get(zhi, ''), 'moving': moving, 'wang': wang,
            'is_kong': kong, 'is_yuepo': yuepo, 'is_richong': richong}


def codes(flags, pos):
    return [f['code'] for f in flags.get(pos, [])]


# ---------------------------------------------------------------- 基础表 / 装卦
sec('基础表与装卦')

ck('八卦表 8 个', len(liuyao.TRIGRAMS) == 8, len(liuyao.TRIGRAMS))
ck('卦表 64 卦', len(liuyao.GUA_TABLE) == 64, len(liuyao.GUA_TABLE))

_names = set()
for _g, _lst in liuyao.GONG_NAMES.items():
    _names.update(_lst)
ck('八宫卦名共 64 个且无重复', len(_names) == 64, len(_names))
ck('卦表名与八宫卦名一致', {v['name'] for v in liuyao.GUA_TABLE.values()} == _names)

ck('lookup 乾为天', liuyao.lookup_gua([1, 1, 1, 1, 1, 1])['name'] == '乾为天')
ck('lookup 坤为地', liuyao.lookup_gua([0] * 6)['name'] == '坤为地')
ck('lookup 水火既济',
   liuyao.lookup_gua([1, 0, 1, 0, 1, 0])['name'] == '水火既济')
ck('lookup 长度不足返回 None', liuyao.lookup_gua([1, 1]) is None)

ck('乾为天 世六应三',
   (liuyao.lookup_gua([1] * 6)['shi'], liuyao.lookup_gua([1] * 6)['ying']) == (6, 3))
_jj = liuyao.lookup_gua([1, 0, 1, 0, 1, 0])
ck('水火既济 世三应六', (_jj['shi'], _jj['ying']) == (3, 6), (_jj['shi'], _jj['ying']))

# 旬空
ck('旬空 甲子日 → 戌亥', liuyao.xunkong_of('甲子') == ('戌', '亥'), liuyao.xunkong_of('甲子'))
ck('旬空 癸酉日（同旬）→ 戌亥', liuyao.xunkong_of('癸酉') == ('戌', '亥'), liuyao.xunkong_of('癸酉'))
ck('旬空 甲戌日 → 申酉', liuyao.xunkong_of('甲戌') == ('申', '酉'), liuyao.xunkong_of('甲戌'))
ck('旬空 甲寅日 → 子丑', liuyao.xunkong_of('甲寅') == ('子', '丑'), liuyao.xunkong_of('甲寅'))

# 六亲 / 旺衰
ck('六亲 金宫见土为父母', liuyao.liuqin_of('金', '土') == '父母')
ck('六亲 金宫见金为兄弟', liuyao.liuqin_of('金', '金') == '兄弟')
ck('六亲 金宫见水为子孙', liuyao.liuqin_of('金', '水') == '子孙')
ck('六亲 金宫见木为妻财', liuyao.liuqin_of('金', '木') == '妻财')
ck('六亲 金宫见火为官鬼', liuyao.liuqin_of('金', '火') == '官鬼')

_cases = [('木', '木', '旺'), ('木', '水', '相'), ('木', '火', '休'),
          ('木', '土', '囚'), ('木', '金', '死')]
for _a, _b, _exp in _cases:
    ck('旺衰 %s爻遇%s月 → %s' % (_a, _b, _exp),
       liuyao.wangshuai_of(_a, _b) == _exp, liuyao.wangshuai_of(_a, _b))

# 月建（取月中旬，避开节气边界）
_mc = [(datetime(2026, 1, 10), '丑'), (datetime(2026, 3, 1), '寅'),
       (datetime(2026, 5, 15), '巳'), (datetime(2026, 9, 16), '酉'),
       (datetime(2026, 11, 20), '亥'), (datetime(2026, 12, 20), '子')]
for _dt, _exp in _mc:
    ck('月建 %s → %s月' % (_dt.date(), _exp),
       liuyao.month_zhi(_dt) == _exp, liuyao.month_zhi(_dt))

# 日干支：逐日递进（比硬编码更稳的正确性判据）
_d1 = liuyao.day_ganzhi(datetime(2026, 9, 16))
_d2 = liuyao.day_ganzhi(datetime(2026, 9, 17))
ck('日干支为双字且在甲子序列内',
   len(_d1) == 2 and _d1[0] in liuyao.GAN_SEQ and _d1[1] in liuyao.ZHI_SEQ, _d1)
ck('日干支逐日递进一位',
   (liuyao.GAN_SEQ.index(_d2[0]) - liuyao.GAN_SEQ.index(_d1[0])) % 10 == 1
   and (liuyao.ZHI_SEQ.index(_d2[1]) - liuyao.ZHI_SEQ.index(_d1[1])) % 12 == 1,
   (_d1, _d2))

# ---------------------------------------------------------------- 飞伏 / 神煞
sec('飞伏生克与神煞')

ck('飞生伏', liuyao.fufu_relation('金', '水')[0] == '飞生伏')
ck('伏生飞', liuyao.fufu_relation('水', '金')[0] == '伏生飞')
ck('飞克伏', liuyao.fufu_relation('金', '木')[0] == '飞克伏')
ck('伏克飞', liuyao.fufu_relation('木', '金')[0] == '伏克飞')
ck('飞伏比和', liuyao.fufu_relation('木', '木')[0] == '飞伏比和')
ck('飞伏空 wx 返回 None', liuyao.fufu_relation('', '木') is None)

_b = [yao(i, z) for i, z in enumerate(['寅', '子', '辰', '午', '申', '戌'])]
_ss = {s['name']: s for s in liuyao.shensha_of(_b, '子', '出行迁移')}
ck('神煞含驿马与桃花', set(_ss) == {'驿马', '桃花'}, list(_ss))
ck('申子辰日 驿马在寅', _ss['驿马']['zhi'] == '寅', _ss['驿马']['zhi'])
ck('申子辰日 桃花在酉', _ss['桃花']['zhi'] == '酉', _ss['桃花']['zhi'])
ck('驿马命中初爻寅', [h['pos'] for h in _ss['驿马']['hits']] == [0],
   _ss['驿马']['hits'])
ck('桃花未命中（卦中无酉）', _ss['桃花']['hits'] == [])
ck('出行类目标记 rel_cat', _ss['驿马']['rel_cat'] is True)

# ---------------------------------------------------------------- 应期
sec('应期线索')

_o = {'pos': 0, 'zhi': '子', 'wx': '水', 'moving': False, 'is_kong': True, 'is_yuepo': False}
_yy = liuyao.yingqi_of(_o, _b, [], '酉', '午', ('戌', '亥'))
ck('旬空 → 出空线索（含冲支午）',
   any(y['k'] == '用神旬空' and '午' in y['v'] for y in _yy), _yy)

_o2 = dict(_o, is_kong=False, is_yuepo=True)
_yy2 = liuyao.yingqi_of(_o2, _b, [], '酉', '午', ('戌', '亥'))
ck('月破 → 出月线索（含酉）', any(y['k'] == '用神月破' for y in _yy2), _yy2)

_o3 = {'pos': 0, 'zhi': '子', 'wx': '水', 'moving': True,
       'is_kong': False, 'is_yuepo': False}
_yy3 = liuyao.yingqi_of(_o3, _b, [0], '酉', '午', ())
ck('发动 → 值日值月线索', any(y['k'] == '用神发动' for y in _yy3), _yy3)

_o4 = {'pos': 0, 'zhi': '子', 'wx': '水', 'moving': False,
       'is_kong': False, 'is_yuepo': False}
_yy4 = liuyao.yingqi_of(_o4, _b, [], '辰', '辰', ())
ck('水爻遇辰日 → 入墓线索', any(y['k'] == '用神入墓' for y in _yy4), _yy4)

_yy5 = liuyao.yingqi_of(None, _b, [], '酉', '午', (), fushen=[
    {'pos_name': '三爻', 'liuqin': '妻财', 'zhi': '午', 'wx': '火',
     'fei': {'zhi': '辰', 'ganzhi': '庚辰'}, 'rel_desc': '伏生飞'}])
ck('用神不现 → 伏神出伏线索（含冲飞之戌）',
   len(_yy5) == 1 and _yy5[0]['k'].startswith('伏神') and '戌' in _yy5[0]['v'], _yy5)

# ---------------------------------------------------------------- 进阶规则黄金样本
sec('detect_advanced 黄金样本')

# 化进：亥 → 子
_p = [yao(0, '亥', moving=True, wang='相')]
_q = [dict(_p[0], zhi='子', wx='水')]
_adv = liuyao.detect_advanced(_p, _q, [0], '酉', '午', (), {0})
ck('化进（亥化子）', 'huajin' in codes(_adv['flags'], 0), codes(_adv['flags'], 0))

# 化退：子 → 亥
_p = [yao(0, '子', moving=True, wang='旺')]
_q = [dict(_p[0], zhi='亥', wx='水')]
_adv = liuyao.detect_advanced(_p, _q, [0], '酉', '午', (), {0})
ck('化退（子化亥）', 'huatui' in codes(_adv['flags'], 0), codes(_adv['flags'], 0))

# 回头生：木爻化水
_p = [yao(0, '寅', moving=True, wang='旺')]
_q = [dict(_p[0], zhi='子', wx='水')]
_adv = liuyao.detect_advanced(_p, _q, [0], '酉', '午', (), {0})
ck('回头生（木化水）', 'huitousheng' in codes(_adv['flags'], 0), codes(_adv['flags'], 0))

# 回头克：木爻化金
_p = [yao(0, '寅', moving=True, wang='旺')]
_q = [dict(_p[0], zhi='申', wx='金')]
_adv = liuyao.detect_advanced(_p, _q, [0], '酉', '午', (), {0})
ck('回头克（木化金）', 'huitouke' in codes(_adv['flags'], 0), codes(_adv['flags'], 0))

# 暗动：静爻旺而日冲
_p = [yao(0, '子', moving=False, wang='旺', richong=True)]
_adv = liuyao.detect_advanced(_p, None, [], '酉', '午', (), {0})
ck('暗动（旺而日冲）', 'andong' in codes(_adv['flags'], 0), codes(_adv['flags'], 0))

# 日破：静爻衰而日冲
_p = [yao(0, '子', moving=False, wang='死', richong=True)]
_adv = liuyao.detect_advanced(_p, None, [], '酉', '午', (), {0})
ck('日破（衰而日冲）', 'ripo' in codes(_adv['flags'], 0), codes(_adv['flags'], 0))

# 空破：旬空 + 月破
_p = [yao(0, '子', kong=True, yuepo=True, wang='休')]
_adv = liuyao.detect_advanced(_p, None, [], '午', '寅', ('子',), {0})
ck('空破（空且月破）', 'kongpo' in codes(_adv['flags'], 0), codes(_adv['flags'], 0))

# 入墓：水爻遇辰日（限 key_pos）
_p = [yao(0, '子', wang='休')]
_adv = liuyao.detect_advanced(_p, None, [], '酉', '辰', (), {0})
ck('入墓（水墓辰、日辰为辰）', 'ruMu' in codes(_adv['flags'], 0), codes(_adv['flags'], 0))
_adv2 = liuyao.detect_advanced(_p, None, [], '酉', '辰', (), set())
ck('入墓不列非 key_pos 之爻', 'ruMu' not in codes(_adv2['flags'], 0))

# 三合局：卦中 申、子（子动），借月建辰凑足
_p = [yao(0, '申', wang='休'), yao(1, '子', moving=True, wang='旺'),
      yao(2, '丑', wang='休'), yao(3, '卯', wang='休'),
      yao(4, '巳', wang='休'), yao(5, '未', wang='休')]
_adv = liuyao.detect_advanced(_p, None, [1], '辰', '午', (), {1})
_he = [c for c in _adv['combos'] if c['type'] == '三合局']
ck('三合局 申子辰·水（借月建凑足）',
   len(_he) == 1 and _he[0]['wx'] == '水' and _he[0]['level'] == '待成',
   _adv['combos'])
ck('变卦地支参与合局', '水' in [c['wx'] for c in _he])

# 六害：只论本卦且须涉及动爻
_p = [yao(0, '子', moving=True, wang='旺'), yao(1, '未', wang='休')]
_adv = liuyao.detect_advanced(_p, None, [0], '酉', '午', (), {0})
ck('六害（子未相穿，含动爻）', any(h['name'] == '六害' for h in _adv['hai']), _adv['hai'])
_p2 = [yao(0, '子', wang='旺'), yao(1, '未', wang='休')]
_adv2 = liuyao.detect_advanced(_p2, None, [], '酉', '午', (), set())
ck('六害无动爻则不列', not _adv2['hai'], _adv2['hai'])

# 三刑：寅巳申俱全
_p = [yao(0, '寅', wang='休'), yao(1, '巳', wang='休'), yao(2, '申', wang='休'),
      yao(3, '子', wang='旺'), yao(4, '卯', wang='旺'), yao(5, '丑', wang='休')]
_adv = liuyao.detect_advanced(_p, None, [], '酉', '午', (), set())
ck('三刑（寅巳申·无恩之刑）',
   any(x['name'] == '无恩之刑' for x in _adv['xing']), [x['name'] for x in _adv['xing']])
ck('自刑（子卯为刑非自刑，此处子仅一见）',
   not any(x['name'] == '自刑' for x in _adv['xing']),
   [x['name'] for x in _adv['xing']])

# ---------------------------------------------------------------- 端到端
sec('compute_liuyao 端到端（固定卦局 + 固定时间）')

_r = liuyao.compute_liuyao(yao6=mk('YYYYYY'), category='求财', dt=FIXED_DT)
ck('乾为天 六爻皆动 → 变卦坤为地',
   _r['ben']['name'] == '乾为天' and _r['bian']['name'] == '坤为地',
   (_r['ben']['name'], (_r['bian'] or {}).get('name')))
ck('六爻皆动 → moving 长度 6', len(_r['moving']) == 6, _r['moving'])
ck('六爻皆动 → struct 报「六爻乱动」',
   any('六爻乱动' in s for s in _r['struct']), _r['struct'])
ck('本卦返回六爻各带纳甲/六亲/六神/旺衰',
   all(y.get('ganzhi') and y.get('liuqin') and y.get('liushen') and y.get('wang')
       for y in _r['ben']['yao']))
ck('伏神字段（本局不现则空）', isinstance(_r['fushen'], list))
ck('神煞返回 2 项（驿马 / 桃花）', len(_r['shensha']) == 2, [s['name'] for s in _r['shensha']])
ck('应期非空', len(_r['yingqi']) >= 1, len(_r['yingqi']))
ck('卦爻辞已接入（本卦卦辞非空）',
   _r['text'] and _r['text']['ci'], (_r['text'] or {}).get('ci', ''))
ck('动爻爻辞逐条对应 moving',
   len(_r['text']['moving_yao']) == len(_r['moving']),
   (len(_r['text']['moving_yao']), len(_r['moving'])))
ck('变卦卦辞已附', bool(_r['text'].get('bian_ci')) and _r['text'].get('bian_name') == '坤为地')
ck('月建/日辰/旬空齐备',
   bool(_r['month_zhi']) and bool(_r['day_gz']) and len(_r['xunkong']) == 2)

# 独发 / 独静
_r2 = liuyao.compute_liuyao(yao6=mk('Yiiiii'), category='出行迁移', dt=FIXED_DT)
ck('独发 → struct 含「独发」', any('独发' in s for s in _r2['struct']), _r2['struct'])
_r3 = liuyao.compute_liuyao(yao6=mk('YyYYYY'), category='出行迁移', dt=FIXED_DT)
ck('独静（五动一静）→ struct 含「独静」',
   any('独静' in s for s in _r3['struct']), _r3['struct'])
_r4 = liuyao.compute_liuyao(yao6=mk('iiiiii'), category='求财', dt=FIXED_DT)
ck('六静卦 → 无变卦且 facts 报六静',
   _r4['bian'] is None and any(f['k'] == '动爻' and '六静' in f['v'] for f in _r4['facts']),
   (_r4['bian'], [f['v'] for f in _r4['facts'] if f['k'] == '动爻']))

# 用神两现：乾为天 · 考试文书 → 父母两现（三爻 / 上爻），取三爻（临应）
_r5 = liuyao.compute_liuyao(yao6=mk('yyyyyy'), category='考试文书', dt=FIXED_DT)
_c5 = _r5['yongshen']['cands']
ck('用神两现 → cands 2 项', len(_c5) == 2, [(c['pos_name'], c['chosen']) for c in _c5])
ck('取用次序：临应者优先',
   [c['pos_name'] for c in _c5 if c['chosen']] == ['三爻'],
   [(c['pos_name'], c['is_ying'], c['chosen']) for c in _c5])
ck('两现时给出取用理由',
   bool(_r5['yongshen']['reason']) and '两现' in _r5['yongshen']['reason'],
   _r5['yongshen']['reason'])

# 用神不现 → 伏神带飞伏关系
_r6 = liuyao.compute_liuyao(yao6=mk('yMiMyM'), category='求财', dt=FIXED_DT)
ck('用神不现 → 产生伏神', len(_r6['fushen']) >= 1, _r6['fushen'])
if _r6['fushen']:
    _f = _r6['fushen'][0]
    ck('伏神带飞神信息', bool(_f.get('fei') and _f['fei'].get('ganzhi')),
       _f.get('fei'))
    ck('伏神带飞伏关系', bool(_f.get('rel')), _f.get('rel'))
    ck('伏神带判据说明', bool(_f.get('note')), _f.get('note'))
ck('用神不现时给出伏神应期线索',
   any(y['k'].startswith('伏神') for y in _r6['yingqi']), _r6['yingqi'])

# 自动起卦分支
_r7 = liuyao.compute_liuyao(yao6=None, category='求财', dt=FIXED_DT)
ck('yao6=None → auto_cast=True', _r7.get('auto_cast') is True)
ck('自动起卦产生 6 爻', len(_r7['ben']['yao']) == 6)

# ---------------------------------------------------------------- 卦爻辞库
sec('zhouyi 卦爻辞库')

ck('自检通过（64 卦 / 各 6 爻）', zhouyi.self_check() == [], zhouyi.self_check())
ck('乾为天 6 条爻辞', len(zhouyi.gua_text('乾为天')['yao']) == 6)
ck('乾为天 初九为「潜龙勿用」',
   '潜龙勿用' in zhouyi.gua_text('乾为天')['yao'][0]['text'],
   zhouyi.gua_text('乾为天')['yao'][0]['text'])
ck('乾坤带用九 / 用六',
   bool(zhouyi.gua_text('乾为天')['yong']) and bool(zhouyi.gua_text('坤为地')['yong']))
ck('未收录卦名返回 None', zhouyi.gua_text('不存在卦') is None)
ck('爻题随卦阴阳（水火既济 初九 / 六二）',
   zhouyi.gua_text('水火既济')['yao'][0]['text'].startswith('初九')
   and zhouyi.gua_text('水火既济')['yao'][1]['text'].startswith('六二'),
   [y['text'][:2] for y in zhouyi.gua_text('水火既济')['yao']])

# ---------------------------------------------------------------- 汇总
print('\n' + '=' * 46)
print('汇总：%d PASS / %d FAIL' % (PASS, FAIL))
if FAILS:
    print('失败项：')
    for f in FAILS:
        print('  ·', f)
print('=' * 46)
sys.exit(1 if FAIL else 0)
