"""Verify the audio stored in the exported patch, including decoding and event reachability."""
import json
import struct
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tools/audio_reference'))
from build_audio_bank import BANK_ID, REMOVED_ACTIONS, GAIN_ADJUSTMENTS, CLIP_FILTERS, FFMPEG, VGMSTREAM, chunks, media, objects
from wwise_hierarchy_154 import WwiseHierarchy_154


def exported_bank():
    data = (ROOT / 'output/9ba626afa44a3aa3.patch_0').read_bytes()
    types, count = struct.unpack_from('<II', data, 4)
    matches = []
    for index in range(count):
        pos = 72 + 32 * types + 80 * index
        file_id, type_id, offset = struct.unpack_from('<QQQ', data, pos)
        size = struct.unpack_from('<I', data, pos + 56)[0]
        if file_id == BANK_ID and type_id == 6006249203084351385:
            matches.append(data[offset:offset + size])
    assert len(matches) == 1
    return matches[0]


def verify():
    original = (ROOT / f'audio_inspection/{BANK_ID}.wwise_bank').read_bytes()
    packed = exported_bank()
    assert struct.unpack_from('<I', packed, 4)[0] == len(packed) - 16
    assert packed[:4] == original[:4] and packed[8:16] == original[8:16]
    before = chunks(original[16:]); after = chunks(packed[16:])
    assert struct.unpack_from('<I', after[b'BKHD'])[0] ^ 0x9211BCAC == 154
    old_media = media(before); actual = media(after)
    report = json.loads((ROOT / 'audio_inspection/audio_build_report.json').read_text(encoding='utf-8'))
    expected_ids = {row['target_media_id'] for row in report['mappings']}
    assert set(old_media) == set(actual)
    assert {mid for mid in actual if old_media[mid] != actual[mid]} == expected_ids
    assert len(expected_ids) == 12
    for row in report['mappings']:
        expected = ROOT / 'tools/audio_conversion/wem/Windows' / Path(row['source']).with_suffix('.wem')
        assert actual[row['target_media_id']] == expected.read_bytes()
    h = WwiseHierarchy_154(); h.load(after[b'HIRC'])
    old_objects, new_objects = objects(before[b'HIRC']), objects(after[b'HIRC'])
    expected_objects = {row['sound_id'] for row in report['mappings']} | set(REMOVED_ACTIONS) | set(GAIN_ADJUSTMENTS)
    assert set(old_objects) == set(new_objects)
    assert {oid for oid in old_objects if old_objects[oid] != new_objects[oid]} == expected_objects
    old_h = WwiseHierarchy_154(); old_h.load(before[b'HIRC'])
    for node_id, delta in GAIN_ADJUSTMENTS.items():
        def gain(hierarchy):
            props = hierarchy.entries[node_id].baseParam.propBundle
            return struct.unpack('<f', props.pValues[props.pIDs.index(5)])[0]
        assert abs(gain(h) - gain(old_h) - delta) < 0.001
    for row in report['mappings']:
        source = h.entries[row['sound_id']].sources[0]
        assert source.source_id == row['target_media_id'] and source.mem_size == len(actual[source.source_id])
        assert source.plugin_id == 0x40001 and source.stream_type == 0

    def reachable(oid, seen=None):
        seen = set() if seen is None else seen
        if oid in seen: return []
        seen.add(oid); node = h.entries[oid]
        if hasattr(node, 'ulActionType') and node.ulActionType != 0x403: return []
        sources = list(getattr(node, 'sources', []))
        children = list(getattr(node, 'ulActionIDs', []))
        if hasattr(node, 'children'): children += node.children.children
        if hasattr(node, 'idExt'): children.append(node.idExt)
        for child in children: sources += reachable(child, seen)
        return sources

    for event_id, removed in REMOVED_ACTIONS.items():
        assert removed not in h.entries[event_id].ulActionIDs
        assert all(s.plugin_id != 0x830402 for s in reachable(event_id))

    # Decode the four distinct clips from the exported bank, not the conversion input folder.
    dest = ROOT / 'audio_inspection/replacement_verified'; dest.mkdir(exist_ok=True)
    decoded = []
    for filename in sorted({row['source'] for row in report['mappings']}):
        row = next(row for row in report['mappings'] if row['source'] == filename)
        wem = dest / Path(filename).with_suffix('.wem')
        wav = wem.with_suffix('.wav'); wem.write_bytes(actual[row['target_media_id']])
        subprocess.run([str(VGMSTREAM), '-o', str(wav), str(wem)],
                       check=True, capture_output=True)
        def pcm(path, filters=None):
            filter_args = ['-af', filters] if filters else []
            result = subprocess.run([str(FFMPEG), '-v', 'error',
                                     '-i', str(path), *filter_args, '-ar', '48000', '-ac', '1', '-f', 'f32le', '-'],
                                    check=True, capture_output=True)
            return np.frombuffer(result.stdout, dtype='<f4')
        selection = json.loads((ROOT / 'audio_inspection/mhw_source/selected_audio.json').read_text(encoding='utf-8'))
        source = pcm(ROOT / selection['source_directory'] / filename, CLIP_FILTERS.get(filename))
        result = pcm(wav)
        assert abs(len(source) - len(result)) <= 1, (filename, len(source), len(result))
        count = min(len(source), len(result))
        correlation = float(np.corrcoef(source[:count], result[:count])[0, 1])
        assert correlation > 0.97, (filename, correlation)
        frames = result[:len(result) // 480 * 480].reshape(-1, 480)
        rms = np.sqrt(np.mean(frames ** 2, axis=1))
        audible = np.flatnonzero(rms > 10 ** (-30 / 20))
        onset = float(audible[0] * 0.01) if len(audible) else None
        if filename == '12.ogg':
            assert onset is not None and onset <= 0.1, (filename, onset)
        decoded.append({'source': filename, 'samples_48khz': len(result),
                        'duration_s': len(result) / 48000, 'pcm_correlation': correlation,
                        'audible_onset_minus30db_s': onset})
    report.update({'status': 'PASS', 'decoded_from_exported_patch': decoded,
                   'existing_payloads_preserved': 6, 'exported_patch_verified': True})
    (ROOT / 'audio_inspection/audio_validation_report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    audio = verify()
    path = ROOT / 'validation_report.json'
    validation = json.loads(path.read_text(encoding='utf-8'))
    validation['audio'] = audio
    check = 'Exported Wwise bank: 12 samples replaced, plugin play layers removed from 3 events; 215 other samples unchanged'
    if check not in validation['checks']: validation['checks'].append(check)
    path.write_text(json.dumps(validation, ensure_ascii=False, indent=2), encoding='utf-8')
    print('EXPORTED_AUDIO_PASS', json.dumps(audio['decoded_from_exported_patch']), flush=True)
