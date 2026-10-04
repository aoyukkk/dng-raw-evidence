"""Read-only classic TIFF/DNG inspection. Python standard library only.

Source file is opened for reading only. JPEG extraction and optional length-test
copies are written exclusively into a separate output directory, never over an
existing file. This is a structural inspection, not a full DNG SDK validator.
"""
import argparse
import hashlib
import struct
from pathlib import Path

NAMES = {254:'NewSubfileType',256:'ImageWidth',257:'ImageLength',258:'BitsPerSample',
         259:'Compression',262:'PhotometricInterpretation',271:'Make',272:'Model',
         273:'StripOffsets',277:'SamplesPerPixel',278:'RowsPerStrip',279:'StripByteCounts',
         330:'SubIFDs',50706:'DNGVersion',50707:'DNGBackwardVersion',
         50708:'UniqueCameraModel',50717:'WhiteLevel',50720:'DefaultCropSize',
         50829:'ActiveArea'}
SIZES = {1:1,2:1,3:2,4:4,5:8,6:1,7:1,8:2,9:4,10:8,11:4,12:8,13:4}
FORMATS = {1:'B',3:'H',4:'I',6:'b',7:'B',8:'h',9:'i',11:'f',12:'d',13:'I'}

def sha(b):
    return hashlib.sha256(b).hexdigest()

def address(n):
    return f'{n:,} (0x{n:X})'

class DNG:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.b = self.path.read_bytes()
        if self.b[:2] not in (b'II', b'MM'):
            raise ValueError('Not a TIFF byte-order header')
        self.en = '<' if self.b[:2] == b'II' else '>'
        if self.unpack('H',2)[0] != 42:
            raise ValueError('This script supports classic TIFF (42), not BigTIFF')
        self.dirs = []
        self.seen = set()
        self.walk(self.unpack('I',4)[0], 'IFD0')

    def unpack(self, fmt, at):
        return struct.unpack_from(self.en + fmt, self.b, at)

    def walk(self, off, name):
        if not off or off in self.seen:
            return
        if len(self.seen) >= 64:
            raise ValueError('Too many IFDs')
        self.seen.add(off)
        n = self.unpack('H',off)[0]
        if off+2+12*n+4 > len(self.b):
            raise ValueError('IFD extends beyond file')
        tags = {}
        for i in range(n):
            at = off + 2 + 12*i
            t, typ, count = self.unpack('HHI',at)
            if typ not in SIZES:
                continue
            length = SIZES[typ] * count
            loc = at+8 if length <= 4 else self.unpack('I',at+8)[0]
            data = self.b[loc:loc+length]
            if len(data) != length:
                raise ValueError(f'Tag {t} payload extends beyond file')
            if typ == 2:
                value = data.rstrip(b'\0').decode('utf-8','replace')
            elif typ in FORMATS:
                value = list(struct.unpack(self.en+str(count)+FORMATS[typ],data)) if count <= 1024 else f'{count} values'
            else:
                value = f'{length} bytes'
            tags[t] = {'value':value,'entry':at,'location':loc,'type':typ,'count':count,'raw':self.b[at:at+12]}
        self.dirs.append({'name':name,'offset':off,'tags':tags})
        for i, sub in enumerate(tags.get(330,{}).get('value',[])):
            self.walk(sub,f'{name}/SubIFD[{i}]')
        nxt = self.unpack('I',off+2+12*n)[0]
        if nxt:
            self.walk(nxt,name+'/NextIFD')

    def values(self, directory, tag):
        return directory['tags'].get(tag,{}).get('value',[])

    def scalar(self, directory, tag, default=None):
        v = self.values(directory,tag)
        return v[0] if isinstance(v,list) and v else default

    def raw_dirs(self):
        return [d for d in self.dirs if self.scalar(d,262) in (32803,34892) and not (self.scalar(d,254,0)&1)]

    def strips(self,d):
        offsets, lengths = self.values(d,273), self.values(d,279)
        if not offsets or not lengths or len(offsets)!=len(lengths):
            raise ValueError('Expected matching StripOffsets and StripByteCounts')
        return list(zip(offsets,lengths))

    def info(self):
        print('SOURCE:',self.path)
        print('FILE SIZE:',address(len(self.b)),'bytes')
        print('SHA256:',sha(self.b))
        print('HEADER:',self.b[:8].hex(' ').upper())
        print('BYTE ORDER:','little-endian (II)' if self.en=='<' else 'big-endian (MM)')
        print('TIFF MAGIC:',self.unpack('H',2)[0])
        print('FIRST IFD OFFSET:',address(self.unpack('I',4)[0]))

    def tags(self):
        for d in self.dirs:
            print('\nDIRECTORY:',d['name'],'at',address(d['offset']))
            for t,v in d['tags'].items():
                if t not in NAMES:
                    continue
                print(f"{NAMES[t]} [tag={t}, type={v['type']}, count={v['count']}] = {v['value']}")
                print(f"  entry @ {address(v['entry'])}; value/payload @ {address(v['location'])}; entry bytes: {v['raw'].hex(' ').upper()}")

    def ranges(self):
        for d in self.dirs:
            if 273 not in d['tags']:
                continue
            print('\nDIRECTORY:',d['name'])
            for i,(start,count) in enumerate(self.strips(d)):
                end = start+count
                available = max(0,min(end,len(self.b))-start)
                print('STRIP:',i)
                print('START:',address(start))
                print('DECLARED BYTE COUNT:',address(count))
                print('DECLARED END (exclusive):',address(end))
                print('FILE END (exclusive):',address(len(self.b)))
                print('AVAILABLE BYTES:',f'{available:,}')
                print('MISSING DECLARED BYTES:',f'{count-available:,}')
                print('WITHIN FILE:',end<=len(self.b))
            bits = self.values(d,258)
            if self.scalar(d,259)==1 and bits and len(set(bits))==1 and bits[0]%8==0:
                expected = self.scalar(d,256)*self.scalar(d,257)*self.scalar(d,277,1)*bits[0]//8
                print('UNCOMPRESSED width*height*samples*bits/8:',f'{expected:,}')

    def zeros(self):
        for d in self.raw_dirs():
            print('\nRAW DIRECTORY:',d['name'])
            print('COMPRESSION:',self.scalar(d,259),'(1 = uncompressed)')
            total=nonzero=missing=0
            for start,count in self.strips(d):
                stop = min(start+count,len(self.b))
                available = max(0,stop-start)
                missing += count-available
                print('SCANNING AVAILABLE RANGE:',address(start),'to',address(stop),'(end exclusive)')
                print('Chunk start (hex) | scanned bytes | nonzero bytes')
                for at in range(start,stop,1024*1024):
                    block = self.b[at:min(at+1024*1024,stop)]
                    nz = len(block)-block.count(0)
                    total += len(block)
                    nonzero += nz
                    print(f'0x{at:08X} | {len(block):>13,} | {nz:>13,}')
                for label,at in [('START',start),('MIDDLE',start+available//2),('END',max(start,stop-32))]:
                    print(label,address(at),':',self.b[at:min(at+32,stop)].hex(' ').upper())
            print('TOTAL SCANNED BYTES:',f'{total:,}')
            print('ZERO BYTES:',f'{total-nonzero:,}')
            print('NONZERO BYTES:',f'{nonzero:,}')
            print('UNAVAILABLE DECLARED BYTES:',f'{missing:,}')
            print('ALL AVAILABLE RAW BYTES ZERO:',total>0 and nonzero==0)
            print('Note: absent bytes are not counted as zero. This scans every available byte, not a sample.')
            if self.scalar(d,259)!=1:
                print('Compressed data: byte statistics alone do not establish decoded pixel values.')

def jpeg_stream(payload):
    """Walk JPEG marker lengths and entropy escaping to the primary EOI.
    Do not just search for FF D9: EXIF thumbnails may contain that sequence.
    Returns exclusive EOI offset and SOF fields. This does not decode pixels.
    """
    if payload[:2]!=b'\xff\xd8':
        raise ValueError('Preview strip does not start with JPEG SOI')
    pos=2
    frame=None
    while pos<len(payload):
        if payload[pos]!=255:
            raise ValueError(f'Expected JPEG marker at {pos}')
        while pos<len(payload) and payload[pos]==255:
            pos+=1
        if pos>=len(payload):
            break
        marker=payload[pos]
        pos+=1
        if marker==0xD9:
            return pos,frame
        if marker in (0xD8,0x01) or 0xD0<=marker<=0xD7:
            continue
        if pos+2>len(payload):
            break
        length=int.from_bytes(payload[pos:pos+2],'big')
        if length<2 or pos+length>len(payload):
            raise ValueError('Truncated JPEG segment')
        if marker in (0xC0,0xC1,0xC2,0xC3,0xC5,0xC6,0xC7,0xC9,0xCA,0xCB,0xCD,0xCE,0xCF):
            if length<8:
                raise ValueError('Short SOF')
            frame={'precision':payload[pos+2],'height':int.from_bytes(payload[pos+3:pos+5],'big'),
                   'width':int.from_bytes(payload[pos+5:pos+7],'big'),'components':payload[pos+7]}
        pos+=length
        if marker==0xDA:
            while pos<len(payload)-1:
                if payload[pos]!=255:
                    pos+=1
                    continue
                following=payload[pos+1]
                if following==0 or 0xD0<=following<=0xD7:
                    pos+=2
                    continue
                if following==255:
                    pos+=1
                    continue
                break
    raise ValueError('Primary JPEG EOI not found')

def write_new(path,b):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as f:
        f.write(b)
    print('CREATED:',path.resolve())
    print('BYTES:',f'{len(b):,}','SHA256:',sha(b))

def extract(dng,out):
    candidates=[d for d in dng.dirs if dng.scalar(d,259)==7 and dng.scalar(d,262) in (2,6)]
    for i,d in enumerate(candidates):
        strips=dng.strips(d)
        if len(strips)!=1:
            print('Skipping multi-strip preview; this extractor handles one JPEG strip.')
            continue
        start,count=strips[0]
        if start+count>len(dng.b):
            raise ValueError('Declared preview region is incomplete')
        region=dng.b[start:start+count]
        end,frame=jpeg_stream(region)
        print('\nJPEG DIRECTORY:',d['name'])
        print('REGION START:',address(start))
        print('DECLARED REGION BYTES:',f'{count:,}')
        print('PRIMARY JPEG STREAM BYTES:',f'{end:,}')
        print('PRIMARY JPEG END (exclusive, file offset):',address(start+end))
        print('EOI MARKER FILE OFFSET:',address(start+end-2))
        print('POST-EOI BYTES IN DECLARED REGION:',f'{count-end:,}')
        print('SOF FRAME:',frame)
        print('SOI:',region[:2].hex(' ').upper(),'EOI:',region[end-2:end].hex(' ').upper())
        prefix=dng.path.stem+f'_preview{i}'
        write_new(out/(prefix+'_declared_region.bin'),region)
        write_new(out/(prefix+'_primary.jpg'),region[:end])
        saved=(out/(prefix+'_primary.jpg')).read_bytes()
        print('EXTRACTED JPEG EXACTLY MATCHES SOURCE SLICE:',saved==dng.b[start:start+end])
        print('No image decoding, resampling, or recompression was performed.')

def length_test(dng,out):
    raw=dng.raw_dirs()
    if len(raw)!=1:
        raise ValueError('Length test expects one RAW image directory')
    target=max(start+count for start,count in dng.strips(raw[0]))
    deficit=target-len(dng.b)
    if not 0<deficit<=64*1024*1024:
        raise ValueError('No reasonable positive length deficit to test')
    print('SYNTHETIC EXPERIMENT: append zero bytes to a COPY; this does not restore RAW.')
    print('ZERO BYTES TO APPEND:',f'{deficit:,}')
    path=out/(dng.path.stem+'_LENGTH_TEST_ZERO_PADDED.dng')
    write_new(path,dng.b+bytes(deficit))
    print('ORIGINAL PREFIX PRESERVED:',path.read_bytes()[:len(dng.b)]==dng.b)
    print('Open original and this labeled test copy in the same Photoshop installation; record actual outcomes.')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('file',type=Path)
    p.add_argument('--step',choices=['info','tags','range','zero','jpeg','all','length-test'],default='info')
    p.add_argument('--out',type=Path,default=Path('dng_evidence_results'))
    args=p.parse_args()
    dng=DNG(args.file)
    original_hash=sha(dng.b)
    print('MODE:',args.step,'| SOURCE ACCESS: read-only')
    if args.step in ('info','all'):
        dng.info()
    else:
        print('SOURCE:',dng.path)
        print('SOURCE SHA256:',original_hash)
    if args.step in ('tags','all'): dng.tags()
    if args.step in ('range','all'): dng.ranges()
    if args.step in ('zero','all'): dng.zeros()
    if args.step in ('jpeg','all'): extract(dng,args.out.resolve())
    if args.step=='length-test': length_test(dng,args.out.resolve())
    current_hash=sha(dng.path.read_bytes())
    print('\nSOURCE HASH UNCHANGED:',current_hash==original_hash)
    if current_hash!=original_hash:
        raise RuntimeError('Source changed during inspection; do not treat this run as one stable sample')

if __name__=='__main__':
    main()
