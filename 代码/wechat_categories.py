"""公众号文章与项目的保守分类。保留分类依据，无法判断的字段留待核对。"""
import re

CITY_AREAS = {
    "南京": ["建邺区","秦淮区","栖霞区","雨花台区","江宁区"],
    "苏州": ["姑苏区","虎丘区","吴中区","相城区","吴江区","昆山市","张家港市","常熟市","太仓市"],
    "镇江": ["句容市","丹阳市","扬中市","京口区"],
    "无锡": ["江阴市","宜兴市"], "徐州": ["邳州市","新沂市"],
    "常州": ["溧阳市"], "南通": ["启东市","如皋市","海安市"],
    "连云港": [], "淮安": [], "盐城": ["东台市"], "扬州": ["仪征市","高邮市"],
    "泰州": ["泰兴市","靖江市","兴化市"], "宿迁": [],
    "合肥":["庐阳区","包河区","瑶海区","蜀山区"],"芜湖":[],"蚌埠":[],"淮南":[],"马鞍山":[],
    "淮北":[],"铜陵":[],"安庆":[],"黄山":[],"滁州":[],"阜阳":[],"宿州":[],"六安":[],
    "亳州":[],"池州":[],"宣城":[],
}
USES = {
    "商业":r"商业|商铺|门面|零售|商场", "办公":r"办公|写字楼",
    "厂房":r"厂房|工业厂房", "仓储":r"仓储|仓库", "园区":r"产业园|工业园|科技园",
    "酒店":r"酒店|宾馆|旅馆", "住宅/公寓":r"住宅|公寓", "场地":r"场地|晒场",
    "配套":r"配套",
}
CLASS_FIELDS=["文章类型","项目城市","城市依据","用途分类","用途依据","价格类型","公司关系"]

def article_type(article):
    title=article["标题"]
    if re.search("流标|流拍|终止|撤销|更正|变更|延期",title):return "招租变更或状态公告"
    if re.search("成交公告|成交公示|成交结果|招租结果|竞价结果",title):return "交易结果公告"
    if re.search("招租|竞租|租赁招商",title) or re.search("【(?:竞价招租底价|招租底价)】",article["正文"]):return "招租公告"
    if re.search("招商|项目推介|资产推介",title):return "招商或项目推介"
    return "其他推送"

def classify_project(article,item,kind):
    address=item.get("项目位置","")
    hit=re.match(r"(?:中国)?(?:(?:江苏|安徽)省?)?("+"|".join(CITY_AREAS)+r")(?:市|(?=.{0,4}区))",address)
    places=[(city,area) for city,areas in CITY_AREAS.items() for area in areas if area in address]
    if hit:city,evidence=hit[1],hit[0]
    elif places and len({c for c,_ in places})==1:city,evidence=places[0]
    else:city,evidence="待核",""
    use=item.get("拟招租业态","")
    uses=[name for name,pattern in USES.items() if re.search(pattern,use)]
    price="待核"
    if kind=="招租公告" and item.get("挂牌底价元每年"):price="挂牌底价"
    elif kind=="交易结果公告":price="成交金额待核"
    elif not item.get("招租底价原文"):price="未提取租金"
    owner=item.get("出租方原文","")
    full_name="融通地产（江苏）有限责任公司"
    relation="公众号发布，项目主体待核"
    if owner:relation="江苏公司署名出租" if owner.replace("(","（").replace(")","）")==full_name else "另列出租主体，待核"
    elif re.search(re.escape(full_name)+r"[^。\n]{0,45}组织实施",article["正文"]):relation="原文明确江苏公司组织招租，逐标的出租方待核"
    return dict(zip(CLASS_FIELDS,[kind,city,evidence,"、".join(uses) or "待核",use,price,relation]))
