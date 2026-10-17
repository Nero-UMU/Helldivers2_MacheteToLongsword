"""CQC-42 Simplified Chinese strings, using the Audio Modder TextBank layout."""
import struct

BANK_ID=10803731882318123174
LANGUAGE=1497550071
NAME='黑龙歼灭刀'
DESCRIPTION='只要被其砍伤后伤口就无法愈合，即使百年后仍将受伤痛的折磨。'
REPLACEMENTS={2217787087:NAME,3631119937:NAME,1561103553:DESCRIPTION}
ORIGINALS={2217787087:'砍刀',3631119937:'砍刀',1561103553:'沉重的单手刀。挥舞速度比其他近战武器慢，但造成的伤害更高。'}

def read_bank(data):
    count,language=struct.unpack_from('<II',data,8)
    ids=struct.unpack_from(f'<{count}I',data,16)
    offsets=struct.unpack_from(f'<{count}I',data,16+4*count)
    strings=[data[o:data.index(b'\0',o)].decode('utf-8') for o in offsets]
    return language,dict(zip(ids,strings))

def replace_bank(data):
    language,strings=read_bank(data)
    assert language==LANGUAGE
    for sid,old in ORIGINALS.items():assert strings[sid]==old,(sid,strings[sid])
    count=len(strings)
    offsets=[];payload=bytearray()
    for sid,old in strings.items():
        offsets.append(16+8*count+len(payload))
        payload.extend(REPLACEMENTS.get(sid,old).encode('utf-8')+b'\0')
    result=bytes(data[:16])+struct.pack(f'<{count}I',*strings)+struct.pack(f'<{count}I',*offsets)+payload
    verify_bank(bytes(data),bytes(result))
    return result

def verify_bank(original,patched):
    lang,before=read_bank(original);new_lang,after=read_bank(patched)
    assert lang==new_lang==LANGUAGE
    assert list(before)==list(after)
    changed={sid for sid in before if before[sid]!=after[sid]}
    assert changed==set(REPLACEMENTS),changed
    for sid,text in REPLACEMENTS.items():assert after[sid]==text
    return {'status':'PASS','language':'简体中文','bank_id':str(BANK_ID),'total_strings':len(after),'changed_strings':[{'id':sid,'before':before[sid],'after':after[sid]} for sid in REPLACEMENTS]}

def add_to_patch(sdk,base,patch):
    from copy import deepcopy
    original=base.GetEntry(BANK_ID,sdk.StringID)
    assert original is not None
    entry=deepcopy(original)
    entry.SetData(replace_bank(bytes(original.TocData)),original.GpuData,original.StreamData)
    patch.AddEntry(entry,override=True,ReloadUI=False)
