"""Run the complete read-only inspection of the two adjacent DNG samples."""
import argparse
import contextlib
import io
import json
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

import dng_evidence as ev

BASE = Path(__file__).resolve().parent
FILES = ['IMG_20261003_205510.dng', 'IMG_20261003_205503.dng']

def summary(dng):
    raw = dng.raw_dirs()[0]
    total = nz = missing = 0
    for start,count in dng.strips(raw):
        data = dng.b[start:min(start+count,len(dng.b))]
        total += len(data)
        nz += len(data)-data.count(0)
        missing += count-len(data)
    return {'文件名':dng.path.name,'SHA256':ev.sha(dng.b),'文件字节数':len(dng.b),
            'RAW宽':dng.scalar(raw,256),'RAW高':dng.scalar(raw,257),
            'RAW存储位深':dng.values(raw,258),'RAW压缩标记':dng.scalar(raw,259),
            'RAW起点':[a for a,b in dng.strips(raw)],
            'RAW声明长度':[b for a,b in dng.strips(raw)],
            'RAW实际扫描字节数':total,'RAW零字节数':total-nz,
            'RAW非零字节数':nz,'RAW声明范围缺少字节数':missing}

def compact_tags(dng, directory):
    print('文件：',dng.path)
    print('目录：',directory['name'],'；目录起点：',ev.address(directory['offset']))
    for tag in [254,256,257,258,259,262,277,273,279,330]:
        if tag not in directory['tags']:
            continue
        item=directory['tags'][tag]
        print(f"{ev.NAMES[tag]} = {item['value']}")
        print(f"  条目偏移 {item['entry']} / 0x{item['entry']:X}；值偏移 {item['location']} / 0x{item['location']:X}")
        print('  原始12字节：',item['raw'].hex(' ').upper())

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--outdir',type=Path,help='Optional output root')
    args=parser.parse_args()
    paths=[BASE/name for name in FILES]
    missing=[str(p) for p in paths if not p.is_file()]
    if missing:
        raise FileNotFoundError('请把以下DNG放回脚本所在文件夹：\n'+'\n'.join(missing))
    now=datetime.now(timezone(timedelta(hours=8)))
    root=args.outdir.resolve() if args.outdir else BASE/'检查结果'
    result=root/now.strftime('%Y%m%d_%H%M%S')
    number=1
    while result.exists():
        result=root/(now.strftime('%Y%m%d_%H%M%S')+f'_{number}')
        number+=1
    result.mkdir(parents=True,exist_ok=False)
    dngs=[ev.DNG(p) for p in paths]
    before=[ev.sha(d.b) for d in dngs]
    first,other=dngs
    recorded=[]

    print('DNG 证据链检查 — 原文件只读')
    print('检查目录：',BASE)
    print('北京时间：',now.strftime('%Y-%m-%d %H:%M:%S %z'))
    print('结果目录：',result)

    def stage(number,title,fn,show=True):
        heading=f'第 {number} 步 / {title}'
        print('\n'+'='*72+'\n'+heading+'\n'+'='*72)
        capture=io.StringIO()
        with contextlib.redirect_stdout(capture):
            fn()
        data=capture.getvalue()
        logfile=result/f'{number:02d}_{title}.txt'
        logfile.write_text(heading+'\n\n'+data,encoding='utf-8-sig')
        recorded.append(logfile.name)
        if show:
            print(data,end='')
        else:
            print('完整逐块统计已写入：',logfile)
        print('\n本步日志：',logfile)

    def identities():
        for d in dngs:
            d.info()
            print()
    stage(1,'文件身份与SHA256',identities)
    preview=next(d for d in first.dirs if first.scalar(d,259)==7 and first.scalar(d,262) in (2,6))
    stage(2,'205510的JPEG预览目录',lambda:compact_tags(first,preview))
    stage(3,'205510的RAW目录',lambda:compact_tags(first,first.raw_dirs()[0]))
    stage(4,'205510的长度范围计算',first.ranges)
    stage(5,'205510的RAW全量零统计',first.zeros)
    stage(6,'205510的JPEG原字节提取',lambda:ev.extract(first,result/'提取JPEG'))
    stage(7,'205503的长度范围计算',other.ranges)

    def other_zero():
        other.zeros()
        s=summary(other)
        print('\nRAW区段是否全零：',s['RAW实际扫描字节数']>0 and s['RAW非零字节数']==0)
        print('非零字节数：',f"{s['RAW非零字节数']:,}")
        print('字节统计不等同于完整图像解码验证。')
    stage(8,'205503的RAW全量统计',other_zero)
    summaries=[summary(d) for d in dngs]

    def compare():
        for s in summaries:
            print('文件：',s['文件名'])
            for key in ['文件字节数','RAW存储位深','RAW实际扫描字节数','RAW零字节数','RAW非零字节数','RAW声明范围缺少字节数']:
                v=s[key]
                print(f'  {key}: {v:,}' if isinstance(v,int) else f'  {key}: {v}')
            print()
        print('16 bit 是文件的存储标记，不能据此证明传感器原生有效精度。')
        print('缺少的字节不存在，不能把它们计为零。')
        print('长度越界证明结构问题，不能单独证明PS报错的唯一原因。')
        print('JPEG提取是复制内嵌成片，不是恢复RAW。')
    stage(9,'两张文件对照与结论边界',compare)

    verified=[]
    def integrity():
        for d,original in zip(dngs,before):
            current=ev.sha(d.path.read_bytes())
            ok=current==original
            verified.append(ok)
            print('文件：',d.path.name)
            print('检查前SHA256：',original)
            print('检查后SHA256：',current)
            print('原文件字节保持不变：',ok)
            print()
        if not all(verified):
            raise RuntimeError('检测到源文件在检查期间发生变化，请勿把本次结果当成同一稳定样本。')
    stage(10,'原文件未修改验证',integrity)
    for s,ok in zip(summaries,verified):
        s['检查前后哈希一致']=ok
    (result/'实测摘要.json').write_text(json.dumps(summaries,ensure_ascii=False,indent=2),encoding='utf-8')
    all_logs='\n\n'.join((result/name).read_text(encoding='utf-8-sig') for name in recorded)
    (result/'完整检查日志.txt').write_text(all_logs,encoding='utf-8-sig')
    print('\n检查完成。')
    print('全部日志和摘要：',result)
    print('提取的纯JPEG：',result/'提取JPEG'/'IMG_20261003_205510_preview0_primary.jpg')

if __name__=='__main__':
    try:
        main()
    except Exception:
        print('\n检查未完成，下面是实际错误：')
        traceback.print_exc()
        raise SystemExit(1)
