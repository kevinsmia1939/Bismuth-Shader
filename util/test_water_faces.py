#!/usr/bin/env python3
"""Actual caustic composition across connected flow faces; analytic numeric pixels only."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import math
from gl_shader_test import ShaderTest
from test_flow_caustics import FIELD, upload
from test_water_volume import WAVES, VOLUME, WATER, AIR, SOLID, close

MAIN='''
uniform vec3 testPosition,testSurface;
uniform vec2 testDisplacement;
uniform float testMode;
void main() {
 if(testMode<0.5) {
  gl_FragColor=vec4(applyWaterCaustics(vec3(0.5),testPosition,vec3(0,1,0),0.0,vec3(1)),1);return;
 }
 vec3 surface=testSurface;vec2 slope=vec2(0);
 bool valid=waterWalkSurface(surface,slope,testDisplacement);
 gl_FragColor=valid ? (testMode<1.5 ? vec4(surface,1) : vec4(slope,surface.y,1)) : vec4(0);
}
'''


def refracted(light,slope):
    normal=(-slope[0],1,-slope[1])
    magnitude=math.sqrt(sum(x*x for x in normal))
    normal=tuple(x/magnitude for x in normal)
    cosine=-sum(a*b for a,b in zip(light,normal))
    eta=1/1.333
    coefficient=eta*cosine+math.sqrt(1-eta*eta*(1-cosine*cosine))
    return tuple(-eta*l-coefficient*n for l,n in zip(light,normal))


def receiver_and_color(surface,slope,light):
    ray=refracted(light,slope)
    scene=(surface[0],surface[1]-0.1,surface[2])
    distance=(55-scene[1])/ray[1]
    receiver=(scene[0]+ray[0]*distance,55,scene[2]+ray[2]*distance)
    jacobian=1-(ray[0]*slope[0]+ray[2]*slope[1])/ray[1]
    incident=1-(slope[0]*light[0]+slope[1]*light[2])/light[1]
    focus=min(4,incident/abs(jacobian))
    delta=(scene[0]-receiver[0],scene[1]-55.1,scene[2]-receiver[2])
    cosine=delta[1]/math.sqrt(sum(x*x for x in delta))
    color=0.5*(1+(focus-1)*cosine)**(1/2.2)
    assert abs(color-0.5)>0.0005,('control must distinguish native lighting',color)
    return receiver,(color,color,color,1)


def connected_faces():
    with ShaderTest(FIELD+WAVES[WAVES.index('// Plane of'):]+VOLUME+MAIN) as gpu:
        gpu.sampler('texture6',6)
        gpu.uniform('waterVolumeOrigin',0,0,0);gpu.uniform('waterAbsoluteOrigin',0,0,0)
        gpu.uniform('waterVolumeParams',1,16,240,1);gpu.uniform('waterMediumParams',0,0,0,0)
        gpu.uniform('waterWaves',1,20,0);gpu.uniform('waterLightColor',1,1,1)
        gpu.uniform('testGradient',0,0);gpu.uniform('testCurvature',0)
        gpu.uniform('testOffset',-0.1);gpu.uniform('testVertical',0)
        gpu.uniform('testMode',0)
        triangle=(240/255,0.4,0,0.4,1,0.4,0.4,0.3)
        left=(240/255,0.7,0,0.4,1,0.4,1,0.4)
        right=(240/255,0.3,0,0.4,0.4,0.2,0.4,0.2)
        cases=(('triangle diagonal',{(7,9,7):triangle},(70.2,88.96,70.2),(-0.1,-0.1),(0.3,math.sqrt(0.87),0.2)),
               ('adjacent cells',{(7,9,7):left,(8,9,7):right},(75.2,88.96,70),(-0.2,0),(0.3,math.sqrt(0.91),0)))
        for label,faces,surface,slope,light in cases:
            pool=lambda x,y,z: faces.get((x,y,z),WATER if 1<=y<9 else AIR)
            upload(gpu,pool)
            receiver,expected=receiver_and_color(surface,slope,light)
            gpu.uniform('waterLight',*light,1);gpu.uniform('testPosition',*receiver)
            close(gpu.draw(),expected,'analytic Snell caustic across '+label,0.0002)
            gpu.uniform('waterVolumeOrigin',-2000,0,3000)
            gpu.uniform('testPosition',receiver[0]-2000,receiver[1],receiver[2]+3000)
            close(gpu.draw(),expected,'cross-face caustic after camera-origin rebase',0.0003)
            gpu.uniform('waterVolumeOrigin',0,0,0);gpu.uniform('testPosition',*receiver)
        # A similar endpoint is insufficient when the shared interface is absent.
        for invalid in (AIR,SOLID,(0,0,0,0),(224/255,0.3,0,0.4,0.4,0.2,0.4,0.2),
                        (240/255,0.4,0,0.4,0.5,0.3,0.5,0.3)):
            upload(gpu,lambda x,y,z: invalid if (x,y,z)==(8,9,7) else pool(x,y,z))
            close(gpu.draw(),(0.5,0.5,0.5,1),'absent, blocked, static or discontinuous neighboring face')
        print('PASS: actual caustic composition crosses a flow diagonal and a connected cell edge;',gpu.renderer)

        def walk(start,delta,end,slope):
            gpu.uniform('testSurface',*start);gpu.uniform('testDisplacement',*delta)
            gpu.uniform('testMode',1)
            close(gpu.draw(),end+(1,),'piecewise surface walk reaches the real rest height')
            gpu.uniform('testMode',2)
            close(gpu.draw(),slope+(end[1],1),'surface walk adopts the destination triangle slope')
        upload(gpu,lambda x,y,z: triangle if (x,y,z)==(7,9,7) else (WATER if 1<=y<9 else AIR))
        walk((68,91.4,68),(5,5),(73,88.4,73),(-0.1,-0.1))
        walk((73,88.4,73),(-5,-5),(68,91.4,68),(-0.6,-0.6))
        walk((68,91.4,68),(2,2),(70,89,70),(-0.6,-0.6))
        walk((73,88.4,73),(-3,-3),(70,89,70),(-0.6,-0.6))
        upload(gpu,pool)
        walk((73,90.2,70),(5,0),(78,88.4,70),(-0.2,0))
        walk((78,88.4,70),(-5,0),(73,90.2,70),(-0.6,0))
        walk((73,90.2,70),(2,0),(75,89,70),(-0.2,0))
        walk((78,88.4,70),(-3,0),(75,89,70),(-0.2,0))
        walk((75,89,70),(0,0),(75,89,70),(-0.2,0))
        flow=(240/255,0.9,0,0.4,1,0.8,1,0.8)
        upload(gpu,lambda x,y,z: flow if (x,y,z)==(8,9,7) else (WATER if 1<=y<=9 else AIR))
        walk((73,95,70),(5,0),(78,94.4,70),(-0.2,0))
        walk((78,94.4,70),(-5,0),(73,95,70),(0,0))
        plain=lambda x,y,z: WATER if 1<=y<=9 else AIR
        upload(gpu,plain)
        walk((72,95,72),(8,8),(80,95,80),(0,0))
        walk((80,95,80),(-8,-8),(72,95,72),(0,0))
        gpu.uniform('testMode',1);gpu.uniform('testSurface',72,95,70)
        gpu.uniform('testDisplacement',8,8)
        for invalid in (AIR,SOLID,(0,0,0,0),(224/255,1,0,0.4)):
            upload(gpu,lambda x,y,z: invalid if (x,y,z)==(8,9,7) else plain(x,y,z))
            close(gpu.draw(),(0,0,0,0),'walk cannot jump an intermediate invalid face')
        upload(gpu,lambda x,y,z: WATER if (x,y,z)==(8,10,7) else plain(x,y,z))
        close(gpu.draw(),(0,0,0,0),'a covered internal top is not a sunlit surface')
        upload(gpu,plain);gpu.uniform('testSurface',152,95,70)
        close(gpu.draw(),(0,0,0,0),'out-of-volume face remains unknown')
        gpu.uniform('testSurface',72,95,72);gpu.uniform('testDisplacement',20,0)
        close(gpu.draw(),(0,0,0,0),'oversized surface correction fails closed')
        print('PASS: bidirectional diagonals/cells, source-flow joins, corner ties and intermediate/covered/unknown guards;',gpu.renderer)


if __name__=='__main__':
    connected_faces()
