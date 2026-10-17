"""Convert the selected clips and replace only CQC-42 draw/holster/swing audio."""
import json
import os
import shutil
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'audio_inspection'
WORK = ROOT / 'tools/audio_conversion'
PROJECT = WORK / 'MacheteAudio/MacheteAudio.wproj'
FFMPEG = Path(os.environ.get('FFMPEG') or shutil.which('ffmpeg') or 'ffmpeg')
VGMSTREAM = Path(os.environ.get('VGMSTREAM') or shutil.which('vgmstream-cli') or str(ROOT / 'tools/vgmstream/vgmstream-cli.exe'))
CONSOLE = Path(os.environ.get('WWISE_CONSOLE') or str(Path(os.environ.get('WWISEROOT', '')) / 'Authoring/x64/Release/bin/WwiseConsole.exe'))
BANK_ID = 9850852767093112933
REMOVED_ACTIONS = {4141703124: 314099501, 3820905703: 557484802, 3065953046: 391543493}
CLIP_FILTERS = {'12.ogg': 'atrim=start=0.75,asetpts=PTS-STARTPTS,afade=t=in:d=0.005'}
GAIN_ADJUSTMENTS = {741917751: 16.0}  # Holster container: -5 dB -> +11 dB.


def chunks(data):
    result = {}; offset = 0
    while offset < len(data):
        tag, size = struct.unpack_from('<4sI', data, offset)
        assert offset + 8 + size <= len(data)
        result[tag] = data[offset + 8:offset + 8 + size]
        offset += 8 + size
    assert offset == len(data)
    return result


def media(bank):
    return {mid: bank[b'DATA'][offset:offset + size]
            for mid, offset, size in struct.iter_unpack('<III', bank[b'DIDX'])}


def objects(hirc):
    result = {}; offset = 4
    for _ in range(struct.unpack_from('<I', hirc)[0]):
        size, oid = struct.unpack_from('<II', hirc, offset + 1)
        result[oid] = hirc[offset:offset + 5 + size]
        offset += 5 + size
    assert offset == len(hirc)
    return result


def main():
    selection = json.loads((DEST / 'mhw_source/selected_audio.json').read_text(encoding='utf-8'))
    inputs = WORK / 'wav'; inputs.mkdir(parents=True, exist_ok=True)
    output = WORK / 'wem'; output.mkdir(exist_ok=True)
    if not PROJECT.exists():
        subprocess.run([str(CONSOLE), 'create-new-project', str(PROJECT), '--platform', 'Windows'], check=True)
    settings_path = PROJECT.parent / 'Conversion Settings/Factory Conversion Settings.wwu'
    settings = ET.parse(settings_path)
    conversion = next(c for c in settings.iter('Conversion') if c.get('Name') == 'Vorbis Quality High')
    plugin = next(conversion.iter('ConversionPlugin'))
    properties = plugin.find('PropertyList')
    if properties is None:
        properties = ET.SubElement(plugin, 'PropertyList')
    quality = properties.find("Property[@Name='QualityFactor']")
    if quality is None:
        quality = ET.SubElement(properties, 'Property', Name='QualityFactor', Type='Real32')
    quality.set('Value', '10')
    settings.write(settings_path, encoding='utf-8', xml_declaration=True)
    external = ET.Element('ExternalSourcesList', SchemaVersion='1', Root=str(inputs))
    for filename in sorted({name for item in selection['replacements'] for name in item['files']}):
        source = ROOT / selection['source_directory'] / filename
        wav = inputs / Path(filename).with_suffix('.wav')
        filters = ['-af', CLIP_FILTERS[filename]] if filename in CLIP_FILTERS else []
        subprocess.run([str(FFMPEG), '-v', 'error', '-y', '-i', str(source), *filters, '-ar', '48000',
                        '-ac', '1', '-c:a', 'pcm_s16le', str(wav)], check=True)
        ET.SubElement(external, 'Source', Path=wav.name, Conversion='Vorbis Quality High',
                      Destination=wav.with_suffix('.wem').name)
    source_list = WORK / 'selected.wsources'
    ET.ElementTree(external).write(source_list, encoding='utf-8', xml_declaration=True)
    subprocess.run([str(CONSOLE), 'convert-external-source', str(PROJECT), '--platform', 'Windows',
                    '--source-file', str(source_list), '--output', str(output)], check=True)

    # Use the documented 154 parser only for objects being changed; retain all others byte for byte.
    sys.path.insert(0, str(ROOT / 'tools/audio_reference'))
    from wwise_hierarchy_154 import WwiseHierarchy_154
    original = (DEST / f'{BANK_ID}.wwise_bank').read_bytes()
    bank = chunks(original[16:]); old_media = media(bank); new_media = dict(old_media)
    h = WwiseHierarchy_154(); h.load(bank[b'HIRC'])
    raw_objects = objects(bank[b'HIRC']); new_objects = dict(raw_objects)
    mappings = []
    changed_sounds = set()
    for item in selection['replacements']:
        for index, mid in enumerate(item['hd2_sample_ids']):
            filename = item['files'][index % len(item['files'])]
            replacement = (output / 'Windows' / Path(filename).with_suffix('.wem')).read_bytes()
            assert replacement[:4] == b'RIFF'
            new_media[mid] = replacement
            parents = [sound for sound in h.sounds if any(s.source_id == mid for s in sound.sources)]
            assert len(parents) == 1
            sound = parents[0]
            assert bytes(sound.get_data()) == raw_objects[sound.get_id()]
            for source in sound.sources:
                if source.source_id == mid:
                    assert source.plugin_id == 0x00040001 and source.stream_type == 0
                    source.mem_size = len(replacement)
            new_objects[sound.get_id()] = bytes(sound.get_data())
            changed_sounds.add(sound.get_id())
            mappings.append({'purpose': item['purpose'], 'source': filename, 'target_media_id': mid,
                             'sound_id': sound.get_id(), 'bytes': len(replacement)})
    for event_id, action_id in REMOVED_ACTIONS.items():
        event = h.entries[event_id]
        assert bytes(event.get_data()) == raw_objects[event_id]
        assert action_id in event.ulActionIDs
        event.ulActionIDs.remove(action_id)
        event.ulActionListSize = len(event.ulActionIDs)
        event.update_size()
        new_objects[event_id] = bytes(event.get_data())
    gain_changes = []
    for node_id, gain_db in GAIN_ADJUSTMENTS.items():
        node = h.entries[node_id]
        assert bytes(node.get_data()) == raw_objects[node_id]
        props = node.baseParam.propBundle
        index = props.pIDs.index(5)  # Wwise 154 MakeUpGain.
        previous = struct.unpack('<f', props.pValues[index])[0]
        props.set_prop_value_float_by_pid(5, previous + gain_db)
        new_objects[node_id] = bytes(node.get_data())
        gain_changes.append({'node_id': node_id, 'before_db': previous, 'after_db': previous + gain_db})
    bank[b'HIRC'] = struct.pack('<I', len(new_objects)) + b''.join(new_objects.values())
    payload = bytearray(); index_data = bytearray()
    for mid, data in new_media.items():
        payload.extend(b'\0' * (-len(payload) % 16))
        index_data.extend(struct.pack('<III', mid, len(payload), len(data)))
        payload.extend(data)
    bank[b'DIDX'] = bytes(index_data); bank[b'DATA'] = bytes(payload)
    encoded = b''.join(tag + struct.pack('<I', len(data)) + data for tag, data in bank.items())
    prefix = bytearray(original[:16]); struct.pack_into('<I', prefix, 4, len(encoded))
    result = bytes(prefix) + encoded
    (DEST / 'machete_replaced.wwise_bank').write_bytes(result)
    (DEST / 'machete_replaced.bnk').write_bytes(encoded)

    reread = chunks(encoded); actual_media = media(reread)
    replaced_ids = {m['target_media_id'] for m in mappings}
    assert set(actual_media) == set(old_media)
    assert {mid for mid in old_media if actual_media[mid] != old_media[mid]} == replaced_ids
    assert len(replaced_ids) == 12
    check = WwiseHierarchy_154(); check.load(reread[b'HIRC'])
    actual_objects = objects(reread[b'HIRC'])
    assert {oid for oid in raw_objects if raw_objects[oid] != actual_objects[oid]} == changed_sounds | set(REMOVED_ACTIONS) | set(GAIN_ADJUSTMENTS)
    for tag in bank:
        if tag not in (b'DATA', b'DIDX', b'HIRC'):
            assert reread[tag] == chunks(original[16:])[tag]
    report = {'status': 'PASS', 'bank_id': str(BANK_ID), 'bank_version': 154,
              'encoder': str(CONSOLE), 'mappings': mappings,
              'removed_plugin_play_actions': REMOVED_ACTIONS,
              'unchanged_media_count': len(old_media) - len(replaced_ids),
              'unchanged_hirc_objects': len(raw_objects) - len(changed_sounds) - len(REMOVED_ACTIONS) - len(GAIN_ADJUSTMENTS),
              'clip_filters': CLIP_FILTERS, 'gain_changes': gain_changes,
              'in_game_tested': False}
    (DEST / 'audio_build_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('AUDIO_BANK_PASS', len(mappings), 'replacements;', len(result), 'bytes', flush=True)


if __name__ == '__main__':
    main()
