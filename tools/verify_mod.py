import bpy,sys,os,importlib,json,math
from pathlib import Path
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
from text_patch import BANK_ID, verify_bank
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(Path(os.environ['APPDATA'])/'Blender Foundation/Blender/5.2/scripts/addons'))
sdk=importlib.import_module('HD2SDK-CommunityEdition')
for n in ('CheckBlenderVersion','CheckAddonUpToDate','UpdateArchiveHashes','UpdateFriendlyNames'):setattr(sdk,n,lambda:None)
sdk.register()
s=bpy.context.scene.Hd2ToolPanelSettings;s.ImportStatic=True;s.ImportLods=True;s.ImportArmature=False
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
manager=sdk.Global_TocManager
arc=manager.LoadArchive(sdk.Global_gamepath+'f5014993c8402d87')
patch=sdk.StreamToc();assert patch.FromFile(str(ROOT/'output/9ba626afa44a3aa3.patch_0'))
# The SDK copies these entries while extracting mesh data. They are unchanged.
for tid in (sdk.BoneID,sdk.StateMachineID):
    for e in list(patch.TocDict.get(tid,{}).values()):
        assert e.GetData()==arc.GetEntry(e.FileID,tid).GetData(), 'Unexpected animation modification'
        patch.RemoveEntry(e.FileID,tid,ReloadUI=False)
    if tid in patch.TocDict and not patch.TocDict[tid]:del patch.TocDict[tid]
patch.ToFile()
manager.Patches.append(patch);manager.SetActivePatch(patch)
report=json.loads((ROOT/'build_report.json').read_text(encoding='utf-8'))
mat_id=int(report['material_id']);me=patch.GetEntry(mat_id,sdk.MaterialID);me.MaterialTemplate='basic+';me.Load(False,True)
mat=me.LoadedData
assert [str(x) for x in mat.TexIDs]==report['texture_ids']
textures=[]
for tid in mat.TexIDs:
    e=patch.GetEntry(tid,sdk.TexID);assert e is not None;e.Load(False,False)
    tex=e.LoadedData;assert tex.Width>0 and tex.Height>0 and tex.NumMipMaps>1
    textures.append({'id':str(tid),'width':tex.Width,'height':tex.Height,'mips':tex.NumMipMaps,'format':tex.Format})
e=patch.GetEntry(int(report['target_unit']),sdk.UnitID);e.Load(False,True)
meshes=e.LoadedData.RawMeshes
assert len(meshes)==9
lod_results=[]
for mesh in meshes:
    exp=next(x for x in report['lods'] if x['mesh_index']==mesh.MeshInfoIndex)
    print('CHECK_MESH',mesh.MeshInfoIndex,'read',len(mesh.VertexPositions),len(mesh.Indices),'expected',exp['referenced_vertices'],exp['export_triangles'],flush=True)
    # SDK readers omit trailing unreferenced vertices after decimation.
    assert len(mesh.VertexPositions)==exp['referenced_vertices']
    assert len(mesh.Indices)==exp['export_triangles']
    assert all(0<=i<len(mesh.VertexPositions) for face in mesh.Indices for i in face)
    assert all(math.isfinite(v) for p in mesh.VertexPositions for v in p)
    assert len(mesh.VertexUVs)>=3
    assert all(len(u)==len(mesh.VertexPositions) for u in mesh.VertexUVs)
    mids=[int(m.MatID) for m in mesh.Materials]
    assert mids==([mat_id] if mesh.MeshInfoIndex>=4 else [6453911083847036449])
    lod_results.append({'index':mesh.MeshInfoIndex,'vertices':len(mesh.VertexPositions),'triangles':len(mesh.Indices),'material_ids':[str(m) for m in mids]})
hero=next(o for o in bpy.data.objects if o.get('MeshInfoIndex')==8)
positions=[v.co for v in hero.data.vertices]
length=max(v.z for v in positions)-min(v.z for v in positions)
assert abs(length-1.5)<0.002
original_unit=arc.GetEntry(e.FileID,sdk.UnitID);original_unit.Load(False,False)
def tip_side(points):
    lo=min(p[2] for p in points);hi=max(p[2] for p in points)
    tip=[p for p in points if p[2]>hi-(hi-lo)*0.015]
    return sum(p[1] for p in tip)/len(tip)
original_hero=next(m for m in original_unit.LoadedData.RawMeshes if m.MeshInfoIndex==8)
original_tip_side=tip_side(original_hero.VertexPositions)
orientation=[]
for mesh in meshes:
    side=tip_side(mesh.VertexPositions)
    assert side*original_tip_side>0, f'Mesh {mesh.MeshInfoIndex} tip faces the wrong side of the grip axis'
    assert max(p[2] for p in mesh.VertexPositions)>abs(min(p[2] for p in mesh.VertexPositions)), 'Tip and handle inverted'
    orientation.append({'mesh_index':mesh.MeshInfoIndex,'tip_side_y':side})
assert e.LoadedData.BonesRef==original_unit.LoadedData.BonesRef
assert e.LoadedData.StateMachineRef==original_unit.LoadedData.StateMachineRef
assert len(patch.TocDict[sdk.UnitID])==1
assert len(patch.TocDict[sdk.MaterialID])==1
assert len(patch.TocDict[sdk.TexID])==3
assert len(patch.TocDict[sdk.StringID])==1
assert len(patch.TocDict[sdk.WwiseBankID])==1
assert sum(len(v) for v in patch.TocDict.values())==7
base=manager.LoadArchive(sdk.Global_gamepath+sdk.BaseArchiveHexID)
text_result=verify_bank(bytes(base.GetEntry(BANK_ID,sdk.StringID).TocData),bytes(patch.GetEntry(BANK_ID,sdk.StringID).TocData))
for o in bpy.data.objects:o.hide_render=o!=hero
# Render the exported file using the same preview camera, lighting and scene settings.
with bpy.data.libraries.load(str(ROOT/'Fatalis_CQC42.blend'),link=False) as (available,wanted):
    wanted.objects=[n for n in available.objects if n in ('Preview Camera','Key','Fill','Rim')]
for o in wanted.objects:
    bpy.context.scene.collection.objects.link(o);o.hide_render=False
scene=bpy.context.scene;scene.camera=bpy.data.objects['Preview Camera']
scene.world.color=(0.18,0.18,0.18);scene.render.engine='CYCLES';scene.cycles.samples=48
scene.render.resolution_x=1200;scene.render.resolution_y=1100;scene.render.resolution_percentage=100
scene.render.filepath=str(ROOT/'Fatalis_CQC42_export_verified.png');bpy.ops.render.render(write_still=True)
result={'status':'PASS','checks':['SDK reopened the exported archive and GPU file','All 9 display/shadow meshes have expected geometry and valid indices','Material references resolve to 3 custom textures with mipmaps','Exactly 1 unit, 1 material and 3 textures in patch','Original bone and animation references retained; no physics, bones or animation entries patched','Exported model length within 2 mm of 1.5 m','Rendered from exported patch, independently of source blend'],'length_m':length,'textures':textures,'meshes':lod_results,'in_game_tested':False}
result['checks'].append('All 9 exported meshes have the same tip-side direction as the original CQC-42')
result['orientation']={'original_tip_side_y':original_tip_side,'meshes':orientation}
result['checks'].append('Simplified Chinese name and description round-trip exactly; all other strings unchanged')
result['text']=text_result
from verify_audio import verify as verify_audio
result['audio']=verify_audio()
(ROOT/'validation_report.json').write_text(json.dumps(result,indent=2))
report['patch_entries']=[{'id':str(e.FileID),'type':sdk.GetTypeNameFromID(e.TypeID),'toc':len(e.TocData),'gpu':len(e.GpuData),'stream':len(e.StreamData)} for v in patch.TocDict.values() for e in v.values()]
(ROOT/'build_report.json').write_text(json.dumps(report,indent=2))
print('VALIDATION_PASS',json.dumps(result),flush=True)
