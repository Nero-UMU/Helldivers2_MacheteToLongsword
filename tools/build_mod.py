"""Build a CQC-42 cosmetic replacement with the installed HD2SDK CE."""
import bpy, sys, os, importlib, json, copy, subprocess, zipfile
from pathlib import Path
from mathutils import Vector, Matrix
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parent))
from text_patch import add_to_patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(Path(os.environ['APPDATA'])/'Blender Foundation/Blender/5.2/scripts/addons'))
sdk=importlib.import_module('HD2SDK-CommunityEdition')
for name in ('CheckBlenderVersion','CheckAddonUpToDate','UpdateArchiveHashes','UpdateFriendlyNames'):
    setattr(sdk,name,lambda:None)
sdk.register()
settings=bpy.context.scene.Hd2ToolPanelSettings
settings.ImportStatic=True
settings.ImportLods=True
settings.AutoLods=False
settings.ImportMaterials=False
settings.ImportArmature=False
settings.SaveTexturesWithMaterial=False
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
manager=sdk.Global_TocManager
arc=manager.LoadArchive(sdk.Global_gamepath+'f5014993c8402d87')
unit_id=8731737688384722662
original=arc.GetEntry(unit_id,sdk.UnitID)
original.Load(False,True,True)
original_objects=[o for o in bpy.data.objects if o.get('Z_ObjectID')==str(unit_id)]
print('ORIGINAL_LOADED',len(original_objects),flush=True)
base=manager.LoadArchive(sdk.Global_gamepath+sdk.BaseArchiveHexID)
manager.CreatePatchFromActive('Fatalis swo034 for CQC-42')
patch=manager.ActivePatch
patch.UpdatePath(str(ROOT/'output/9ba626afa44a3aa3.patch_0'))

def asset_id(name):
    return sdk.murmur64_hash(('mods/machete_to_fatalis_swo034/'+name).encode())

def constant_png(name,color):
    im=bpy.data.images.new(name,width=16,height=16,alpha=True)
    im.colorspace_settings.name='Non-Color'
    im.pixels.foreach_set(np.tile(np.array(color,dtype=np.float32),16*16))
    im.filepath_raw=str(ROOT/'source'/name);im.file_format='PNG';im.save()
    return im.filepath_raw

normal_path=constant_png('fatalis_flat_normal.png',(128/255,128/255,1,1))
pbr_path=constant_png('fatalis_pbr.png',(0.18,0.62,1,1))
texture_specs=[('pbr',pbr_path,'BC7_UNORM'),('color',str(ROOT/'source/swo034_BML.PNG'),'BC7_UNORM_SRGB'),('normal',normal_path,'BC7_UNORM')]
texture_ids=[]
for name,path,fmt in texture_specs:
    args=[sdk.Global_texconvpath,'-y','-dx10','-f',fmt,'-o',str(ROOT/'source'),'--',path]
    subprocess.run(args,check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    dds=Path(path).with_suffix('.dds').read_bytes()
    tex=sdk.StingrayTexture();tex.FromDDS(dds)
    toc=sdk.MemoryStream(IOMode='write');gpu=sdk.MemoryStream(IOMode='write');stream=sdk.MemoryStream(IOMode='write')
    tex.Serialize(toc,gpu,stream)
    e=sdk.TocEntry();e.FileID=asset_id(name);e.TypeID=sdk.TexID;e.IsCreated=True
    e.SetData(toc.Data,gpu.Data,stream.Data);e.LoadedData=tex;e.IsLoaded=True
    manager.AddNewEntryToPatch(e);texture_ids.append(e.FileID)
    print('TEXTURE',name,e.FileID,tex.Width,tex.Height,tex.Format,flush=True)

mat_id=asset_id('material')
mat_data=sdk.StingrayMaterial()
mat_data.Serialize(sdk.MemoryStream((Path(sdk.Global_materialpath)/'basic+.material').read_bytes()))
assert len(mat_data.TexIDs)==3
mat_data.TexIDs=texture_ids
toc=sdk.MemoryStream(IOMode='write');mat_data.Serialize(toc)
mat_entry=sdk.TocEntry();mat_entry.FileID=mat_id;mat_entry.TypeID=sdk.MaterialID
mat_entry.IsCreated=True;mat_entry.MaterialTemplate='basic+';mat_entry.SetData(toc.Data,b'',b'')
manager.AddNewEntryToPatch(mat_entry)
mat_entry.Load(False,True)
material=bpy.data.materials[str(mat_id)]

bpy.ops.wm.obj_import(filepath=str(ROOT/'source/swo034.obj'),forward_axis='NEGATIVE_Z',up_axis='Y')
source=bpy.context.selected_objects[0]
# OBJ local coordinates: X is blade width, Y is length, Z is thickness.
# Put the blade in the original YZ plane, pointing +Z. Rotate 180 degrees
# around the grip axis so the hooked tip faces the same side as the CQC-42 tip.
# The upper grip is centered at source Y=-8, aligned to the CQC-42 hand origin.
scale=1.5/(198.538330078125-(-89.77570343017578))
rotation=Matrix(((0,0,-1,0),(-1,0,0,0),(0,1,0,0),(0,0,0,1)))
transform=Matrix.Translation(Vector((0,0,8*scale))) @ Matrix.Diagonal((scale,scale,scale,1)) @ rotation
source.data.transform(transform);source.matrix_world=Matrix.Identity(4)
source.data.update()
source.name='Fatalis_Source_Aligned'
source.data.materials.clear();source.data.materials.append(material)
source.data.uv_layers[0].name='UVMap'

ratios={8:1.0,7:0.75,6:0.40,5:0.16,4:0.06,3:0.22,2:0.10,1:0.04,0:0.015}
replacements=[];manifest=[]
for old in original_objects:
    index=old['MeshInfoIndex']
    o=old.copy();o.data=source.data.copy();bpy.context.collection.objects.link(o)
    o.name='Fatalis_'+old.name;o.matrix_world=old.matrix_world.copy()
    if index<4:
        o.data.materials.clear()
        for m in old.data.materials:o.data.materials.append(m)
    bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o
    if ratios[index]<1:
        mod=o.modifiers.new('Distance simplification','DECIMATE');mod.ratio=ratios[index]
        bpy.ops.object.modifier_apply(modifier=mod.name)
    for p in o.data.polygons:p.use_smooth=True
    manifest.append({'name':o.name,'mesh_index':index,'vertices':len(o.data.vertices),'triangles':sum(len(p.vertices)-2 for p in o.data.polygons),'ratio':ratios[index]})
    replacements.append(o)
    bpy.data.objects.remove(old,do_unlink=True)
bpy.data.objects.remove(source,do_unlink=True)

bpy.ops.object.select_all(action='DESELECT')
for o in replacements:o.select_set(True)
bpy.context.view_layer.objects.active=next(o for o in replacements if o['MeshInfoIndex']==8)
print('EXTRACTING_MESHES',flush=True)
mesh_data=sdk.GetObjectsMeshData(manager,sdk.Global_BoneNames)[str(unit_id)]
for item in manifest:
    exported=mesh_data[item['mesh_index']]
    item['export_vertices']=len(exported.VertexPositions)
    item['export_triangles']=len(exported.Indices)
    item['referenced_vertices']=max(i for f in exported.Indices for i in f)+1
entry=manager.AddEntryToPatch(unit_id,sdk.UnitID)
for index,mesh in mesh_data.items():entry.LoadedData.RawMeshes[index]=mesh
assert len(mesh_data)==9
entry.Save(BlenderOpts=settings.get_settings_dict())
print('UNIT_SAVED',flush=True)
for tid in (sdk.BoneID,sdk.StateMachineID):
    for extra in list(patch.TocDict.get(tid,{}).values()):
        assert extra.GetData()==arc.GetEntry(extra.FileID,tid).GetData()
        patch.RemoveEntry(extra.FileID,tid,ReloadUI=False)
    if tid in patch.TocDict and not patch.TocDict[tid]:del patch.TocDict[tid]
add_to_patch(sdk,base,patch)
from audio_patch import add_audio_bank
add_audio_bank(sdk,patch)
patch.ToFile()

# Only the display LOD is visible in the editing project and the preview.
for o in replacements:
    o.hide_render=o['MeshInfoIndex']!=8
    o.hide_set(o['MeshInfoIndex']!=8)
bpy.ops.object.select_all(action='DESELECT')
hero=next(o for o in replacements if o['MeshInfoIndex']==8)
hero.select_set(True);bpy.context.view_layer.objects.active=hero
scene=bpy.context.scene
scene.render.engine='CYCLES';scene.cycles.samples=48
scene.render.resolution_x=1200;scene.render.resolution_y=1100;scene.render.resolution_percentage=100
scene.world.color=(0.18,0.18,0.18)
points=[hero.matrix_world@Vector(v) for v in hero.bound_box]
lo=Vector([min(p[i] for p in points) for i in range(3)]);hi=Vector([max(p[i] for p in points) for i in range(3)])
center=(lo+hi)/2
cd=bpy.data.cameras.new('Preview Camera');cam=bpy.data.objects.new('Preview Camera',cd);scene.collection.objects.link(cam)
cam.location=center+Vector((3.7,-0.5,0.15));cam.rotation_euler=(center-cam.location).to_track_quat('-Z','Y').to_euler()
cd.type='ORTHO';cd.ortho_scale=1.78;scene.camera=cam
for name,pos,energy,size in [('Key',(3,-2,3),450,3),('Fill',(2,3,1),180,2),('Rim',(-2,0,2.5),300,2)]:
    ld=bpy.data.lights.new(name,'AREA');light=bpy.data.objects.new(name,ld);scene.collection.objects.link(light)
    light.location=center+Vector(pos);light.rotation_euler=(center-light.location).to_track_quat('-Z','Y').to_euler();ld.energy=energy;ld.size=size
scene.render.filepath=str(ROOT/'Fatalis_CQC42_preview.png')
bpy.ops.render.render(write_still=True)
for area in bpy.context.screen.areas:
    if area.type=='VIEW_3D':
        area.spaces.active.region_3d.view_location=center
        area.spaces.active.region_3d.view_distance=2.5
        area.spaces.active.region_3d.view_rotation=cam.rotation_euler.to_quaternion()
        area.spaces.active.shading.type='MATERIAL'
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'Fatalis_CQC42.blend'))
report={'game_build':'25480438','blender':bpy.app.version_string,'sdk_version':sdk.bl_info['version'],'source_archive':'f5014993c8402d87','target_unit':str(unit_id),'patch_base':sdk.BaseArchiveHexID,'length_m':1.5,'source_grip_y':-8,'scale':scale,'material_id':str(mat_id),'texture_ids':[str(i) for i in texture_ids],'lods':manifest,'patch_entries':[{'id':str(e.FileID),'type':sdk.GetTypeNameFromID(e.TypeID),'toc':len(e.TocData),'gpu':len(e.GpuData),'stream':len(e.StreamData)} for v in patch.TocDict.values() for e in v.values()]}
(ROOT/'build_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print('BUILD_DONE',json.dumps(report),flush=True)
