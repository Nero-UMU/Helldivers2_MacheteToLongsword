"""Read original CQC-42 bank; extract inspection copies without changing any patches."""
import bpy,sys,os,importlib,struct,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'audio_inspection';DEST.mkdir(exist_ok=True)
sys.path.insert(0,str(Path(os.environ['APPDATA'])/'Blender Foundation/Blender/5.2/scripts/addons'))
sdk=importlib.import_module('HD2SDK-CommunityEdition')
for n in ('CheckBlenderVersion','CheckAddonUpToDate','UpdateArchiveHashes','UpdateFriendlyNames'):setattr(sdk,n,lambda:None)
sdk.register()
arc=sdk.Global_TocManager.LoadArchive(sdk.Global_gamepath+'f5014993c8402d87')
for e in arc.TocDict.get(sdk.WwiseDepID,{}).values():
    print('DEP',e.FileID,bytes(e.TocData),flush=True)
for e in arc.TocDict.get(sdk.WwiseBankID,{}).values():
    raw=bytes(e.TocData)
    (DEST/f'{e.FileID}.wwise_bank').write_bytes(raw)
    assert raw[16:20]==b'BKHD'
    bank=raw[16:];(DEST/f'{e.FileID}.bnk').write_bytes(bank)
    chunks={};offset=0
    while offset+8<=len(bank):
        tag=bank[offset:offset+4].decode('ascii');size=struct.unpack_from('<I',bank,offset+4)[0]
        chunks[tag]=bank[offset+8:offset+8+size];offset+=8+size
    print('BANK',e.FileID,'VERSION',struct.unpack_from('<I',chunks['BKHD'])[0]^0x9211BCAC,'CHUNKS',{k:len(v) for k,v in chunks.items()},flush=True)
    for tag,data in chunks.items():
        if tag not in ('DATA',):(DEST/f'{tag}.bin').write_bytes(data)
    media=[]
    for i in range(0,len(chunks.get('DIDX',b'')),12):
        mid,start,size=struct.unpack_from('<III',chunks['DIDX'],i)
        folder=DEST/'wem';folder.mkdir(exist_ok=True)
        data=chunks['DATA'][start:start+size];(folder/f'{mid}.wem').write_bytes(data)
        media.append({'id':mid,'size':size,'header':data[:32].hex()})
    hirc=chunks['HIRC'];count=struct.unpack_from('<I',hirc)[0];offset=4;objects=[]
    for i in range(count):
        typ=hirc[offset];size,oid=struct.unpack_from('<II',hirc,offset+1)
        objects.append({'id':oid,'type':typ,'size':size,'data':hirc[offset+9:offset+5+size].hex()})
        offset+=5+size
    result={'archive':'f5014993c8402d87','bank_id':str(e.FileID),'media':media,'objects':objects}
    (DEST/'bank_inventory.json').write_text(json.dumps(result,indent=2))
    print('EXTRACTED',len(media),'WEM',len(objects),'HIRC_OBJECTS',flush=True)
