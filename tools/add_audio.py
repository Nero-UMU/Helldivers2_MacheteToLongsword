"""Add audio and verify that existing model, texture and text payloads survive unchanged."""
import importlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(Path(os.environ['APPDATA']) / 'Blender Foundation/Blender/5.2/scripts/addons'))
from audio_patch import BANK_ID, add_audio_bank
from text_patch import BANK_ID as TEXT_ID, verify_bank

sdk = importlib.import_module('HD2SDK-CommunityEdition')
for name in ('CheckBlenderVersion', 'CheckAddonUpToDate', 'UpdateArchiveHashes', 'UpdateFriendlyNames'):
    setattr(sdk, name, lambda: None)
sdk.register()
path = ROOT / 'output/9ba626afa44a3aa3.patch_0'
patch = sdk.StreamToc(); assert patch.FromFile(str(path))
before = {(e.TypeID, e.FileID): tuple(bytes(d) for d in e.GetData())
          for entries in patch.TocDict.values() for e in entries.values() if e.TypeID != sdk.WwiseBankID}
assert len(before) == 6
add_audio_bank(sdk, patch)
patch.ToFile()
check = sdk.StreamToc(); assert check.FromFile(str(path))
assert sum(map(len, check.TocDict.values())) == 7
for (type_id, file_id), data in before.items():
    assert tuple(bytes(d) for d in check.GetEntry(file_id, type_id).GetData()) == data
assert bytes(check.GetEntry(BANK_ID, sdk.WwiseBankID).TocData) == (ROOT / 'audio_inspection/machete_replaced.wwise_bank').read_bytes()
base = sdk.Global_TocManager.LoadArchive(sdk.Global_gamepath + sdk.BaseArchiveHexID)
text = verify_bank(bytes(base.GetEntry(TEXT_ID, sdk.StringID).TocData), bytes(check.GetEntry(TEXT_ID, sdk.StringID).TocData))
report = json.loads((ROOT / 'validation_report.json').read_text(encoding='utf-8'))
report['text'] = text
report['audio'] = {'status': 'PENDING', 'bank_id': str(BANK_ID), 'existing_payloads_preserved': 6}
(ROOT / 'validation_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
build = json.loads((ROOT / 'build_report.json').read_text(encoding='utf-8'))
build['patch_entries'] = [{'id': str(e.FileID), 'type': sdk.GetTypeNameFromID(e.TypeID),
                          'toc': len(e.TocData), 'gpu': len(e.GpuData), 'stream': len(e.StreamData)}
                         for entries in check.TocDict.values() for e in entries.values()]
(ROOT / 'build_report.json').write_text(json.dumps(build, ensure_ascii=False, indent=2), encoding='utf-8')
print('AUDIO_MERGE_PASS: 7 entries; all 6 previous payloads unchanged', flush=True)
