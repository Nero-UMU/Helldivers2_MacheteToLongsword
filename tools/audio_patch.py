"""Merge the generated Wwise bank into the SDK model/text patch."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BANK_ID = 9850852767093112933


def add_audio_bank(sdk, patch):
    data = (ROOT / 'audio_inspection/machete_replaced.wwise_bank').read_bytes()
    entry = sdk.TocEntry()
    entry.FileID = BANK_ID
    entry.TypeID = sdk.WwiseBankID
    entry.SetData(data, b'', b'')
    patch.AddEntry(entry, override=True, ReloadUI=False)
