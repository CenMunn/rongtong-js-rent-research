"""把经正文编号核对的香山成交DOM摘录关联至既有挂牌，生成独立新版。

python 代码/合库准备/apply_xiangshan_browser_evidence_v2.py <本批目录>
仅离线重建，不是自动联网的浏览器采集器；不训练或覆盖旧批。
"""
import csv
import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

from build_suzhou_office_followup import listing, date_iso

ROOT = Path(__file__).resolve().parents[2]
PREVIOUS = ROOT / "成员成果/王玮/合库准备/2026-11-12_苏州办公四维分层与流程准入"


def read(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def build(batch):
    p, _ = listing(batch / "辅助原件/香山60幢_挂牌.html")
    e = json.loads((batch / "浏览器证据摘录/香山60幢_成交.json").read_text(encoding="utf8"))
    assert e["证据类型"] == "本轮浏览器DOM文本摘录；非服务器原始HTML/PDF"
    assert p["项目编号"] == "SCJR20261830" and "60幢1楼和2楼" in e["正文标题"]
    cells = [row.split("\t") for row in e["表格行"] if row.startswith("SCJR20261830\t")]
    assert len(cells) == 1 and len(cells[0]) == 6
    pid, address, period, annual, day, method = cells[0]
    assert period == "2026年08月21日至2026年08月28日"
    assert p["挂牌起始日"] == "2026-08-21" and p["挂牌终止日"] == "2026-08-28"
    area, rent = Decimal(p["出租面积(m²)"]), Decimal(annual)
    assert area == Decimal("2704.1") and rent == Decimal("584085.6")
    assert p["使用用途及要求"] == "商务办公" and p["租金以外费用"] == "物业费：5元/平方米/月"
    eid = "SZ-OFF-" + pid
    rows = read(PREVIOUS / "逐条分层与准入决定_8观察.csv")
    assert len(rows) == 8 and all(r["观察ID"] != eid for r in rows)
    added = dict.fromkeys(rows[0], "")
    added.update({
        "观察ID": eid, "来源原记录UID": eid, "项目编号": pid,
        "楼宇切分组": "香山慧境商务中心60幢", "地址范围": "后塘路香山慧境商务中心60幢1楼和2楼",
        "费用层": "F_SEPARATE", "面积分母层": "A_DISCLOSED_UNTYPED", "用途层": "U_OFFICE_DISCLOSED",
        "成交年份": "2026", "四维联合层": "F_SEPARATE|A_DISCLOSED_UNTYPED|U_OFFICE_DISCLOSED|2026",
        "物业费处理原文": "物业费：5元/平方米/月（挂牌租金以外费用栏）", "物业费元每㎡月": "5",
        "面积口径原文": "挂牌出租面积2704.1㎡；建筑/使用/合同计租类型未明",
        "披露面积㎡": str(area), "用途原文": p["使用用途及要求"], "成交日": date_iso(day),
        "公示成交元每年": str(rent), "y_名义元每披露㎡月": f"{rent / 12 / area:.6f}",
        "标签说明": "公示年租÷12÷披露面积；费用未折净、不代表有效租金",
        "处理角色": "主流程候选", "主流程准入": "是_仅流程测试", "正式统一口径定价准入": "否",
        "判定理由": "沿用既有名义流程门槛：2026、办公用途披露、物业另收；面积类型及税费仍未知",
        "完整税费": "未取得明确含税/不含税及签署合同证据",
        "权证风险": "本批未确证权证，不以未见风险推为有证",
        "当前限制": "1-2层合包；1年租期、免租1个月仅限租金；面积类型/合同税费未证；太湖度假区区位与目标不同",
        "本轮动作": "既有挂牌线索补到官方同编号成交，新增名义流程候选；非新增挂牌",
        "挂牌来源": "https://ggzy.suzhou.gov.cn/jyxx/003026/003026001/20260821/26257670700485.html",
        "成交来源": e["URL"], "输入来源": "浏览器证据摘录/香山60幢_成交.json；辅助原件/香山60幢_挂牌.html",
        "核验状态": "浏览器官方成交正文与同号挂牌辅助核对；未代成员人工签核", "规则版本": "SZ-OFF-STRATA-1.0（本轮新增证据；规则未变）",
    })
    rows.append(added)
    for r in rows:
        r["本轮补证提示"] = ""
        if r["项目编号"] == "SCJRZ20260793":
            r["本轮补证提示"] = "普通浏览器详情可读；有使用面积以现状为准措辞，498㎡与合同分母关系仍未确认；未见可下载文件直链"
        elif r["项目编号"] == "SCJRZ20260373":
            r["本轮补证提示"] = "普通浏览器详情可读；103㎡类型/税费仍未知，未见可下载文件直链"
        elif r["项目编号"] == pid:
            r["本轮补证提示"] = "结果公示已取得，替代旧未取得成交状态；面积类型与税费缺口保留"
    flow = read(PREVIOUS / "基线流程输入_主组2观察.csv")
    flow.append({"id": eid, "building_group": added["楼宇切分组"], "city": "苏州",
                 "area_disclosed_sqm": str(area), "area_basis": "A_DISCLOSED_UNTYPED",
                 "rent_annual_cny": str(rent), "y_nominal_cny_per_disclosed_sqm_month": added["y_名义元每披露㎡月"],
                 "transaction_date": added["成交日"], "fee_group": "F_SEPARATE", "use_group": "U_OFFICE_DISCLOSED",
                 "tax_status": "UNKNOWN", "allowed_usage": "仅流程演示；分母/税费未统一，不提供实际定价能力评价", "source_observation_id": eid})
    write(batch / "苏州办公分层候选_v2_9观察.csv", rows)
    write(batch / "基线流程输入_v2_主组3观察.csv", flow)
    counts = Counter(r["处理角色"] for r in rows)
    assert len(rows) == 9 and len({r["观察ID"] for r in rows}) == 9
    summary = {"截至日": "2026-11-12", "新增同编号成交观察": 1, "主流程候选": len(flow),
               "主流程楼宇组": len({r["building_group"] for r in flow}), "全视图观察数": len(rows),
               "全视图楼宇组数": len({r["楼宇切分组"] for r in rows}), "角色计数": dict(counts),
               "名义月单价": added["y_名义元每披露㎡月"], "正式统一口径定价准入": 0,
               "面积类型税费已补清数": 0, "是否训练报价": False,
               "备注": "主组准入沿用旧名义流程规则；不代表满足明确面积类型的正式补采目标"}
    (batch / "本批检查结果.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    build(Path(sys.argv[1]))
