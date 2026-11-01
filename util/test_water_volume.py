#!/usr/bin/env python3
"""Actual loaded-water traversal/transport/focusing GLSL; numeric pixels only."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import math
import subprocess
import tempfile
from pathlib import Path
from gl_shader_test import ShaderTest

ROOT = Path(__file__).resolve().parents[1]
WAVES = (ROOT / "client/shaders/common/water_waves.glsl").read_text()
VOLUME = (ROOT / "client/shaders/common/water_volume.glsl").read_text()


def close(actual, expected, label, tolerance=3e-4):
    assert max(abs(a-b) for a, b in zip(actual, expected)) < tolerance, (label, actual, expected)


def cells(n, function):
    atlas=[]
    for z in range(n):
        for y in range(n):
            row=[function(x,y,z) for x in range(n)]
            atlas.extend(c for cell in row for c in cell[:4])
            atlas.extend(c for cell in row for c in (cell[4:] if len(cell)==8 else (cell[1],)*4))
    return atlas


AIR = (64/255, 0, 1, 0)
SOLID = (128/255, 0, 0, 0)
WATER = (1, 1, 0, 0.4)


def test_traversal():
    fragment = "#define ENABLE_WATER_VOLUME\n" + WAVES + VOLUME + """
uniform vec3 testPosition;
uniform vec3 testDirection;
uniform vec3 testSurface;
uniform float testDistance;
uniform float testMode;
void main() {
 float exit;
 if (testMode < 0.5) gl_FragColor = traceWaterVolume(testPosition, normalize(testDirection), testDistance, exit);
 else if (testMode < 1.5) { vec4 path=traceWaterVolume(testPosition, normalize(testDirection), testDistance, exit); gl_FragColor=vec4(exit,path.xyz); }
 else if (testMode < 2.5) gl_FragColor=vec4(waterAt(testPosition) ? 1.0 : 0.0);
 else if (testMode < 3.5) { vec3 solved; gl_FragColor=vec4(waterFocusing(testPosition,testSurface,solved)); }
 else if (testMode < 4.5) gl_FragColor=vec4(applyWaterCaustics(vec3(0.5),testPosition,vec3(0,1,0),0.0,vec3(1.0)),1.0);
 else gl_FragColor=vec4(waterWaveHeight(testPosition,waterWaves));
}
"""
    n = 8
    with ShaderTest(fragment) as gpu:
        gpu.sampler("texture6", 6)
        gpu.uniform("waterVolumeOrigin", 0, 0, 0)
        gpu.uniform("waterAbsoluteOrigin", 0, 0, 0)
        gpu.uniform("waterVolumeParams", 1, n, 200, 0.7)
        gpu.uniform("waterLight", 0, 1, 0, 1)
        gpu.uniform("waterLightColor", 1, 1, 1)
        gpu.uniform("waterWaves", 0, 20, 0)
        gpu.uniform("waterMediumParams", 0, 1, 0, 0)
        gpu.uniform("testPosition", 20, 20, 20)
        gpu.uniform("testSurface", 20, 45, 20)
        gpu.uniform("testDirection", 0, 1, 0)
        gpu.uniform("testDistance", 60)
        gpu.uniform("testMode", 0)
        atlas = cells(n, lambda x,y,z: WATER if 1 <= y <= 4 else AIR)
        gpu.texture(6, atlas, width=2*n, height=n*n)
        weighted = 25 * (0.3 + 1.7 * 0.4)
        close(gpu.draw(), (25, weighted, 55, 1), "finite pool exit / air is not water")
        gpu.uniform("testMode", 1)
        close(gpu.draw()[:1], (25,), "first rear exit")
        gpu.uniform("testMode", 0)
        gpu.uniform("testDistance", 10)
        close(gpu.draw()[:3], (10, 10*0.98, 10), "endpoint inside volume")
        gpu.uniform("testDistance", 60)
        gpu.texture(6, cells(n, lambda x,y,z: SOLID if y == 6 else (WATER if 1 <= y <= 4 else AIR)), width=2*n, height=n*n)
        close(gpu.draw(), (25, weighted, 35, 0), "opaque roof blocks light traversal")
        gpu.texture(6, cells(n, lambda x,y,z: (0,0,0,0) if y == 6 else (WATER if 1 <= y <= 4 else AIR)), width=2*n, height=n*n)
        close(gpu.draw(), (25, weighted, 35, 0), "unknown terrain is not unoccluded sky")
        gpu.texture(6, cells(n, lambda x,y,z: WATER if y in (2,4) else AIR), width=2*n, height=n*n)
        close(gpu.draw(), (15, 15*0.98, 55, 1), "separated liquid layers count only water")
        partial = (224/255, 0.25, 0, 0.4)
        gpu.texture(6, cells(n, lambda x,y,z: partial if y == 2 else AIR), width=2*n, height=n*n)
        gpu.uniform("testPosition", 20, 15, 20)
        close(gpu.draw(), (2.5, 2.45, 60, 1), "partial flowing-liquid slab")
        gpu.uniform("testMode", 2)
        gpu.uniform("testPosition", 20, 16, 20)
        close(gpu.draw(), (1,)*4, "inside shallow flow")
        gpu.uniform("testPosition", 20, 20, 20)
        close(gpu.draw(), (0,)*4, "above partial liquid")
        gpu.uniform("testMode", 0)
        gpu.texture(6, cells(n, lambda x,y,z: WATER), width=2*n, height=n*n)
        gpu.uniform("testPosition", 20, 20, 20)
        gpu.uniform("testDirection", 1, 1, 1)
        gpu.uniform("testDistance", 20)
        close(gpu.draw()[:3], (20, 19.6, 20), "tied-axis corner traversal")
        gpu.uniform("testDirection",0,-1,0)
        close(gpu.draw()[:3],(20,19.6,20),"negative-axis traversal")
        gpu.uniform("testDistance",0)
        close(gpu.draw(),(0,0,0,0),"zero-length segment")
        gpu.uniform("testDistance",20)
        gpu.uniform("testDirection",1,1,1)
        gpu.uniform("waterVolumeOrigin", -2000, 0, 0)
        gpu.uniform("testPosition", -1980, 20, 20)
        close(gpu.draw()[:3], (20, 19.6, 20), "camera-origin shift preserves path")
        gpu.uniform("waterVolumeOrigin", 0, 0, 0)
        gpu.uniform("testPosition", 20, 20, 20)
        gpu.uniform("testMode", 3)
        close(gpu.draw(), (1,)*4, "flat interface has unit flux focusing")
        gpu.uniform("waterLight", 0.6, 0.8, 0, 1)
        close(gpu.draw(), (1,)*4, "oblique flat refraction has unit focusing")
        gpu.uniform("waterWaves",1,20,0.3)
        focused=gpu.draw()
        gpu.uniform("waterVolumeOrigin",-2000,0,0)
        gpu.uniform("testPosition",-1980,20,20)
        gpu.uniform("testSurface",-1980,45,20)
        close(gpu.draw(),focused,"world-wave focusing survives camera-origin shift",0.003)
        gpu.uniform("waterVolumeOrigin",0,0,0)
        gpu.uniform("testPosition",20,20,20)
        gpu.uniform("testSurface",20,45,20)
        gpu.uniform("testMode", 4)
        gpu.texture(6, (float("nan"),)*4, width=2*n, height=n*n)
        gpu.uniform("waterVolumeParams", 0, n, 200, 0.7)
        close(gpu.draw(), (0.5,0.5,0.5,1), "unbound volume bypass before sampling")
        gpu.uniform("waterVolumeParams", 1, n, 200, 0)
        close(gpu.draw(), (0.5,0.5,0.5,1), "zero caustics bypass")
        gpu.uniform("testMode", 5)
        gpu.uniform("testPosition", 0, 0, 0)
        gpu.uniform("waterWaves", 1, 20, 0)
        close(gpu.draw(), (-5,)*4, "shared mesh wave displacement at zero lattice point")
        gpu.uniform("waterWaves",1,20,0.5)
        animated=gpu.draw()[0]
        assert -5 < animated <= 0,("shared mesh wave animation",animated)
        gpu.uniform("testPosition",0.75,20.25,0.5)
        original_wave=gpu.draw()
        gpu.uniform("testPosition",0.75,20.25+289*64*16,0.5)
        close(gpu.draw(),original_wave,"far-world wave lattice periodicity",0.0005)
        print(f"PASS: loaded-water traversal, boundaries, turbidity, flow, origin and flat focusing; {gpu.renderer}")


def test_displaced_boundaries():
    # Controlled fields give closed-form intersections while using the actual
    # source mesh planes, diagonal splits, candidate cells and union traversal.
    split = WAVES.index("// Plane of")
    prefix = WAVES[:split].replace("float waterWaveHeight(", "float nativeWaterWaveHeight(")
    fragment = "#define ENABLE_WATER_VOLUME\n" + prefix + """
uniform float testField;
uniform float testHeight;
float waterWaveHeight(vec3 p, vec3 waves) {
 if(testField<0.5) return nativeWaterWaveHeight(p,waves);
 if(testField<1.5) return testHeight;
 // Saddle: the two source triangles have distinct slopes at their diagonal.
 return testHeight+0.01*(p.x-20.0)*(p.z-20.0);
}
""" + WAVES[split:] + VOLUME + """
uniform vec3 testPosition;
uniform vec3 testDirection;
uniform float testDistance;
uniform float testMode;
void main() {
 float exit;
 if(testMode<0.5) gl_FragColor=traceWaterVolume(testPosition,normalize(testDirection),testDistance,exit);
 else if(testMode<1.5) { vec4 p=traceWaterVolume(testPosition,normalize(testDirection),testDistance,exit,true); gl_FragColor=vec4(exit,p.xyz); }
 else if(testMode<2.5) gl_FragColor=vec4(waterAt(testPosition)?1:0);
 else gl_FragColor=vec4(waterWaveHeight(testPosition,waterWaves));
}
"""
    with ShaderTest(fragment) as gpu:
        n=8
        gpu.sampler("texture6",6)
        gpu.uniform("waterVolumeOrigin",0,0,0);gpu.uniform("waterAbsoluteOrigin",0,0,0)
        gpu.uniform("waterVolumeParams",1,n,200,0)
        gpu.uniform("waterWaves",1,20,0)
        gpu.uniform("testPosition",20,20,20);gpu.uniform("testDirection",0,1,0)
        gpu.uniform("testDistance",60);gpu.uniform("testMode",0)
        gpu.uniform("testField",1);gpu.uniform("testHeight",-4)
        pool=lambda x,y,z: WATER if 2<=y<=4 else AIR
        gpu.texture(6,cells(n,pool),width=2*n,height=n*n)
        close(gpu.draw(),(21,21*0.98,55,1),"source waves lower the upper interface")
        gpu.uniform("testMode",1)
        close(gpu.draw(),(21,21,21*0.98,21),"first displaced exit truncates transport")
        gpu.uniform("testMode",2)
        for y,wet in ((10.9,0),(11.1,1),(40.9,1),(41.1,0),(43,0)):
            gpu.uniform("testPosition",20,y,20)
            close(gpu.draw(),(wet,)*4,"source occupancy follows top and bottom triangles")
        gpu.uniform("testMode",0);gpu.uniform("testPosition",20,20,20)
        gpu.uniform("testDirection",0,-1,0)
        close(gpu.draw()[:2],(9,9*0.98),"displaced bottom extends into the air cell below")
        gpu.uniform("testMode",2);gpu.uniform("testHeight",-3.5)
        gpu.uniform("testField",2)
        # In the center of this saddle quad, triangle interpolation is -3.75;
        # resampling the continuous field at the center would incorrectly give -3.5.
        for y,wet in ((41.2,1),(41.3,0)):
            gpu.uniform("testPosition",20,y,20)
            close(gpu.draw(),(wet,)*4,"mesh triangle interpolation rather than a fragment noise sample")
        gpu.uniform("testMode",0);gpu.uniform("testPosition",16,41.4,18)
        gpu.uniform("testDirection",1,0,1);gpu.uniform("testDistance",5*math.sqrt(2))
        # Along x=16+s,z=18+s the first plane is H=41.55-s*0.1.
        # It crosses the mesh diagonal at s=3, then the second plane slopes up.
        # With y=41.4 the first 1.5 and final 0.5 units are wet.
        close(gpu.draw()[:2],(2*math.sqrt(2),2*math.sqrt(2)*0.98),"ray crosses a source triangle diagonal")
        # Large, legal waves reach cells two nodes below their source without
        # absorbing a dry gap, and stopAtExit must not accumulate a later pool.
        gpu.uniform("waterWaves",4,20,0);gpu.uniform("testField",1);gpu.uniform("testHeight",-18)
        gpu.texture(6,cells(n,lambda x,y,z: WATER if y==4 else AIR),width=2*n,height=n*n)
        gpu.uniform("testPosition",20,20,20);gpu.uniform("testDirection",0,1,0);gpu.uniform("testDistance",30)
        close(gpu.draw()[:2],(7,7*0.98),"two-node displacement coverage")
        gpu.uniform("testMode",2)
        gpu.uniform("testPosition",20,18,20)
        close(gpu.draw(),(1,)*4,"camera below the original source cell")
        gpu.uniform("testMode",0);gpu.uniform("waterWaves",1,20,0);gpu.uniform("testHeight",-4)
        gpu.texture(6,cells(n,lambda x,y,z: WATER if y in (2,4) else AIR),width=2*n,height=n*n)
        gpu.uniform("testPosition",20,12,20);gpu.uniform("testDirection",0,1,0);gpu.uniform("testDistance",40)
        close(gpu.draw()[:2],(19,19*0.98),"separated displaced pools count only wet intervals")
        gpu.uniform("testMode",1)
        close(gpu.draw(),(9,9,9*0.98,9),"first-exit transport excludes a later displaced pool")
        # Independent CPU test uses these same exact integer-lattice anchors.
        gpu.uniform("testMode",3);gpu.uniform("testField",0)
        for p,expected in (((0,0,0),-5),((0,0,40),-30/41),((60,0,0),-100/41)):
            gpu.uniform("testPosition",*p)
            close(gpu.draw(),(expected,)*4,"CPU/GPU shared wave lattice anchors",0.00001)
        print(f"PASS: displaced source triangles, first exits, diagonal crossing, lower cells, amplitude bounds and CPU/GPU anchors; {gpu.renderer}")


def test_flow_boundaries():
    fragment="""#define ENABLE_WATER_VOLUME
uniform float testWaveHeight;
float waterWaveHeight(vec3 p, vec3 waves) { return waves.x>0.0 ? testWaveHeight : 0.0; }
"""+WAVES[WAVES.index("// Plane of"):]+VOLUME+"""
uniform vec3 testPosition;
uniform vec3 testDirection;
uniform float testDistance;
uniform float testMode;
void main() {
 float exit;
 if(testMode<0.5) gl_FragColor=traceWaterVolume(testPosition,normalize(testDirection),testDistance,exit);
 else if(testMode<1.5) { vec4 path=traceWaterVolume(testPosition,normalize(testDirection),testDistance,exit,true); gl_FragColor=vec4(exit,path.xyz); }
 else gl_FragColor=vec4(waterAt(testPosition)?1:0);
}
"""
    with ShaderTest(fragment) as gpu:
        n=8
        gpu.sampler("texture6",6)
        gpu.uniform("waterVolumeOrigin",0,0,0)
        gpu.uniform("waterVolumeParams",1,n,200,0)
        gpu.uniform("waterWaves",0,20,0);gpu.uniform("testWaveHeight",-4)
        gpu.uniform("testPosition",17.5,15,17.5);gpu.uniform("testDirection",0,1,0)
        gpu.uniform("testDistance",10);gpu.uniform("testMode",0)
        corners=(0.2,0.8,0.6,0.4)
        def upload(waving=False, solid_below=False):
            flow=(240/255 if waving else 224/255,0.5,0,0.4)+corners
            gpu.texture(6,cells(n,lambda x,y,z: flow if (x,y,z)==(2,2,2) else
                               (SOLID if solid_below and y==1 else AIR)),width=2*n,height=n*n)
        upload()
        close(gpu.draw(),(4.5,4.5*0.98,10,0),"vertical path clips the lower flowing triangle")
        gpu.uniform("testMode",2)
        for x,y,z,wet in ((17.5,19.25,17.5,1),(17.5,19.75,17.5,0),
                          (22.5,20.25,22.5,1),(22.5,20.75,22.5,0)):
            gpu.uniform("testPosition",x,y,z)
            close(gpu.draw(),(wet,)*4,"flow occupancy follows both mesh slopes rather than a flat slab")
        gpu.uniform("testMode",0);gpu.uniform("testPosition",16,20.5,16)
        gpu.uniform("testDirection",1,0,1);gpu.uniform("testDistance",8*math.sqrt(2))
        close(gpu.draw()[:2],(4*math.sqrt(2),4*math.sqrt(2)*0.98),"static flow ray crosses the diagonal")
        gpu.uniform("testMode",1)
        close(gpu.draw(),(6.5*math.sqrt(2),4*math.sqrt(2),4*math.sqrt(2)*0.98,6.5*math.sqrt(2)),
              "sloped first exit truncates at the upper triangle")
        gpu.uniform("waterWaves",1,20,0);gpu.uniform("testMode",2);gpu.uniform("testPosition",17.5,12,17.5)
        close(gpu.draw(),(0,)*4,"static flow is unaffected by other liquids' wave settings")
        upload(waving=True)
        close(gpu.draw(),(1,)*4,"waving flow enters the air node below")
        gpu.uniform("testMode",0);gpu.uniform("testPosition",17.5,15,17.5)
        gpu.uniform("testDirection",0,1,0);gpu.uniform("testDistance",10)
        close(gpu.draw()[:2],(0.5,0.49),"wave displacement is applied to each flowing top corner")
        gpu.uniform("testMode",2);gpu.uniform("testPosition",17.5,12,17.5)
        upload(waving=True,solid_below=True)
        close(gpu.draw(),(0,)*4,"solid geometry still occludes displaced flow")
        upload(waving=True)
        gpu.uniform("waterWaves",4,20,0);gpu.uniform("testWaveHeight",-18)
        gpu.uniform("testPosition",17.5,-1,17.5)
        close(gpu.draw(),(1,)*4,"maximum wave amplitude reaches two cells below flowing water")
        print(f"PASS: sloped/static/waving flow triangles, diagonal crossings, first exits, lower cells and solid occlusion; {gpu.renderer}")


def test_shoreline_ordering():
    fragment="#define ENABLE_WATER_VOLUME\n"+WAVES+VOLUME+"""
uniform vec3 testPosition;
uniform float testThickness;
void main() {
 float bottom=waterWaveHeight(testPosition,waterWaves);
 float top=testThickness+waterWaveHeight(testPosition+vec3(0,testThickness,0),waterWaves);
 vec3 middle=testPosition+vec3(0,(top+bottom)*0.5,0);
 gl_FragColor=vec4(vec3((top-bottom)/testThickness),waterAt(middle)?1:0);
}
"""
    with ShaderTest(fragment) as gpu:
        n=4
        gpu.sampler("texture6",6);gpu.uniform("waterVolumeParams",1,n,200,0)
        for p in ((5,15,-35),(-105,35,-215),(309985,75,-309995)):
            origin=tuple(c-15 for c in p)
            gpu.uniform("waterVolumeOrigin",*origin);gpu.uniform("waterAbsoluteOrigin",*origin)
            gpu.uniform("testPosition",*p)
            for depth in (0.2,0.625,5,10):
                height=depth/10
                flow=(240/255,height,0,0.4)+(height,)*4
                gpu.texture(6,cells(n,lambda x,y,z:flow if (x,y,z)==(2,2,2) else AIR),width=2*n,height=n*n)
                gpu.uniform("testThickness",depth)
                for amplitude in (1,4):
                    for length in (0.1,7.123,20):
                        for phase in (0,0.9,4.5):
                            gpu.uniform("waterWaves",amplitude,length,phase)
                            result=gpu.draw()
                            assert 0.53<result[0]<1.47,("vertical ordering",p,depth,amplitude,length,phase,result)
                            close(result[3:],(1,),"actual thin-flow midpoint stays represented")
        print(f"PASS: actual shoreline thickness and occupancy through maximum wave amplitude, minimum wavelength and far origins; {gpu.renderer}")


def test_cpu_wave_agreement():
    # Compile only the production CPU wave header, independently of the engine
    # and GPU. Compare animated, negative and far-world samples on both triangles.
    program = r'''#include "client/render/water_waves.h"
#include <iostream>
#include <iomanip>
int main() {
 float x,y,z,h,l,t,u,v,a,b,c,d;
 std::cout<<std::setprecision(9);
 while(std::cin>>x>>y>>z>>h>>l>>t>>u>>v>>a>>b>>c>>d) {
  const v3f p(x,y,z), waves(h,l,t);
  std::cout<<WaterWaves::height(p,waves)<<" "<<WaterWaves::surface(p,u,v,waves,{a,b,c,d})<<"\n";
 }
}
'''
    samples=[(*p,*waves,*uv,*corners)
             for p in ((-5,5,-5),(-105,35,-215),(309985,75,-309995),(-309995,289035,309985))
             for waves in ((0,20,0),(1,20,0.3),(4,2.5,4.713),(1.33,7.123,0.713))
             for uv in ((0.2,0.3),(0.7,0.6),(0.25,0.75))
             for corners in ((0,0,0,0),(1,1,1,1),(0.0625,0.1875,0.8125,0.9375))]
    with tempfile.TemporaryDirectory(prefix="luanti-cpu-waves-") as work:
        binary=str(Path(work)/"waves")
        subprocess.run(["c++","-std=c++17","-O2","-I",str(ROOT/"src"),"-I",str(ROOT/"irr/include"),
                        "-x","c++","-","-o",binary],input=program,text=True,check=True,capture_output=True)
        output=subprocess.run([binary],input="\n".join(" ".join(map(str,s)) for s in samples),
                              text=True,check=True,capture_output=True).stdout.splitlines()
    fragment=WAVES+"""
uniform vec3 testPosition;
uniform vec3 testWaves;
uniform vec2 testUV;
uniform vec4 testCorners;
void main() {
 vec3 plane=waterLiquidPlane(vec3(0),testCorners,testUV.x+testUV.y>1.0,testPosition+vec3(5),testWaves);
 gl_FragColor=vec4(waterWaveHeight(testPosition,testWaves),
   dot(plane,vec3(testUV,1))*10.0+testPosition.y,0,1);
}
"""
    with ShaderTest(fragment) as gpu:
        for sample,row in zip(samples,output):
            gpu.uniform("testPosition",*sample[:3]);gpu.uniform("testWaves",*sample[3:6]);gpu.uniform("testUV",*sample[6:8]);gpu.uniform("testCorners",*sample[8:])
            expected=tuple(map(float,row.split()))
            tolerance=0.065 if abs(sample[1])>100000 else 0.002
            close(gpu.draw()[:2],expected,"production C++ and GLSL wave/mesh agreement",tolerance)
        print(f"PASS: {len(samples)} production CPU/GPU animated wave and triangle samples, negative/far origins and maximum amplitude; {gpu.renderer}")


def test_mesh_normals():
    source=(ROOT/"client/shaders/nodes_shader/opengl_fragment.glsl").read_text()
    begin=source.index("#if MATERIAL_WATER_REFLECTIONS &&")
    end=source.index("#endif",begin)+len("#endif")
    fragment="""#define MATERIAL_WATER_REFLECTIONS 1
uniform vec3 testNormal;
void main() {
 vec3 worldPosition=vec3(gl_FragCoord.x, -0.2*gl_FragCoord.x+0.1*gl_FragCoord.y, gl_FragCoord.y);
 vec3 fNormal=testNormal;
"""+source[begin:end]+"\n gl_FragColor=vec4(fNormal,1); }"
    with ShaderTest(fragment) as gpu:
        length=math.sqrt(1+0.2**2+0.1**2)
        expected=(0.2/length,1/length,-0.1/length)
        for sign in (1,-1):
            gpu.uniform("testNormal",0,sign,0)
            close(gpu.draw(),tuple(sign*v for v in expected)+(1,),"actual shared water normal follows the displaced triangle")
        print(f"PASS: actual node refraction/reflection/surface-buffer water normals; {gpu.renderer}")


def test_curved_interface():
    # Analytic quadratic wave isolates the refracted-photon Jacobian from noise.
    fragment = """#define ENABLE_WATER_VOLUME
uniform float testCurvature;
float waterWaveHeight(vec3 p, vec3 waves) {
 vec2 q=p.xz-vec2(75.0); return waves.x*testCurvature*dot(q,q);
}
vec3 waterWavePlane(vec3 cell, float restY, bool upper, vec3 origin, vec3 waves) {
 // Isolate the smooth photon model from mesh occupancy in this analytic test.
 return vec3(0,0,restY);
}
""" + WAVES[WAVES.index("// Plane of"):WAVES.index("// Fixed X/Z")] + VOLUME + """
uniform float testMode;
uniform float testNight;
uniform vec3 testShadow;
void main() {
 vec3 receiver=vec3(75,55,75), surface=vec3(75,95,75), solved;
 if(testMode<0.5) gl_FragColor=vec4(waterFocusing(receiver,surface,solved));
 else gl_FragColor=vec4(applyWaterCaustics(vec3(0.5),receiver,vec3(0,1,0),testNight,testShadow),1);
}
"""
    with ShaderTest(fragment) as gpu:
        n = 16
        gpu.sampler("texture6", 6)
        gpu.uniform("waterVolumeOrigin", 0, 0, 0)
        gpu.uniform("waterAbsoluteOrigin", 0, 0, 0)
        gpu.uniform("waterVolumeParams", 1, n, 200, 0.7)
        gpu.uniform("waterMediumParams", 0, 1, 0, 0)
        gpu.uniform("waterLight", 0, 1, 0, 1)
        gpu.uniform("waterLightColor", 1, 1, 1)
        gpu.uniform("waterWaves", 1, 20, 0)
        gpu.uniform("testMode", 0)
        gpu.uniform("testNight", 0)
        gpu.uniform("testShadow", 1, 1, 1)
        # Thin-angle limit: j=1+(1-eta)*2*curvature*depth. Compare finite Snell result.
        eta = 1/1.333
        for curvature in (-0.01, 0.01):
            gpu.uniform("testCurvature", curvature)
            expected = 1/(1+(1-eta)*2*curvature*40)**2
            close(gpu.draw(), (expected,)*4, "converging/diverging photon flux", 0.001)
        gpu.uniform("testCurvature", -0.05)
        close(gpu.draw(), (4,)*4, "bounded fold focusing", 0.001)
        gpu.uniform("testCurvature", -0.01)
        gpu.uniform("testMode", 1)
        pool = lambda x,y,z: WATER if 6 <= y <= 9 else AIR
        gpu.texture(6, cells(n,pool), width=2*n,height=n*n)
        result = gpu.draw()
        assert 0.5 < result[0] < result[1] < result[2], ("submerged flux and RGB light absorption",result)
        gpu.uniform("waterMediumParams",0,0,0,0)
        unabsorbed=gpu.draw()
        assert unabsorbed[0]>0.5
        close(unabsorbed[:3],(unabsorbed[0],)*3,"zero absorption keeps caustic flux spectrally neutral")
        gpu.uniform("waterMediumParams",0,1,0,0)
        for obstacle in (SOLID,(0,0,0,0)):
            gpu.texture(6,cells(n,lambda x,y,z: obstacle if y==12 else pool(x,y,z)),width=2*n,height=n*n)
            close(gpu.draw(),(0.5,0.5,0.5,1),"roof/unknown sunlight rejection")
        gpu.texture(6,cells(n,pool),width=2*n,height=n*n)
        gpu.uniform("testShadow",0,0,0)
        close(gpu.draw(),(0.5,0.5,0.5,1),"directional shadow occlusion")
        gpu.uniform("testShadow",1,1,1)
        gpu.uniform("testNight",1)
        close(gpu.draw(),(0.5,0.5,0.5,1),"artificial-light dominated receiver guard")
        gpu.uniform("testNight",0)
        gpu.texture(6,cells(n,lambda x,y,z:(224/255,1,0,0.4) if 6<=y<=9 else AIR),width=2*n,height=n*n)
        close(gpu.draw(),(0.5,0.5,0.5,1),"static liquids do not produce wave caustics")
        print(f"PASS: refracted photon focusing/divergence, bounds, occlusion and native-light guards; {gpu.renderer}")


def test_underwater_transport():
    source=(ROOT/"client/shaders/water_volume/opengl_fragment.glsl").read_text()
    source=source.replace("CENTROID_ VARYING_ mediump vec2 varTexCoord;", "#define varTexCoord (gl_FragCoord.xy/64.0)")
    with ShaderTest("#define ENABLE_WATER_VOLUME\n"+WAVES+VOLUME+source) as gpu:
        n=8
        gpu.sampler("texture0",0);gpu.sampler("texture1",1);gpu.sampler("texture6",6)
        gpu.uniform("waterVolumeOrigin",-30,-30,-30)
        gpu.uniform("waterVolumeParams",1,n,200,0.7)
        gpu.uniform("waterMediumParams",1,1,0,0)
        gpu.uniform("waterScatterColor",0.1,0.3,0.5)
        identity=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]
        projection=identity[:];projection[0]=projection[5]=projection[10]=40
        gpu.matrix("inverseProjection",projection);gpu.matrix("inverseView",identity)
        gpu.texture(0,(0.8,0.5,0.2,0.37));gpu.texture(1,(0.75,0,0,1))
        gpu.texture(6,cells(n,lambda x,y,z:WATER),width=2*n,height=n*n)
        distance=math.sqrt(20**2+2*0.625**2)
        def expected(path):
            t=[math.exp(-sigma*path*0.98/10) for sigma in (0.32,0.085,0.035)]
            return [((c**2.2)*v+(s**2.2)*(1-v))**(1/2.2)
                    for c,s,v in zip((0.8,0.5,0.2),(0.1,0.3,0.5),t)]+[0.37]
        close(gpu.draw(),expected(distance),"analytic underwater RGB transmission/scatter")
        gpu.texture(6,cells(n,lambda x,y,z: WATER if z in (3,4) else AIR),width=2*n,height=n*n)
        close(gpu.draw(),expected(15*distance/20),"underwater rear exit stops absorption in air")
        for inside,strength,ready in ((0,1,1),(1,0,1),(1,1,0)):
            gpu.uniform("waterMediumParams",inside,strength,0,0)
            gpu.uniform("waterVolumeParams",ready,n,200,0.7)
            gpu.texture(6,(float("nan"),)*4,width=2*n,height=n*n)
            close(gpu.draw(),(0.8,0.5,0.2,0.37),"dry/zero/absent underwater bypass")
        print(f"PASS: actual underwater pass, Beer-Lambert/RGB scatter, rear exits, alpha and bypasses; {gpu.renderer}")


def test_interface_reflections():
    source=(ROOT/"client/shaders/scene_lighting/opengl_fragment.glsl").read_text().replace(
        "CENTROID_ VARYING_ mediump vec2 varTexCoord;", "#define varTexCoord (gl_FragCoord.xy/64.0)")
    fragment="#define ENABLE_SCENE_SURFACE\n#define ENABLE_SCREEN_SPACE_REFLECTIONS\n"+source
    with ShaderTest(fragment) as gpu:
        for name,unit in (("texture0",0),("texture1",1),("texture2",2)):
            gpu.sampler(name,unit)
        a,b=1001/999,-2000/999
        gpu.matrix("sceneProjection",[1,0,0,0,0,1,0,0,0,0,a,1,0,0,b,0])
        gpu.matrix("inverseProjection",[1,0,0,0,0,1,0,0,0,0,0,1/b,0,0,1,-a/b])
        gpu.matrix("inverseView",[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1])
        gpu.uniform("sceneParams",0,0.8,0,0)
        gpu.uniform("waterCameraInside",1)
        env=(0.1,0.2,0.3)
        gpu.uniform("waterScatterColor",*env)
        gpu.uniform("fogColor",1,1,1,1)
        gpu.texture(0,(0,0,0,0.37))
        gpu.texture(1,((a+b/20)*0.5+0.5,0,0,1))
        scale=math.sqrt(1+2*(1/64)**2)
        incident=(1/64/scale,1/64/scale,1/scale)
        for s in (0,0.5,0.74,0.9):
            normal=(s,0,-math.sqrt(1-s*s))
            l1=abs(normal[0])+abs(normal[2])
            gpu.texture(2,(1,(2-abs(normal[0])/l1)*0.5,20,1))
            cosine=abs(sum(v*n for v,n in zip(incident,normal)))
            sin_squared=1.333**2*(1-cosine*cosine)
            if sin_squared>=1:
                weight=1
            else:
                ct=math.sqrt(1-sin_squared)
                rs=(1.333*cosine-ct)/(1.333*cosine+ct)
                rp=(cosine-1.333*ct)/(cosine+1.333*ct)
                physical=0.5*(rs*rs+rp*rp)
                blend=max(0,min(1,(physical-0.5)/0.5))
                blend=blend*blend*(3-2*blend)
                weight=physical*(0.8+0.2*blend)
            close(gpu.draw(),[c*weight**(1/2.2) for c in env]+[0.37],
                  "actual scene pass underwater Fresnel/TIR and liquid fallback",7e-5)
        gpu.uniform("sceneParams",0,0,0,0)
        close(gpu.draw(),(0,0,0,0.37),"zero reflection setting keeps source")
        print(f"PASS: actual water reflection pass, dielectric Fresnel, critical angle, TIR and liquid fallback; {gpu.renderer}")


if __name__ == "__main__":
    test_traversal()
    test_displaced_boundaries()
    test_flow_boundaries()
    test_shoreline_ordering()
    test_cpu_wave_agreement()
    test_mesh_normals()
    test_curved_interface()
    test_underwater_transport()
    test_interface_reflections()
