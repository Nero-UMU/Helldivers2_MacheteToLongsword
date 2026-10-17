import json, zipfile
from pathlib import Path

root=Path(__file__).resolve().parents[1]
report=json.loads((root/'validation_report.json').read_text(encoding='utf-8'))
assert report['status']=='PASS'
assert report['text']['status']=='PASS'
assert report['audio']['status']=='PASS'
files=list((root/'output').glob('9ba626afa44a3aa3.patch_0*'))
assert len(files)==3
files += [root/'manifest.json',root/'README_安装说明.md']
dest=root/'Fatalis_CQC42_Mod.zip'
with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED) as z:
    for file in files:z.write(file,arcname=file.name)
with zipfile.ZipFile(dest) as z:
    assert z.testzip() is None
    print(json.dumps({'zip':str(dest),'size':dest.stat().st_size,'files':z.namelist()},ensure_ascii=False))
