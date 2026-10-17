import bpy,sys,os,importlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from text_patch import add_to_patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(Path(os.environ['APPDATA'])/'Blender Foundation/Blender/5.2/scripts/addons'))
sdk=importlib.import_module('HD2SDK-CommunityEdition')
for n in ('CheckBlenderVersion','CheckAddonUpToDate','UpdateArchiveHashes','UpdateFriendlyNames'):setattr(sdk,n,lambda:None)
sdk.register()
base=sdk.Global_TocManager.LoadArchive(sdk.Global_gamepath+sdk.BaseArchiveHexID)
patch=sdk.StreamToc();assert patch.FromFile(str(ROOT/'output/9ba626afa44a3aa3.patch_0'))
add_to_patch(sdk,base,patch)
patch.ToFile()
print('TEXT_ADDED',flush=True)
