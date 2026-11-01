#!/usr/bin/env python3
"""Compare full-column integration with actual displaced triangle clipping."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import math
import random
from gl_shader_test import ShaderTest
from test_water_volume import WAVES, VOLUME, cells, WATER, AIR, SOLID, close


def run():
    # This control bypasses only the interior shortcut. Both branches traverse
    # the same production geometry; the reference clips/merges every wet prism.
    reference=VOLUME.replace('bool fullColumn = here.r > 0.99',
                             'bool fullColumn = testUseMesh < 0.5 && here.r > 0.99')
    assert reference!=VOLUME
    fragment='#define ENABLE_WATER_VOLUME\nuniform float testUseMesh;\n'+WAVES+reference+'''
uniform vec3 testPosition, testDirection;
uniform float testDistance, testStop, testResultKind;
void main() {
 float firstExit; vec2 firstWater;
 vec3 direction=normalize(testDirection);
 vec4 path=traceWaterVolume(testPosition,direction,testDistance,firstExit,testStop>0.5,firstWater);
 if(testResultKind<0.5) gl_FragColor=path;
 else gl_FragColor=vec4(firstExit,firstWater,
   firstWater.x<0.0 ? 0.0 : (waterAt(testPosition+direction*((firstWater.x+firstWater.y)*0.5)) ? 1.0 : 0.0));
}
'''
    rng=random.Random(439)
    count=0
    with ShaderTest(fragment,size=1) as gpu:
        gpu.sampler('texture6',6)
        gpu.uniform('waterVolumeOrigin',0,0,0);gpu.uniform('waterAbsoluteOrigin',0,0,0)
        gpu.uniform('waterVolumeParams',1,16,200,0.7)
        layouts=[lambda x,y,z: WATER,
                 lambda x,y,z: WATER if 3<=y<=12 else AIR,
                 lambda x,y,z: WATER if y in (3,4,7,8,9,10) else AIR,
                 lambda x,y,z: SOLID if x==9 else (WATER if 3<=y<=12 else AIR),
                 lambda x,y,z: (0,0,0,0) if z==9 else WATER,
                 lambda x,y,z: (1,1,0,0.2 if y%2 else 0.8),
                 lambda x,y,z: (240/255,0.5,0,0.4,0.1,0.4,0.6,0.9) if y==8 else (WATER if 3<=y<8 else AIR)]
        directions=[(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1),
                    (1,1,1),(-1,-1,-1),(1,0,1),(1,1,0),(0,1,1)]
        rays=[((40,40,40),d,80) for d in directions]
        rays += [((45,45,45),d,20*math.sqrt(sum(v*v for v in d))) for d in directions]
        rays += [((rng.uniform(10,135),rng.uniform(10,135),rng.uniform(10,135)),
                  tuple(rng.uniform(-1,1) for _ in range(3)),rng.uniform(0.05,150)) for _ in range(22)]
        for index,layout in enumerate(layouts):
            gpu.texture(6,cells(16,layout),width=32,height=256)
            for height in (0,0.5,1,4):
                gpu.uniform('waterWaves',height,20,0.3)
                for position,direction,length in rays:
                    gpu.uniform('testPosition',*position);gpu.uniform('testDirection',*direction)
                    gpu.uniform('testDistance',length)
                    for stop in (0,1):
                        gpu.uniform('testStop',stop);gpu.uniform('testResultKind',0)
                        gpu.uniform('testUseMesh',1);expected=gpu.draw()
                        gpu.uniform('testUseMesh',0);actual=gpu.draw()
                        control=(index,height,position,direction,length,stop)
                        close(actual,expected,('full-column path versus displaced triangle union',control),0.001)
                        gpu.uniform('testResultKind',1)
                        info=gpu.draw()
                        gpu.uniform('testUseMesh',1);mesh_info=gpu.draw()
                        close(info[:2],mesh_info[:2],('first exit and first wet start',control,actual),0.001)
                        if actual[0]>0.001:
                            assert 0<=info[1]<info[2]<=actual[2]+0.001, (info,actual)
                            assert info[3]==1, ('representative first interval must be actual water',info)
                        count+=1
        # A continuous column must not manufacture an exit at a shared plane.
        # This oblique ray previously acquired one at 115.71 world units when
        # clipping every prism, despite the full 119.156-unit path being wet.
        gpu.texture(6,cells(16,lambda x,y,z:WATER),width=32,height=256)
        gpu.uniform('waterWaves',0,20,0.3)
        gpu.uniform('testPosition',39.2439845,121.717812,25.9917581)
        gpu.uniform('testDirection',0.41683935,-0.99871139,-0.03762007)
        gpu.uniform('testDistance',119.156106);gpu.uniform('testStop',1)
        gpu.uniform('testUseMesh',1);gpu.uniform('testResultKind',0)
        close(gpu.draw(),(119.156106,119.156106*0.98,119.156106,0),'continuous clipped column has no premature exit',0.001)
        gpu.uniform('testResultKind',1)
        close(gpu.draw()[:1],(-1,),'continuous clipped column exit marker')
        # A real, narrow air gap must still stop both upward and downward rays.
        gap=(224/255,0.9998,0,0.4,0.9998,0.9998,0.9998,0.9998)
        gpu.texture(6,cells(16,lambda x,y,z:gap if y==12 else WATER),width=32,height=256)
        for mode in (0,1):
            gpu.uniform('testUseMesh',mode)
            for y,direction,distance in ((40,1,84.998),(130,-1,5)):
                gpu.uniform('testPosition',40,y,40);gpu.uniform('testDirection',0,direction,0)
                gpu.uniform('testDistance',120);gpu.uniform('testResultKind',0)
                close(gpu.draw(),(distance,distance*0.98,distance,0),'real 0.002-world-unit gap retains first-exit truncation',0.001)
                gpu.uniform('testResultKind',1)
                close(gpu.draw()[:1],(distance,),'real gap exit marker',0.001)
        # The maximum geometry grid has coarser absolute plane precision.
        gpu.texture(6,cells(64,lambda x,y,z:WATER),width=128,height=4096)
        gpu.uniform('waterVolumeParams',1,64,640,0.7)
        gpu.uniform('testUseMesh',1)
        for height in (1,4):
            gpu.uniform('waterWaves',height,20,0.3)
            for _ in range(32):
                position=tuple(rng.uniform(200,500) for _ in range(3))
                direction=tuple(rng.uniform(-1,1) for _ in range(3))
                length=rng.uniform(2,80)
                gpu.uniform('testPosition',*position);gpu.uniform('testDirection',*direction)
                gpu.uniform('testDistance',length);gpu.uniform('testResultKind',0)
                close(gpu.draw(),(length,length*0.98,length,0),
                      ('continuous 64-node clipped column',position,direction,height),0.001)
                gpu.uniform('testResultKind',1)
                close(gpu.draw()[:1],(-1,),'64-node continuous column exit marker')
        print(f'PASS: {count} full-column/mesh path, turbidity, sky, first-exit and wet-interval controls;',gpu.renderer)


if __name__=='__main__': run()
