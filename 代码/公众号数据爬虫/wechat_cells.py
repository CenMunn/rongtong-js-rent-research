"""数值单元格的漏行定位与跨行拼接；原OCR和坐标由调用方保留。"""
import re
import numpy as np
import cv2

def repair_numeric_cell(rgb,bounds,tokens,recognizer):
    x1,y1,x2,y2=bounds
    inside=[t for t in tokens if x1<sum(p[0] for p in t[0])/4<x2 and y1<sum(p[1] for p in t[0])/4<y2]
    inside.sort(key=lambda t:sum(p[1] for p in t[0])/4)
    raw='\n'.join(t[1] for t in inside)
    audit={'原单元格OCR':raw,'状态':'未补读','边界':list(bounds)}
    if len(inside)!=1 or not re.fullmatch(r'\d+(?:\.\d*)?',inside[0][1].strip()):return [],audit
    missing=uncovered_strips(rgb,bounds,tokens)
    if not missing:return [],audit
    lines=uncovered_strips(rgb,bounds,[])
    if not 2<=len(lines)<=3:return [],audit
    # 仅把同格的墨迹行横向排开再识别，避免单个小数字置信度过低。
    tiles=[]
    for img,_ in lines:
        tile=img[5:-5,5:-5]
        tiles.append(cv2.resize(tile,(max(1,round(tile.shape[1]*32/tile.shape[0])),32)))
    flattened=cv2.copyMakeBorder(np.hstack(tiles),5,5,5,5,cv2.BORDER_CONSTANT,value=(255,255,255))
    results,_=recognizer([flattened])
    if len(results)!=1:return [],audit
    text,score=results[0];value=''.join(text.split());prefix=inside[0][1].strip()
    audit.update(重排识别原文=text,候选值=value,整格识别分数=float(score),状态='候选待复核')
    if float(score)<.80 or not re.fullmatch(r'\d+(?:\.\d+)?',value):return [],audit
    if not value.startswith(prefix) or not re.fullmatch(r'\d{1,6}',value[len(prefix):]):return [],audit
    # 待补字符必须在已有数字下方，且位于同一数字列。
    known_bottom=max(p[1] for p in inside[0][0]);known_x=sum(p[0] for p in inside[0][0])/4
    for _,box in missing:
        if min(p[1] for p in box)<known_bottom-2 or abs(sum(p[0] for p in box)/4-known_x)>.3*(x2-x1):return [],audit
    boxes=[p for _,box in missing for p in box];l=min(p[0] for p in boxes);r=max(p[0] for p in boxes);t=min(p[1] for p in boxes);b=max(p[1] for p in boxes)
    audit['状态']='同格跨行补读候选，原图仍需复核'
    return [[[[l,t],[r,t],[r,b],[l,b]],value[len(prefix):],float(score)]],audit

def numeric_cell_text(text):
    lines=[x.strip() for x in text.splitlines() if x.strip()]
    if len(lines)<2:
        return text
    # 不拼接两个完整小数、区间、带标签的多期报价或单位不同的数字。
    if not re.fullmatch(r'\d+(?:\.\d*)?',lines[0]):
        return text
    if not all(re.fullmatch(r'\d+',x) for x in lines[1:]):
        return text
    return ''.join(lines)

def uncovered_strips(rgb,bounds,tokens):
    """只寻找本单元格内未被已有OCR框覆盖的墨迹行，不跨格借数字。"""
    x1,y1,x2,y2=map(int,bounds)
    left,top,right,bottom=x1+3,y1+3,x2-2,y2-2
    roi=rgb[top:bottom,left:right]
    if not roi.size:return []
    gray=cv2.cvtColor(roi,cv2.COLOR_RGB2GRAY);ink=gray<155
    yy=np.where(ink.sum(axis=1)>=2)[0]
    result=[]
    for run in np.split(yy,np.where(np.diff(yy)>4)[0]+1):
        if len(run)<4:continue
        if (ink[run].sum(axis=1)>.87*ink.shape[1]).any():continue
        xx=np.where(ink[run].any(axis=0))[0]
        if len(xx)<2:continue
        l=left+int(xx[0]);r=left+int(xx[-1])+1;t=top+int(run[0]);b=top+int(run[-1])+1
        if r-l<2 or b-t<4 or (r-l)/(b-t)>60:continue
        covered=False
        for box,_,_ in tokens:
            bx1=min(p[0] for p in box);bx2=max(p[0] for p in box);by1=min(p[1] for p in box);by2=max(p[1] for p in box)
            overlap=max(0,min(r,bx2)-max(l,bx1))*max(0,min(b,by2)-max(t,by1))
            if overlap/((r-l)*(b-t))>=.55:covered=True;break
        if covered:continue
        l=max(left,l-2);r=min(right,r+2);t=max(top,t-2);b=min(bottom,b+2)
        crop=rgb[t:b,l:r]
        scale=max(1,32/crop.shape[0])
        enlarged=cv2.resize(crop,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
        padded=cv2.copyMakeBorder(enlarged,5,5,5,5,cv2.BORDER_CONSTANT,value=(255,255,255))
        result.append((padded[:,:,::-1].copy(),[[l,t],[r,t],[r,b],[l,b]]))
    return result
