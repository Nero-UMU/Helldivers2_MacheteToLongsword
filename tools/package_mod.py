import json, struct, zipfile
from pathlib import Path

root=Path(__file__).resolve().parents[1]
report=json.loads((root/'validation_report.json').read_text(encoding='utf-8'))
assert report['status']=='PASS'
assert report['audio']['status']=='PASS'
patch=root/'output/9ba626afa44a3aa3.patch_0'
data=patch.read_bytes()
types,count=struct.unpack_from('<II',data,4)
for i in range(count):
    type_id=struct.unpack_from('<Q',data,72+32*types+80*i+8)[0]
    if type_id==979299457696010195:
        raise ValueError('The patch must not contain game text resources')
files=[patch,patch.with_suffix('.patch_0.gpu_resources'),patch.with_suffix('.patch_0.stream')]
files += [root/'manifest.json',root/'README_安装说明.md']
dest=root/'Fatalis_CQC42_Mod.zip'
with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED) as z:
    for file in files:z.write(file,arcname=file.name)
with zipfile.ZipFile(dest) as z:
    assert z.testzip() is None
    print(json.dumps({'zip':str(dest),'size':dest.stat().st_size,'files':z.namelist()},ensure_ascii=False))
