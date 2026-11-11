"""Build descriptive samples and baseline feasibility from the fixed 18-event snapshot."""
import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / '成员成果/王玮/合库准备/2026-11-12_统一分层可用性视图/18事件统一分层可用性视图.csv'
CORE = {'CAND-E01', 'CAND-E06', 'CAND-E08', 'NEXT-E14', 'NEXT-E17', 'NEXT-E18'}
CONDITIONAL = {'CAND-E07', 'NEXT-E13', 'NEXT-E15'}
CAMPUS = {'CAND-E02', 'CAND-E03', 'CAND-E04'}
CONTRACT = {'CAND-E09', 'CAND-E10', 'CAND-E11', 'CAND-E12'}
SCOPES = {
    'CAND-E01': ('商业披露', '1层整体', '单一一层范围'),
    'CAND-E06': ('办公披露', '5层', '三室合包'),
    'CAND-E08': ('经营用房披露', '1层', '102室；非由房号推楼层，来自新挂牌原文'),
    'NEXT-E14': ('商业用房_办公经营用途', '1层', '单门牌；不等同纯零售或纯办公'),
    'NEXT-E17': ('经营用房披露', '1-2层', '多层整体'),
    'NEXT-E18': ('商业用房_办公用途', '1-2层', '多层整体；额外装修费用待核'),
    'CAND-E07': ('商业披露', '1层', '101/107两室合包'),
    'NEXT-E13': ('商业披露', '1层', '附号3整体'),
    'NEXT-E15': ('商业披露', '1-2层', '整体，不能按首层单独分摊'),
}


def read(p):
    with p.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def write(p, rows):
    with p.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def build(out):
    if out.exists():
        raise FileExistsError('Do not overwrite published batches')
    digest = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    rows = read(SOURCE)
    assert len(rows) == 18
    decisions, samples, contexts, held = [], [], [], []
    for x in rows:
        eid = x['统一候选事件ID']
        reason = ''
        if eid in CORE:
            role = '核心描述样本'
            reason = '公示成交、披露面积可对应、日期字段可分别解释；费用/权证/用途差异仍保留'
        elif eid in CONDITIONAL:
            role = '条件描述样本'
            reason = '中山34号发布时间异常' if eid == 'CAND-E07' else '清江挂牌/成交缺直接编号桥，且公示页头与正文日期异常'
        elif eid in CAMPUS:
            role = '校园场景单列'
            reason = '经营限制及校园需求结构特殊；9号明确超市；不混普通商业/办公目标'
        elif eid in CONTRACT:
            role = '历史合同背景单列'
            reason = '不是公示成交标签；两资产多期及费用组合不同，不作为新增独立成交'
        else:
            assert eid in {'CAND-E05', 'NEXT-E16'}
            role = '暂缓名义样本'
            reason = '宝带物业/水费口径冲突未解决' if eid == 'CAND-E05' else '中山243面积分母本轮未核、挂牌403'
        decisions.append({'事件ID': eid, '处理决定': role, '纳入/单列/暂缓依据': reason,
                          '原数值是否删除': '否', '是否准入训练': '未执行',
                          '限制保留': x['关键限制'], '依据入口': x['证据及采用依据']})
        if eid in CORE | CONDITIONAL:
            assert x['名义月单价'] and x['披露面积㎡']
            use, floor, bundle = SCOPES[eid]
            # E08 old narrative contains pre-supplement "use unverified" wording. Keep it
            # in source/decision history, but do not present the stale instruction as current.
            current_limit = x['关键限制']
            if eid == 'CAND-E08':
                current_limit = '已由SCJX20244680挂牌原件核实1层经营用途、约20㎡；无两证披露；费用/实际计租与合法用途未核。原“用途未证”措辞只作历史，不再作为当前阻塞。'
            samples.append({'事件ID': eid, '资产切分组_本批临时': x['临时资产范围ID'],
                            '分析角色': role, '城市': x['城市'], '用途披露分层': use,
                            '楼层披露': floor, '合包范围': bundle,
                            '披露面积平方米': x['披露面积㎡'],
                            '正文成交日期原文': x['正文成交日'],
                            '成交年份_仅描述': x['正文成交日'][:4],
                            'y_公示名义元每披露平方米月': x['名义月单价'],
                            '目标定义': '公示年总租÷12÷同范围披露面积；非净有效租金',
                            '证据入口': x['证据及采用依据'], '当前限制': current_limit,
                            '训练准入': '尚未执行；本表不是已验证训练集'})
        elif eid in CAMPUS | CONTRACT:
            contexts.append({'事件ID': eid, '角色': role, '单列原因': reason,
                             '原名义数值': x['名义月单价'], '范围': x['披露范围'],
                             '来源与限制': x['证据及采用依据'] + '；' + x['关键限制']})
        else:
            held.append({'事件ID': eid, '暂缓原因': reason, '原名义值保留': x['名义月单价'],
                         '补证标准': '取得费用明确解释' if eid == 'CAND-E05' else '取得同轮面积与范围证据',
                         '未取得处理': '继续暂缓；不以0补值、不猜费用/分母'})
    core = [x for x in samples if x['分析角色'] == '核心描述样本']
    assert len(core) == 6 and len(samples) == 9 and len(contexts) == 7 and len(held) == 2
    assert len({x['事件ID'] for x in decisions}) == 18
    assert len({x['资产切分组_本批临时'] for x in samples}) == 9
    out.mkdir(parents=True)
    write(out / '第一版分析样本_核心6条.csv', core)
    write(out / '第一版分析样本_含条件9条.csv', samples)
    write(out / '18事件纳入排除说明.csv', decisions)
    write(out / '校园与合同背景_7条.csv', contexts)
    write(out / '暂缓样本_2条.csv', held)
    distribution = []
    for label, ss in [('核心6条', core), ('含条件9条', samples)]:
        for (city, use, floor), n in sorted(Counter((x['城市'], x['用途披露分层'], x['楼层披露']) for x in ss).items()):
            distribution.append({'样本版本': label, '城市': city, '披露用途': use,
                                 '楼层': floor, '事件数': n,
                                 '适用限制': '细分层仅1-2条；不是同质随机样本或已确认甲方可比'})
    write(out / '基线可行性_样本分布.csv', distribution)
    write(out / '实验字段使用约定.csv', [
        {'字段类别': '目标y', '允许字段': '公示名义元每披露平方米月', '限制': '不冒充净有效租金/实收'},
        {'字段类别': '描述/潜在输入', '允许字段': '城市、披露面积、用途、楼层、合包、价格年份', '限制': '费用及权证异质；回测前核当时是否可得'},
        {'字段类别': '禁止同目标输入', '允许字段': '原成交总价、目标单价、底价成交比、结果字段', '限制': '原成交总价是y的组成，不能作为预测输入'},
        {'字段类别': '切分与溯源', '允许字段': '事件ID、资产组、证据入口、原日期', '限制': '不当数值特征；先查全库关联再切分'},
        {'字段类别': '事后信息', '允许字段': '验收状态、成交后条款、未来期指数', '限制': '不能当作提前预测已知特征'},
    ])
    record = {'source': str(SOURCE.relative_to(ROOT)), 'source_sha256': digest,
              'decisions': 18, 'core': 6, 'conditional_extra': 3, 'contexts': 7, 'held': 2,
              'unique_asset_groups_in_analysis': 9,
              'core_city_counts': dict(Counter(x['城市'] for x in core)),
              'exploratory_pipeline_possible': True, 'reliable_generalization_assessment_supported': False,
              'model_fitted': False, 'member_signoff_added': False}
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == digest
    (out / '核查记录.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(record, ensure_ascii=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--out', type=Path, required=True)
    build(p.parse_args().out.resolve())
