"""固定快照的苏州办公分层分析；不训练、不改原表、不输出资产报价。

python 代码/合库准备/stratify_suzhou_office_v1.py --out <新批次目录>
输入是已发布7观察和既有CAND-E06；人民路保留原ID，不作为本轮新增。
"""
import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREV = ROOT / "成员成果/王玮/合库准备/2026-11-12_苏州办公大面积追采"
BASE = ROOT / "成员成果/王玮/合库准备"
SEVEN = PREV / "苏州办公补采整理版_v2_7观察.csv"
EIGHTEEN = BASE / "2026-11-12_统一分层可用性视图/18事件统一分层可用性视图.csv"
MERGE = BASE / "2026-11-12_合库准备初版/合库候选_28字段及来源.csv"
AS_OF = date(2026, 11, 12)
VERSION = "SZ-OFF-STRATA-1.0"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write(path, rows):
    assert rows, path
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def normalized_inputs():
    rows = read(SEVEN)
    assert len(rows) == 7
    event = next(x for x in read(EIGHTEEN) if x["统一候选事件ID"] == "CAND-E06")
    source = next(x for x in read(MERGE) if x["source_record_uid"] == "B02::B02-SZ04-C")
    assert event["价格性质"] == "PUBLISHED_TRANSACTION" and source["round_contract_id"] == "SCJRZ20260373"
    # 从既有已核字段读取；不把74200挂牌价复制为新的成交事件。
    rows.append({
        "观察ID": "CAND-E06", "项目编号": "SCJRZ20260373", "楼宇切分组": "人民路1058号",
        "地址范围": event["披露范围"], "披露面积㎡": event["披露面积㎡"],
        "面积口径": "103㎡公告出租面积；建筑/使用/实际计租分母未明确",
        "成交年租金元": event["原金额"], "名义元每披露㎡月": event["名义月单价"],
        "价格性质": "官方公示成交年租金；非合同实收/有效租金",
        "成交日": event["正文成交日"], "用途": source["use_legal_actual"],
        "物业费处理": "另收", "物业费元每㎡月": "10", "公共能耗费元每㎡月": "",
        "费用原文": source["tax_fee"], "税费口径": "完整税费与签署合同未取得",
        "限制及纳入建议": event["关键限制"], "核验状态": "沿用已发布限定辅助核对；未新增成员人工签核",
        "挂牌来源": "https://ggzy.suzhou.gov.cn/jyxx/003026/003026001/20260626/25635422732485.html",
        "成交来源": "https://ggzy.suzhou.gov.cn/jyxx/003026/003026002/20260707/25759941931717.html",
        "本轮动作": "既有CAND-E06纳入分层视图；非新增采集",
    })
    return rows


def classify(x):
    fee = "F_SEPARATE" if x["物业费处理"] == "另收" else (
        "F_INCLUDED_KNOWN" if x["物业费元每㎡月"] else "F_INCLUDED_UNKNOWN")
    area = "A_USE" if "以使用面积为准" in x["面积口径"] else "A_DISCLOSED_UNTYPED"
    text = x["用途"] + x["限制及纳入建议"]
    use = "U_OFFICE_WAREHOUSE_ALLOWED" if "仓库" in text else (
        "U_RESEARCH_OFFICE" if "研发" in text else "U_OFFICE_DISCLOSED")
    day = date.fromisoformat(x["成交日"])
    assert day <= AS_OF
    year = str(day.year)
    known_title_risk = "无产证" in text
    # 未见“无产证”不等于已验证有证；这里只单列已有明确不利披露。
    if known_title_risk:
        role, reason = "权证条件背景", "明确披露无产证；四维相同也不自动并入普通办公主组"
    elif area == "A_USE" or use == "U_OFFICE_WAREHOUSE_ALLOWED":
        role, reason = "使用面积及用途条件背景", "明确使用面积，且允许办公/仓库；不能等同建筑面积纯办公"
    elif use == "U_RESEARCH_OFFICE":
        role, reason = "研发办公条件背景", "研发/总部办公条件、含物业且2024历史；与主组用途费用年份均不同"
    elif fee != "F_SEPARATE":
        role, reason = "含物业背景", "租金含物业但未披露可拆金额；同楼房间保留但整体分组，不能按两楼计"
    elif day.year != AS_OF.year:
        role, reason = "历史扩展候选", "办公、物业另收，但为2024历史；不做无依据的时间折算，不直接并入2026主组"
    else:
        role, reason = "主流程候选", "2026成交、仅披露办公用途、物业另收；仅按披露面积名义标签试通流程"
    return fee, area, use, year, known_title_risk, role, reason


def build(out):
    if out.exists():
        raise FileExistsError("不能覆盖已发布批次；请使用新输出目录")
    raw = normalized_inputs()
    rows = []
    for x in raw:
        fee, area, use, year, title_risk, role, reason = classify(x)
        a, v = Decimal(x["披露面积㎡"]), Decimal(x["成交年租金元"])
        y = v / 12 / a
        assert a > 0 and v > 0
        assert abs(y - Decimal(x["名义元每披露㎡月"])) <= Decimal("0.0000005")
        rows.append({
            "观察ID": x["观察ID"], "来源原记录UID": "B02::B02-SZ04-C" if x["观察ID"] == "CAND-E06" else x["观察ID"],
            "项目编号": x["项目编号"], "楼宇切分组": x["楼宇切分组"],
            "地址范围": x["地址范围"], "费用层": fee, "面积分母层": area,
            "用途层": use, "成交年份": year, "四维联合层": "|".join([fee, area, use, year]),
            "物业费处理原文": x["物业费处理"], "物业费元每㎡月": x["物业费元每㎡月"],
            "公共能耗费元每㎡月": x["公共能耗费元每㎡月"],
            "面积口径原文": x["面积口径"], "披露面积㎡": str(a), "用途原文": x["用途"],
            "成交日": x["成交日"], "公示成交元每年": str(v),
            "y_名义元每披露㎡月": f"{y:.6f}", "标签说明": "公示年租÷12÷披露面积；费用未折净、不代表有效租金",
            "处理角色": role, "主流程准入": "是_仅流程测试" if role == "主流程候选" else "否_单列",
            "正式统一口径定价准入": "否", "判定理由": reason,
            "完整税费": x["税费口径"], "权证风险": "明确无产证" if title_risk else "本批未确证权证，不以未见风险推为有证",
            "当前限制": x["限制及纳入建议"], "本轮动作": x["本轮动作"],
            "挂牌来源": x["挂牌来源"], "成交来源": x["成交来源"],
            "输入来源": SEVEN.relative_to(ROOT).as_posix() if x["观察ID"] != "CAND-E06" else EIGHTEEN.relative_to(ROOT).as_posix(),
            "核验状态": x["核验状态"], "规则版本": VERSION,
        })
    assert len(rows) == 8 and len({x["观察ID"] for x in rows}) == 8
    main = [r for r in rows if r["处理角色"] == "主流程候选"]
    hist = [r for r in rows if r["处理角色"] == "历史扩展候选"]
    background = [r for r in rows if r not in main + hist]
    strata = defaultdict(list)
    for r in rows:
        strata[r["四维联合层"]].append(r)
    summary = [{"四维联合层": k, "观察数": len(v), "楼宇组数": len({r["楼宇切分组"] for r in v}),
                "主流程候选数": sum(r["处理角色"] == "主流程候选" for r in v),
                "观察ID": "；".join(r["观察ID"] for r in v),
                "处理角色分布": json.dumps(dict(Counter(r["处理角色"] for r in v)), ensure_ascii=False)}
               for k, v in sorted(strata.items())]
    out.mkdir(parents=True)
    write(out / "逐条分层与准入决定_8观察.csv", rows)
    write(out / "四维联合分层汇总.csv", summary)
    write(out / "历史扩展候选_1观察.csv", hist)
    write(out / "条件背景_5观察.csv", background)
    flow = [{"id": r["观察ID"], "building_group": r["楼宇切分组"], "city": "苏州",
             "area_disclosed_sqm": r["披露面积㎡"], "area_basis": r["面积分母层"],
             "rent_annual_cny": r["公示成交元每年"], "y_nominal_cny_per_disclosed_sqm_month": r["y_名义元每披露㎡月"],
             "transaction_date": r["成交日"], "fee_group": r["费用层"], "use_group": r["用途层"],
             "tax_status": "UNKNOWN", "allowed_usage": "仅读表、楼宇切分、训练侧中位数流程检查；非正式价格回归",
             "source_observation_id": r["来源原记录UID"].split("::")[-1]} for r in main]
    write(out / "基线流程输入_主组2观察.csv", flow)
    stats = {"规则版本": VERSION, "截至日": str(AS_OF), "输入观察数": len(rows),
             "楼宇组数": len({r["楼宇切分组"] for r in rows}), "四维联合层数": len(strata),
             "角色计数": dict(Counter(r["处理角色"] for r in rows)),
             "主流程楼宇组数": len({r["楼宇切分组"] for r in main}),
             "主流程面积范围㎡": [str(min(Decimal(r["披露面积㎡"]) for r in main)), str(max(Decimal(r["披露面积㎡"]) for r in main))],
             "正式统一口径定价准入数": 0, "训练是否执行": False,
             "价格是否折净": False, "历史价格是否按指数调整": False,
             "同楼房间处理": "观察保留；按building_group整体切分，不随机切行",
             "主组相对旧流程": "移出长丰204/205含物业观察；保留人民路和城市生活广场，不比较前后误差大小"}
    (out / "分层检查结果.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf8")
    evidence = ROOT / "成员成果/王玮/成员成果验收/2026-11-10_首批/原始提交展开/B02_20261109/证据"
    inputs = [SEVEN, EIGHTEEN, MERGE, PREV / "补采索引.json", evidence / "SZ04_P.html", evidence / "SZ04_C_ALT.html", Path(__file__)]
    write(out / "输入来源与哈希.csv", [{"文件": p.relative_to(ROOT).as_posix(), "字节数": p.stat().st_size,
                                       "SHA256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in inputs])
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    build(parser.parse_args().out)
