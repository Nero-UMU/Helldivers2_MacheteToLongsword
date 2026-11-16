"""Add audio and verify that existing model and texture payloads survive unchanged."""
import importlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(Path(os.environ['APPDATA']) / 'Blender Foundation/Blender/5.2/scripts/addons'))
from audio_patch import BANK_ID, add_audio_bank

sdk = importlib.import_module('HD2SDK-CommunityEdition')
for name in ('CheckBlenderVersion', 'CheckAddonUpToDate', 'UpdateArchiveHashes', 'UpdateFriendlyNames'):
    setattr(sdk, name, lambda: None)
sdk.register()
path = ROOT / 'output/9ba626afa44a3aa3.patch_0'
patch = sdk.StreamToc(); assert patch.FromFile(str(path))
before = {(e.TypeID, e.FileID): tuple(bytes(d) for d in e.GetData())
          for entries in patch.TocDict.values() for e in entries.values() if e.TypeID != sdk.WwiseBankID}
assert not patch.TocDict.get(sdk.StringID)
assert len(before) == 5
add_audio_bank(sdk, patch)
patch.ToFile()
check = sdk.StreamToc(); assert check.FromFile(str(path))
assert sum(map(len, check.TocDict.values())) == 6
for (type_id, file_id), data in before.items():
    assert tuple(bytes(d) for d in check.GetEntry(file_id, type_id).GetData()) == data
assert bytes(check.GetEntry(BANK_ID, sdk.WwiseBankID).TocData) == (ROOT / 'audio_inspection/machete_replaced.wwise_bank').read_bytes()
report = json.loads((ROOT / 'validation_report.json').read_text(encoding='utf-8'))
report['audio'] = {'status': 'PENDING', 'bank_id': str(BANK_ID), 'existing_payloads_preserved': 5}
(ROOT / 'validation_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
build = json.loads((ROOT / 'build_report.json').read_text(encoding='utf-8'))
build['patch_entries'] = [{'id': str(e.FileID), 'type': sdk.GetTypeNameFromID(e.TypeID),
                          'toc': len(e.TocData), 'gpu': len(e.GpuData), 'stream': len(e.StreamData)}
                         for entries in check.TocDict.values() for e in entries.values()]
(ROOT / 'build_report.json').write_text(json.dumps(build, ensure_ascii=False, indent=2), encoding='utf-8')
print('AUDIO_MERGE_PASS: 6 entries; all 5 model/texture payloads unchanged', flush=True)
