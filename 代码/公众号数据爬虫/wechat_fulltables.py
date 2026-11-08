"""四片区公众号正文表图补采。分阶段导出清单、原图、单元格及条款。"""
from pathlib import Path
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit,urlunsplit
import csv,hashlib,json,os,re,sqlite3,sys,time,threading
import requests,cv2,numpy as np
from PIL import Image
from io import BytesIO
from lxml import html
from wechat_crawler import export_csv
BASE=Path(__file__).resolve().parent
ALBUMS=BASE/'outputs/公众号片区采集'
OUT=BASE/'outputs/群内提交/四片区基本情况表补采'
WORK=BASE/'outputs/表图缓存'
for p in [OUT,WORK,WORK/'识别',WORK/'图',WORK/'筛图']:p.mkdir(parents=True,exist_ok=True)
AREAS={'4167416190114906129':'南京','4167437118936891402':'苏北','4167473103481520130':'苏南','4167485713270620161':'安徽'}
def key(s):return hashlib.sha256(s.encode()).hexdigest()[:24]
def canonical(u):
 p=urlsplit(u);return urlunsplit(('https',p.netloc,p.path,p.query,''))
def dump(p,v):
 tmp=p.with_suffix(f'.{os.getpid()}.{threading.get_ident()}.tmp');tmp.write_text(json.dumps(v,ensure_ascii=False),'utf8');tmp.replace(p)
def inventory():
 records=[]
 for aid,name in AREAS.items():
    root=ALBUMS/aid
    with sqlite3.connect(root/'文章.sqlite3') as db:arts=[json.loads(r[0]) for r in db.execute('select data from articles')]
    def parse(a):
        text=(root/a['原文存档']).read_text('utf8'); raw=text[text.rfind('<',0,text.index('id="js_content"')):]
        tree=html.fromstring(raw);body=tree if tree.get('id')=='js_content' else tree.get_element_by_id('js_content')
        imgs=[]
        for i,img in enumerate(body.xpath('.//img'),1):
            u=img.get('data-src') or img.get('src') or ''
            if not u.startswith(('https://','http://')):continue
            u=canonical(u);imgs.append(dict(片区=name,原文链接=a['原文链接'],标题=a['标题'],发布日期=a['发布日期'],图序=i,图片链接=u,ID=key(u),宽=img.get('data-w',''),高宽比=img.get('data-ratio','')))
        return imgs
    with ThreadPoolExecutor(6) as ex:
        for imgs in ex.map(parse,arts): records.extend(imgs)
    print(name,len(arts),len(records),flush=True)
 export_csv(WORK/'全部图索引.csv',['片区','原文链接','标题','发布日期','图序','图片链接','ID','宽','高宽比'],records)
def read(p):
 with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def mask_lines(rgb,pale=False):
 g=rgb.min(axis=2) if pale else cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
 b=(g<(231 if pale else 180)).astype('uint8')
 h,w=b.shape
 vert=cv2.morphologyEx(b,cv2.MORPH_OPEN,np.ones((max(14,h//15),1),np.uint8))
 hor=cv2.morphologyEx(b,cv2.MORPH_OPEN,np.ones((1,max(16,w//10)),np.uint8))
 return vert,hor
def groups(x):
 return [int(np.mean(a)) for a in np.split(x,np.where(np.diff(x)>3)[0]+1) if len(a)]
def grid(rgb,pale=False):
 vert,hor=mask_lines(rgb,pale);h,w=vert.shape
 xs=groups(np.where(vert.sum(axis=0)>max(16,h*.115))[0]);ys=groups(np.where(hor.sum(axis=1)>max(20,w*.36))[0])
 return xs,ys,vert,hor
def urlcache():
 lookup={}
 for directory in list(ALBUMS.glob('*/图片缓存'))+[BASE/'outputs/南京片区合集试采/图片复核底稿/表图',BASE/'公众号采集结果/图片识别/图片']:
    if directory.exists():
        for f in directory.iterdir():
            if f.suffix.lower() in ['.jpeg','.jpg','.png','.gif','.webp']:lookup[f.stem]=f
 return lookup
SESSION=threading.local()
def decode_image(payload):
 if b'<svg' in payload[:1000]:
    import pymupdf
    with pymupdf.open(stream=payload,filetype='svg') as doc:
        page=doc[0];scale=min(1.0,1800/max(1,page.rect.width,page.rect.height))
        pix=page.get_pixmap(matrix=pymupdf.Matrix(scale,scale),alpha=False)
        return Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
 return Image.open(BytesIO(payload))
def screen():
 rows=read(WORK/'全部图索引.csv'); lookup=urlcache(); unique={r['ID']:r for r in rows}
 def work(r):
    id=r['ID'];u=r['图片链接'];record=WORK/'筛图'/(id+'.json')
    old=json.loads(record.read_text('utf8')) if record.exists() else {}
    revisit=('pale' in sys.argv and old.get('状态')=='未见规则表线' and not old.get('已筛浅色网格'))
    if record.exists() and '失败' not in old.get('状态','') and not revisit:return
    width=float(r['宽'] or 0);ratio=float(r['高宽比'] or 0)
    if width and (width<180 or (ratio and width*ratio<75)):
        dump(record,{'状态':'低尺寸装饰候选，未识别'});return
    try:
        f=lookup.get(hashlib.sha256(u.encode()).hexdigest());fmt=''
        if f:im=Image.open(f)
        else:
            if urlsplit(u).hostname not in ('mmbiz.qpic.cn','mmbiz.qlogo.cn'):raise ValueError('非微信图片域名')
            if not hasattr(SESSION,'s'):SESSION.s=requests.Session()
            resp=SESSION.s.get(u,timeout=(5,10),headers={'Referer':r['原文链接']});resp.raise_for_status();im=decode_image(resp.content)
        if im.width*im.height>40000000:raise ValueError('图像过大')
        rgb=im.convert('RGB');arr=np.asarray(rgb);xs,ys,_,_=grid(arr)
        tab=len(xs)>=4 and len(ys)>=3
        if not tab and (arr.min(axis=2)>225).mean()>.46:
            xs,ys,_,light=grid(arr,True)
            tab=len(xs)>=4 and sum(light[max(0,y-2):y+3].sum(axis=1).max()>.65*arr.shape[1] for y in ys)>=3
        if tab:rgb.save(WORK/'图'/(id+'.png'))
        dump(record,{'状态':'候选表图' if tab else '未见规则表线','列线':xs if tab else [],'行线':ys if tab else [],'尺寸':rgb.size,'已筛浅色网格':True})
    except Exception as e:dump(record,{'状态':'读取失败','问题':str(e)[:120]})
 with ThreadPoolExecutor(9) as ex:
    for i,_ in enumerate(ex.map(work,unique.values()),1):
        if i%500==0:print('筛图',i,'/',len(unique),flush=True)
if __name__=='__main__':
 if 'index' in sys.argv:inventory()
 if 'screen' in sys.argv:screen()
def ocr_engine():
 import rapidocr_onnxruntime.utils as util
 from onnxruntime import SessionOptions
 from rapidocr_onnxruntime import RapidOCR
 def options():
    opts=SessionOptions();opts.intra_op_num_threads=2;opts.inter_op_num_threads=1
    opts.add_session_config_entry("session.intra_op.allow_spinning","0")
    return opts
 util.SessionOptions=options
 cv2.setNumThreads(1);return RapidOCR()
def ocr_split(n,total):
 engine=ocr_engine()
 rows=read(WORK/'全部图索引.csv');urls={r['ID']:r['图片链接'] for r in rows}
 existing={f.stem:f for f in ALBUMS.glob('*/图片缓存/*.json')}
 files=sorted((WORK/'图').glob('*.png'))
 if 'extra' in sys.argv:
    files=[p for p in files if json.loads((WORK/'筛图'/(p.stem+'.json')).read_text('utf8'))['状态']=='基本情况段落补查']
 for j,f in enumerate(files[n::total]):
    dest=WORK/'识别'/(f.stem+'.json')
    if dest.exists():continue
    cached=existing.get(hashlib.sha256(urls[f.stem].encode()).hexdigest())
    try:
        if cached:
            o=json.loads(cached.read_text('utf8'));tokens=o.get('文字坐标')
        else:tokens=None
        if tokens is None:
            arr=np.asarray(Image.open(f).convert('RGB'));tokens,_=engine(arr[:,:,::-1].copy())
        dump(dest,{'tokens':tokens or []})
    except Exception as e:dump(dest,{'error':str(e)[:150]})
    if j%50==0:print(n,j,flush=True)
if __name__=='__main__' and 'ocr' in sys.argv:
 ocr_split(int(sys.argv[-2]),int(sys.argv[-1]))
# Table extraction deliberately retains the full OCR alongside normalized columns.
COLS=['序号','资产包编号','房地产位置','房屋面积','土地面积','水','电','消防','交付方式','申请主体要求','招租业态','竞价保证金','竞价招租底价','租赁期限','免租期','租金涨幅']
def sort_tokens(tokens):
 return sorted(tokens,key=lambda t:(int(t[2]//10),t[1]))
def category(h):
 n=''.join(h.split())
 patterns=[('竞价招租底价','招租底|租底价|租金底价|底价|招租价'),('竞价保证金','保证金|竞价保|证金'),('房地产位置','房地产位|坐落|地址|位置'),('房屋面积','房屋|建筑'),('土地面积','土地'),('交付方式','交付|交房'),('招租业态','招租业态|租赁业态|拟招|使用用途'),('申请主体要求','申请|主体'),('租赁期限','租赁期限|租赁期|年限|租期'),('免租期','免租'),('租金涨幅','涨幅|增长|递增|涨率'),('资产包编号','资产包'),('序号','序号'),('消防','消防'),('水','^水$'),('电','^电$')]
 if re.search('竞价招租.*年',n) and '保证' not in n:return '竞价招租底价'
 if re.search('水电消防',n):return None
 return next((k for k,pat in patterns if re.search(pat,n)),None)
def extract_cells(im,tokens):
 arr=np.asarray(im.convert('RGB'));h,w=arr.shape[:2];xs,ys,vert,hor=grid(arr)
 pts=[]
 for box,t,score in tokens:
    pts.append((t,float(np.mean([p[0] for p in box])),float(np.mean([p[1] for p in box])),float(score)))
 full=[y for y in ys if np.max(hor[max(y-2,0):y+3].sum(axis=1))>.68*w]
 if len(full)<4 or len(xs)<4:
    xx,yy,vv,hh=grid(arr,True)
    ff=[y for y in yy if np.max(hh[max(y-2,0):y+3].sum(axis=1))>.68*w]
    if len(ff)>len(full) or (len(ff)>=len(full) and len(xx)>len(xs)):
        xs,ys,vert,hor,full=xx,yy,vv,hh,ff
 if len(full)<2 or len(xs)<3:return [],[],[]
 # First full horizontal rule below header, before first clearly numeric data row.
 first=next((y for y in full if y>max(16,min(50,h*.045))),None)
 if first is None:return [],[],[]
 edges=sorted(set([first]+[y for y in full if y>first+4]))
 if edges[-1]<h-10:edges.append(h-1)
 cols=sorted(set(xs))
 if cols[0]>.035*w:cols.insert(0,0)
 if cols[-1]<.965*w:cols.append(w-1)
 def contents(x1,x2,y1,y2):return '\n'.join(t[0] for t in sort_tokens([t for t in pts if x1-1<=t[1]<x2+1 and y1<=t[2]<y2]))
 names=[contents(x1,x2,0,first) for x1,x2 in zip(cols,cols[1:])]
 keys_by_col=[category(n) for n in names]
 # Infer missing labels only for this specific template with aligned anchor columns.
 template=(len(names)==14 and keys_by_col[1]=='房地产位置' and
           keys_by_col[2:4]==['房屋面积','土地面积'] and
           keys_by_col[9]=='招租业态' and keys_by_col[10]=='竞价保证金' and
           (keys_by_col[11]=='竞价招租底价' or '竞价' in names[11]) and
           keys_by_col[12]=='租赁期限')
 if template:
    keys_by_col[:13]=['序号','房地产位置','房屋面积','土地面积','水','电','消防','交付方式','申请主体要求','招租业态','竞价保证金','竞价招租底价','租赁期限']
 short_table=(3<=len(keys_by_col)<=6 and ('房屋面积' in keys_by_col or '土地面积' in keys_by_col))
 if short_table and len(names)==4 and keys_by_col[2:]==['房屋面积','土地面积']:
    keys_by_col[1]='项目名称'
 cells=[];rs=[];notes=[]
 for j,(x1,x2) in enumerate(zip(cols,cols[1:])):
    cells.append([0,j+1,x1,0,x2,first,'表头','',names[j]])
 for i,(y1,y2) in enumerate(zip(edges,edges[1:]),1):
    if y2-y1<7:continue
    actual=[cols[0]]+[x for x in cols[1:-1] if np.any(vert[y1+2:y2-1,max(x-2,0):x+3].sum(axis=0)>.45*(y2-y1))]+[cols[-1]]
    is_note=len(actual)<=4 and not(short_table and len(actual)>=4)
    row={};unmap=[];vals=[]
    for j,(x1,x2) in enumerate(zip(actual,actual[1:]),1):
        v=contents(x1,x2,y1,y2); vals.append(v)
        heads=[(n,k) for n,k,a,b in zip(names,keys_by_col,cols,cols[1:]) if x1<=(a+b)/2<=x2]
        hs=' / '.join(n for n,_ in heads if n)
        cells.append([i,j,x1,y1,x2,y2,'数据或说明',hs,v])
        if is_note:continue
        keys=list(dict.fromkeys(k for _,k in heads if k))
        if len(keys)==1 and len(heads)==1:
            key=keys[0];row[key]='\n'.join(filter(None,[row.get(key),v]))
            if key in ('竞价保证金','竞价招租底价','房屋面积','土地面积'):
                row[key+'表头原文']=hs
        elif v:
            label='、'.join(keys) if keys else f'列{j}'
            unmap.append(f'{label}：{v}')
    if is_note:
        if any(vals):notes.append((i,'\n'.join(filter(None,vals))))
    elif any(vals):
        row['图内行序']=i;row['表头匹配依据']='表头文字及已对齐的模板列序' if template else '仅表头文字'
        row['未映射或合并列OCR']=' | '.join(unmap);rs.append(row)
 return cells,rs,notes

def publish():
 rows=read(WORK/'全部图索引.csv'); byid=defaultdict(list)
 for r in rows:byid[r['ID']].append(r)
 inv=[]; wide=[];cells=[];notes=[]; texts=[]; images=[]
 for uid,occ in byid.items():
    st=WORK/'筛图'/(uid+'.json'); flag=json.loads(st.read_text('utf8')) if st.exists() else {'状态':'未筛'}
    for r in occ:inv.append(dict(r,筛查=flag['状态'],问题=flag.get('问题','')))
    if flag['状态'] not in ('候选表图','基本情况段落补查'):continue
    f=WORK/'识别'/(uid+'.json'); dat=json.loads(f.read_text('utf8')) if f.exists() else {'error':'未完成OCR'}
    tokens=dat.get('tokens',[])
    supplement=WORK/'补格'/(uid+'.json')
    if supplement.exists():tokens=tokens+json.loads(supplement.read_text('utf8')).get('tokens',[])
    fulltext='\n'.join(t for _,t,_ in tokens)
    compact=fulltext.replace('\n','')
    score=sum(bool(re.search(p,compact)) for p in ('底价|租底','保证金|竞价保','竞价','房地产位|房屋面积|建筑面积|土地面积','承租|招租|出租','特别说明|交付方式|租赁期限'))
    if re.search('建筑面积|房屋面积',compact) and re.search('项目名称|土地面积',compact):score=max(2,score)
    kind=('疑似项目表，需复核' if score>=2 else '其他网格或表头难辨')
    im=Image.open(WORK/'图'/(uid+'.png'))
    cc,rr,nn=extract_cells(im,tokens) if score>=2 or flag['状态']=='候选表图' else ([],[],[])
    if score>=2 and not rr and not nn and len(re.findall(r'(?:^|\n)\s*\d{1,2}[.．、]',fulltext))>=2:
        nn=[('整图，条款续页或行界待核',fulltext)]
    for r in occ:
        base={k:r[k] for k in ['片区','原文链接','标题','发布日期','图序','图片链接','ID']}
        texts.append(dict(base,判定=kind,识别问题=dat.get('error',''),全图OCR=fulltext))
        for v in cc:cells.append(dict(base,判定=kind,**dict(zip(['图内行序','图内列序','左','上','右','下','区域','对应表头OCR','内容OCR'],v))))
        if score<2:continue
        images.append(dict(base,表内数据行数=len(rr),说明区块数=len(nn),识别状态='机器提取，需核图' if rr else '行结构待核'))
        for v in rr:wide.append(dict(base,**v))
        for j,t in nn:notes.append(dict(base,图内行序=j,说明区文字OCR=t))
 k=['片区','原文链接','标题','发布日期','图序','图片链接','ID']
 export_csv(OUT/'01_项目表格行.csv',k+['图内行序','项目名称']+COLS+[c+'表头原文' for c in ('房屋面积','土地面积','竞价保证金','竞价招租底价')]+['未映射或合并列OCR','表头匹配依据'],wide)
 export_csv(OUT/'02_特别说明等合并区.csv',k+['图内行序','说明区文字OCR'],notes)
 export_csv(OUT/'03_全部单元格含表头.csv',k+['判定','图内行序','图内列序','左','上','右','下','区域','对应表头OCR','内容OCR'],cells)
 export_csv(OUT/'04_网格候选图全文OCR.csv',k+['判定','识别问题','全图OCR'],texts)
 export_csv(OUT/'05_项目表图定位.csv',k+['表内数据行数','说明区块数','识别状态'],images)
 export_csv(OUT/'06_正文图片筛查台账.csv',['片区','原文链接','标题','发布日期','图序','图片链接','ID','宽','高宽比','筛查','问题'],inv)
 print('导出',len(images),len({r['ID'] for r in images}),len(wide),len(cells),len(notes),'候选',len(texts),flush=True)
def context():
 """Check images under explicit project headings, including borderless images, and export native HTML table cells."""
 selected={}; native=[]
 for aid,name in AREAS.items():
    root=ALBUMS/aid
    with sqlite3.connect(root/'文章.sqlite3') as db:
        arts=[json.loads(r[0]) for r in db.execute('select data from articles')]
    for a in arts:
        text=(root/a['原文存档']).read_text('utf8')
        raw=text[text.rfind('<',0,text.index('id="js_content"')):]
        tree=html.fromstring(raw);body=tree if tree.get('id')=='js_content' else tree.get_element_by_id('js_content')
        base=dict(片区=name,原文链接=a['原文链接'],标题=a['标题'],发布日期=a['发布日期'])
        for ti,table in enumerate(body.xpath('.//table'),1):
            if not re.search('面积|房地产|项目地址|招租|底价|承租|保证金',table.text_content()):continue
            for ri,tr in enumerate(table.xpath('./tr|./thead/tr|./tbody/tr|./tfoot/tr'),1):
                for ci,td in enumerate(tr.xpath('./th|./td'),1):
                    native.append(dict(base,网页表序=ti,行序=ri,格序=ci,跨行=td.get('rowspan','1'),跨列=td.get('colspan','1'),内容=' '.join(td.text_content().split())))
        active=False
        for element in body.xpath('.//text()|.//img'):
            if isinstance(element,str):
                s=''.join(element.split())
                if re.search('项目基本情况|项目基本信息|项目情况表|项目基本概况|项目概况表',s):active=True
                elif re.search('项目图片|项目简介|位置图|竞价详情|报名方式|项目地址|项目位置|实景图|项目介绍|招商热线|项目照片|项目周边',s):active=False
                continue
            u=element.get('data-src') or element.get('src','')
            if active and u.startswith(('https://','http://')):
                u=canonical(u);selected[key(u)]=(u,a['原文链接'])
 export_csv(OUT/'07_网页原生表格单元格.csv',['片区','原文链接','标题','发布日期','网页表序','行序','格序','跨行','跨列','内容'],native)
 def extra(item):
    uid,(u,ref)=item;st=WORK/'筛图'/(uid+'.json')
    d=json.loads(st.read_text('utf8')) if st.exists() else {}
    if d.get('状态') in ('候选表图','基本情况段落补查'):return
    if d.get('尺寸') and min(d['尺寸'])<48:return
    try:
        if urlsplit(u).hostname not in ('mmbiz.qpic.cn','mmbiz.qlogo.cn'):return
        resp=requests.get(u,timeout=(5,12),headers={'Referer':ref});resp.raise_for_status()
        im=decode_image(resp.content)
        if min(im.size)<48 or im.width*im.height>40000000:return
        rgb=im.convert('RGB');rgb.save(WORK/'图'/(uid+'.png'))
        dump(st,dict(d,状态='基本情况段落补查',尺寸=im.size))
    except Exception as e:dump(st,dict(d,状态='读取失败',问题=str(e)[:120]))
 with ThreadPoolExecutor(7) as ex:list(ex.map(extra,selected.items()))
 print('段落命中图',len(selected),'网页原生格',len(native),flush=True)
def fill_blanks(n,total):
 """Run line recognition inside ink-bearing cells missed by page detection."""
 dest=WORK/'补格';dest.mkdir(exist_ok=True)
 engine=ocr_engine()
 files=sorted((WORK/'识别').glob('*.json'))
 for f in files[n::total]:
    out=dest/f.name
    if out.exists():
        prior=json.loads(out.read_text('utf8'))
        if 'refill' not in sys.argv or prior.get('tokens') or prior.get('version')==2:continue
    tokens=json.loads(f.read_text('utf8')).get('tokens',[])
    full=''.join(t for _,t,_ in tokens)
    if not re.search('竞价|招租|承租|保证金|房地产|土地面积|房屋面积',full):continue
    im=Image.open(WORK/'图'/(f.stem+'.png')).convert('RGB')
    cc,_,_=extract_cells(im,tokens)
    arr=np.asarray(im);g=cv2.cvtColor(arr,cv2.COLOR_RGB2GRAY)
    strips=[];boxes=[]
    for ri,ci,x1,y1,x2,y2,_,_,v in cc:
        if v.strip() or x2-x1<12 or y2-y1<10:continue
        left,top,right,bottom=x1+3,y1+3,x2-2,y2-2
        roi=g[top:bottom,left:right]
        if not roi.size:continue
        ink=roi<155
        yy=np.where(ink.sum(axis=1)>=2)[0]
        for run in np.split(yy,np.where(np.diff(yy)>2)[0]+1):
            if len(run)<4:continue
            if (ink[run].sum(axis=1)>.87*ink.shape[1]).any():continue
            xx=np.where(ink[run].any(axis=0))[0]
            if len(xx)<2:continue
            l=max(left,left+int(xx[0])-2);r=min(right,left+int(xx[-1])+3)
            t=max(top,top+int(run[0])-2);b=min(bottom,top+int(run[-1])+3)
            if (r-l)/(b-t)>60 or (r-l)<2 or (b-t)<4:continue
            strips.append(arr[t:b,l:r,::-1].copy());boxes.append([[l,t],[r,t],[r,b],[l,b]])
    extra=[]
    if strips:
        results,_=engine.text_recognizer(strips)
        extra=[[box,txt,str(score)] for box,(txt,score) in zip(boxes,results) if txt and score>=.70]
    dump(out,{'tokens':extra,'version':2})
if __name__=='__main__' and 'fill' in sys.argv:fill_blanks(int(sys.argv[-2]),int(sys.argv[-1]))
if __name__=='__main__' and 'context' in sys.argv:context()
if __name__=='__main__' and 'publish' in sys.argv:publish()
def coverage():
 rows=read(OUT/'06_正文图片筛查台账.csv')
 pics=read(OUT/'05_项目表图定位.csv')
 wide=read(OUT/'01_项目表格行.csv')
 text=read(OUT/'04_网格候选图全文OCR.csv')
 notes=read(OUT/'02_特别说明等合并区.csv')
 native=read(OUT/'07_网页原生表格单元格.csv')
 cells=read(OUT/'03_全部单元格含表头.csv')
 stats=[]
 for aid,area in AREAS.items():
    filt=lambda ls:[r for r in ls if r['片区']==area]
    rs,ps,ws,ts,ns,hs=map(filt,(rows,pics,wide,text,notes,native))
    occ=lambda ls:len({(r['原文链接'],r['图序']) for r in ls})
    stats.append(dict(片区=area,存档文章数=len(read(ALBUMS/aid/'文章.csv')),正文图片出现次数=len(rs),
        图像识别候选出现次数=len(ts),项目表图候选出现次数=len(ps),有可拆行的候选图次=occ(ws),项目表候选行=len(ws),
        底价列有OCR文字的行=sum(bool(r['竞价招租底价'].strip()) for r in ws),
        特别说明等合并区块=len(ns),原生表格单元格=len(hs),图片读取失败出现次数=sum(r['筛查']=='读取失败' for r in rs)))
 export_csv(OUT/'四片区覆盖统计.csv',list(stats[0]),stats)
 f=OUT/'四片区金额抽查_逐图核对.csv'
 if f.exists():
    checks=read(f)
    for c in checks:
        vv=[r for r in wide if r['ID']==c['ID'] and r['原文链接']==c['原文链接']]
        for col,truth in [('竞价保证金','竞价保证金（万元）'),('竞价招租底价','竞价招租底价（万元/年）')]:
            c[col+'机器原值']=' / '.join(r[col] for r in vv)
            c[col+'机器表头']=' / '.join(r[col+'表头原文'] for r in vv)
            v=re.sub(r'[（(]不含税[）)]','',re.sub(r'\s','',c[col+'机器原值']))
            c[col+'数值抽查']='同值（单位另核）' if re.fullmatch(r'\d+(?:\.\d+)?',v) and float(v)==float(c[truth]) else '缺值或不一致'
    export_csv(f,list(checks[0]),checks)
 print('文章图次',len(rows),'唯一图',len({r['ID'] for r in rows}),'候选OCR',len(text),'唯一OCR',len({r['ID'] for r in text}),
       '疑似项目图次',len(pics),'唯一疑似',len({r['ID'] for r in pics}),'拆行图次',len({(r['原文链接'],r['图序']) for r in wide}),
       '候选行',len(wide),'说明块',len(notes),'单元格',len(cells),'原生格',len(native))
 print('筛查（独立URL）',Counter({k:len({r['ID'] for r in rows if r['筛查']==k}) for k in set(r['筛查'] for r in rows)}))
 print('识别失败',sum(bool(r['识别问题']) for r in text))
 print('有底价字段',sum(bool(r['竞价招租底价'].strip()) for r in wide))
if __name__=='__main__' and 'coverage' in sys.argv:coverage()
if __name__=='__main__' and len(sys.argv)>=4 and sys.argv[1]=='album':
 root=Path(sys.argv[2]).resolve()
 if not (root/'文章.sqlite3').is_file():sys.exit('缺少已采文章数据库')
 area=AREAS.get(root.name,sys.argv[3])
 AREAS={root.name:area};ALBUMS=root.parent
 OUT=root/'交付文件/项目基本情况表';WORK=root/'表图缓存'
 for p in [OUT,WORK,WORK/'识别',WORK/'图',WORK/'筛图']:p.mkdir(parents=True,exist_ok=True)
 inventory();screen();context();ocr_split(0,1);fill_blanks(0,1);publish();coverage()



