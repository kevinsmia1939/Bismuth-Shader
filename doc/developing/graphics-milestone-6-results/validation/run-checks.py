import hashlib,json,os,subprocess,sys
from pathlib import Path
ROOT=Path('/home/kevin/Dropbox/Desktop/software/luanti')
OUT=Path('/tmp/bismuth-m6')
env=os.environ|{'SDL_VIDEODRIVER':'wayland','__GL_SHADER_DISK_CACHE':'1','__GL_SHADER_DISK_CACHE_PATH':str(ROOT/'cache/bismuth-gl')}
def guard():
 paths=[]
 for root in ('src','irr/include','irr/src','client/shaders','util'):
  paths += [p for p in (ROOT/root).rglob('*') if p.suffix in ('.cpp','.h','.c','.glsl','.py','.lua','.sh') and p.is_file()]
 paths += [ROOT/'misc'/f'graphics-{name}.conf' for name in ('basic','balanced','quality')]
 return hashlib.sha256(b''.join(str(p.relative_to(ROOT)).encode()+b'\0'+p.read_bytes() for p in sorted(paths))).hexdigest()
initial=guard();records=[]
def run(name,command,extra=None):
 print('Checking '+name,flush=True)
 path=OUT/('verified-'+name+'.log')
 with path.open('w') as log:
  result=subprocess.run(command,cwd=ROOT,env=env|(extra or {}),stdout=log,stderr=subprocess.STDOUT)
 assert result.returncode==0,f'{name} failed: {path}'
 assert guard()==initial,'Implementation changed during validation'
 records.append({'name':name,'log':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
 (OUT/'verified-checks.json').write_text(json.dumps({'source_guard':initial,'checks':records},indent=2)+'\n')
 print('PASS '+name,flush=True)
run('cpp',['bin/luanti','--run-unittests'])
run('blend',['bin/luanti','--run-tests','[surface-blend]'])
suites=['surface_materials','image_stability','light_falloff','floor_shading','dynamic_lighting','point_materials','native_emission','dark_caves','cloud_shadows','surface_directional','camera_effects','water_lighting','voxel_fog','fog_denoise','volumetric_clouds']
for driver,extra in [('nvidia330',{}),('nvidia120',{'LUANTI_TEST_GLSL':'120'}),('mesa330',{'SDL_VIDEODRIVER':'offscreen','__EGL_VENDOR_LIBRARY_FILENAMES':'/usr/share/glvnd/egl_vendor.d/50_mesa.json','LIBGL_ALWAYS_SOFTWARE':'true'})]:
 for suite in suites:run(driver+'-'+suite,[sys.executable,'util/test_'+suite+'.py'],extra)
run('native',[sys.executable,'util/test_graphics_milestones.py','/tmp/bismuth-m5-minetest/prepared-world','--output',str(OUT/'native-complete'),'--texture-pack','textures/bismuth-minetest-game','--daylight-cave','--surface-materials','--resize'])
run('legacy-surfaces',['bash','util/test_material_shading.sh'],{'LUANTI_TEST_TIMEOUT':'1200','LUANTI_TEST_DRIVER':'opengl','LUANTI_TEST_AA':'fsaa','LUANTI_TEST_STEREO':'sidebyside','LUANTI_TEST_LEAVES':'simple','LUANTI_TEST_SURFACE_MATERIALS':'true','LUANTI_TEST_DYNAMIC_DIRECT':'false','LUANTI_TEST_DIRECTIONAL':'true'})
run('exposure-no-bloom',['bash','util/test_material_shading.sh'],{'LUANTI_TEST_TIMEOUT':'1200','LUANTI_TEST_BLOOM':'false','LUANTI_TEST_EXPOSURE':'true','LUANTI_TEST_SURFACE_MATERIALS':'true','LUANTI_TEST_DYNAMIC_DIRECT':'true','LUANTI_TEST_DIRECTIONAL':'true'})
run('forward-surfaces',['bash','util/test_material_shading.sh'],{'LUANTI_TEST_TIMEOUT':'1200','LUANTI_TEST_POST_PROCESSING':'false','LUANTI_TEST_SHADOWS':'false','LUANTI_TEST_LEAVES':'opaque','LUANTI_TEST_WAVING':'false','LUANTI_TEST_SURFACE_MATERIALS':'true','LUANTI_TEST_DYNAMIC_DIRECT':'true'})
print('PASS all final checks: '+str(OUT/'verified-checks.json'),flush=True)
