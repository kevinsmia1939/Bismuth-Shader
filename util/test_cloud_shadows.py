#!/usr/bin/env python3
"""Actual cloud optical-depth generation/projection/lighting GLSL; numeric pixels only."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import math
from pathlib import Path
from gl_shader_test import ShaderTest

ROOT = Path(__file__).resolve().parents[1]/"client/shaders"
DENSITY = (ROOT/"common/volumetric_clouds.glsl").read_text()
SAMPLE = "#define ENABLE_CLOUD_SHADOWS\n"+(ROOT/"common/cloud_shadows.glsl").read_text()
GENERATE = (ROOT/"cloud_shadows/opengl_fragment.glsl").read_text().replace(
    "CENTROID_ VARYING_ mediump vec2 varTexCoord;", "")


def close(actual, expected, label, tolerance=3e-4):
    assert max(abs(a-b) for a,b in zip(actual,expected))<tolerance,(label,actual,expected)


def generation():
    with ShaderTest(DENSITY+GENERATE) as gpu:
        gpu.sampler("texture2",2)
        gpu.texture(2,(0.5,0.5,0.5,1),True,width=6,height=24)
        gpu.uniform("cloudTextureSize",6,24)
        gpu.uniform("cloudLayer",100,120,1,0.01)
        gpu.uniform("cloudParams",1,32,1000,0)
        gpu.uniform("cloudWind",0,0,0,0)
        gpu.uniform("cloudLight",0,1,0,1)
        gpu.uniform("cloudShadowOrigin",0,100,0)
        gpu.uniform("cloudShadowParams",0,1/128,0,0)
        gpu.uniform("cloudShadowSlab",120,1,1/64)
        # Native vertical profile has integral .77, and upper partial integrals
        # .5266667 and .1933333 at 1/3 and 2/3. Midpoint quadrature is bounded.
        expected=(0.77*1.2,(0.72-1/3+0.14)*1.2,(0.72-2/3+0.14)*1.2,0)
        close(gpu.draw(),tuple(math.exp(-x) for x in expected),"native cloud density cumulative optical depths",0.001)
        gpu.uniform("cloudLight",0.6,0.8,0,1)
        close(gpu.draw(),tuple(math.exp(-x/0.8) for x in expected),"oblique Beer-Lambert path length",0.001)
        gpu.uniform("cloudLight",0.6,-0.8,0,1)
        gpu.uniform("cloudShadowOrigin",0,220,0)
        close(gpu.draw(),tuple(math.exp(-x) for x in (0.77*1.5,(0.77-(0.72-2/3+0.14))*1.5,
                          (0.09+1/3-0.18)*1.5,0)),"light from below traverses the same density",0.001)
        for layer,ready,light in (((100,120,0,0.01),1,(0,1,0,1)),
                                  ((100,0,1,0.01),1,(0,1,0,1)),
                                  ((100,120,1,0),1,(0,1,0,1)),
                                  ((100,120,1,0.01),0,(0,1,0,1)),
                                  ((100,120,1,0.01),1,(0,1,0,0)),
                                  ((100,120,1,0.01),1,(1,0,0,1))):
            gpu.uniform("cloudLayer",*layer);gpu.uniform("cloudParams",ready,32,1000,0)
            gpu.uniform("cloudLight",*light)
            gpu.texture(2,(float("nan"),)*4,True,width=6,height=24)
            close(gpu.draw(),(1,1,1,1),"empty/hidden/transparent/horizon bypass before sampling")
        print(f"PASS: actual cloud-shadow generation, native density profile, height anchors, oblique/downward light and bypasses; {gpu.renderer}")


def receivers():
    fragment=SAMPLE+"""
uniform vec3 testPosition;
uniform vec3 testNormal;
uniform vec3 testGeometry;
uniform float testNight;
uniform float testMode;
void main() {
 float t=cloudSunTransmission(testPosition);
 if(testMode<0.5) gl_FragColor=vec4(t);
 else gl_FragColor=vec4(cloudShadeNative(vec3(0.8,0.5,0.2),t,testNormal,testNight,testGeometry),1);
}
"""
    with ShaderTest(fragment) as gpu:
        gpu.sampler("texture7",7);gpu.texture(7,tuple(math.exp(-x) for x in (2,4/3,2/3,0)),True)
        gpu.uniform("cloudShadowOrigin",0,100,0);gpu.uniform("cloudShadowDirection",0,1,0)
        gpu.uniform("cloudShadowSlab",120,1,0);gpu.uniform("cloudShadowParams",1,1/200,1,1)
        gpu.uniform("testPosition",0,0,0);gpu.uniform("testMode",0)
        gpu.uniform("testNormal",0,1,0);gpu.uniform("testNight",0);gpu.uniform("testGeometry",1,1,1)
        for y,tau in ((0,2),(100,2),(140,4/3),(160,1),(180,2/3),(220,0),(250,0)):
            gpu.uniform("testPosition",0,y,0)
            close(gpu.draw(),(math.exp(-tau),)*4,"receiver below/inside/above layer")
        gpu.uniform("testPosition",0,0,0);gpu.uniform("testMode",1)
        factor=(1-0.65*(1-math.exp(-2)))**(1/2.2)
        close(gpu.draw(),(0.8*factor,0.5*factor,0.2*factor,1),"direct estimate attenuates in linear light")
        for normal,night,geometry in (((0,1,0),1,(1,1,1)),((0,1,0),0,(0,0,0)),((0,-1,0),0,(1,1,1))):
            gpu.uniform("testNormal",*normal);gpu.uniform("testNight",night);gpu.uniform("testGeometry",*geometry)
            close(gpu.draw(),(0.8,0.5,0.2,1),"artificial light, geometry shade and backfaces are preserved")
        gpu.uniform("testMode",0)
        gpu.uniform("cloudShadowDirection",0,-1,0);gpu.uniform("cloudShadowOrigin",0,220,0)
        gpu.uniform("cloudShadowSlab",120,-1,0)
        for y,tau in ((250,2),(180,4/3),(140,2/3),(100,0),(80,0)):
            gpu.uniform("testPosition",0,y,0)
            close(gpu.draw(),(math.exp(-tau),)*4,"downward-light receiver heights")
        gpu.uniform("cloudShadowOrigin",0,100,0);gpu.uniform("cloudShadowDirection",0.6,0.8,0)
        gpu.uniform("cloudShadowSlab",120,1,0)
        # A linear map checks light-direction projection and both texture axes.
        gradient=[c for y in range(64) for x in range(64)
                  for c in (math.exp(-1-2*(x+0.5)/64-3*(y+0.5)/64),1,1,1)]
        gpu.texture(7,gradient,True)
        gpu.uniform("testPosition",-20,0,-30)
        close(gpu.draw(),(math.exp(-3.6),)*4,"world/light projection into the cloud map")
        gpu.uniform("cloudShadowOrigin",-2000,100,0);gpu.uniform("testPosition",-2020,0,-30)
        close(gpu.draw(),(math.exp(-3.6),)*4,"camera-origin shift preserves the shadow")
        # Filtering must average transmission, not optical depth: equal dark
        # and clear texels transmit half the light at their boundary.
        gpu.uniform("cloudShadowOrigin",0,100,0);gpu.uniform("cloudShadowDirection",0,1,0)
        gpu.uniform("testPosition",0,0,0)
        edge=[c for y in range(64) for x in range(64) for c in ((0,0,0,1) if x<32 else (1,1,1,1))]
        gpu.texture(7,edge,True)
        close(gpu.draw(),(0.5,)*4,"spatial cloud-edge filtering conserves transmission")
        for ready,strength,fade in ((0,1,1),(1,0,1),(1,1,0)):
            gpu.uniform("cloudShadowParams",ready,1/200,strength,fade)
            gpu.texture(7,(float("nan"),)*4)
            close(gpu.draw(),(1,)*4,"unbound/zero/horizon receiver bypass")
        gpu.uniform("cloudShadowParams",1,1/200,1,1)
        gpu.uniform("testPosition",10000,0,10000)
        close(gpu.draw(),(1,)*4,"uncovered rays do not clamp distant cloud shadows onto terrain")
        print(f"PASS: cloud shadow projection, partial layers, origin shifts, native-light separation and guards; {gpu.renderer}")


def end_to_end_map():
    # Generate a varying physical field, copy its float target to sampler7, and
    # sample it with the actual receiver. No image output or device input occurs.
    field="""uniform vec4 cloudParams,cloudLayer,cloudLight;
float cloudDensity(vec3 p) { return 0.5+0.002*p.x+0.003*p.z; }
"""
    gen=GENERATE.replace("void main()","void generateCloudShadow()")
    # Generator and receiver share uniforms, but the generation file declares
    # these three too; retain only one declaration of each.
    for line in ("uniform vec3 cloudShadowOrigin; // absolute center on the entry boundary\n",
                 "uniform vec4 cloudShadowParams; // unused, reciprocal span, unused, unused\n",
                 "uniform vec3 cloudShadowSlab; // unused, unused, reciprocal map resolution\n"):
        gen=gen.replace(line,"")
    fragment=field+SAMPLE+gen+"""
uniform float testMode;
uniform vec3 testPosition;
void main(){if(testMode<0.5) generateCloudShadow();else gl_FragColor=vec4(cloudSunTransmission(testPosition));}
"""
    with ShaderTest(fragment) as gpu:
        gpu.uniform("cloudParams",1,32,1000,0);gpu.uniform("cloudLayer",100,40,1,0.01)
        gpu.uniform("cloudLight",0.6,0.8,0,1)
        gpu.uniform("cloudShadowOrigin",0,100,0);gpu.uniform("cloudShadowParams",1,1/128,1,1)
        gpu.uniform("cloudShadowDirection",0.6,0.8,0);gpu.uniform("cloudShadowSlab",40,1,1/64)
        gpu.uniform("testMode",0);gpu.uniform("testPosition",2,80,-3)
        gpu.sampler("texture7",7);gpu.texture(7,(0,0,0,0),True)
        gpu.draw()
        import ctypes as c
        gpu.api("glCopyTexSubImage2D",None,c.c_uint,*([c.c_int]*7))(0x0DE1,0,0,0,0,0,64,64)
        gpu.uniform("testMode",1)
        close(gpu.draw(),(math.exp(-0.2775),)*4,"generated optical map reaches the correct world receiver")
        print(f"PASS: generated-map-to-receiver transport, X/Z orientation and bilinear sampling; {gpu.renderer}")


def node_light_separation():
    source=(ROOT/"nodes_shader/opengl_fragment.glsl").read_text()
    begin=source.index("#if defined(ENABLE_CLOUD_SHADOWS) && !defined(MATERIAL_EMISSIVE)")
    end=source.index("#endif",begin)+len("#endif")
    block=source[begin:end]
    # Exercise the actual node composition with a backlit leaf/glint contribution
    # and full artificial light: only the explicit sun terms should be attenuated.
    fragment=SAMPLE+"""
void main() {
 vec3 worldPosition=vec3(0),fNormal=vec3(0,-1,0),cloudGeometryVisibility=vec3(0);
 float nightRatio=1.0;
 vec4 col=vec4(0.8,0.5,0.2,1);
 vec3 waterSpecular=vec3(0.1),cloudExplicitSun=vec3(0.2),materialSun=vec3(0.4),waterSunVisibility=vec3(1);
 col.rgb+=waterSpecular+cloudExplicitSun;
"""+block+"\n gl_FragColor=vec4(col.rgb,materialSun.x); }"
    with ShaderTest(fragment) as gpu:
        gpu.sampler("texture7",7);gpu.texture(7,(0.25,0.5,0.75,1),True)
        gpu.uniform("cloudShadowOrigin",0,100,0);gpu.uniform("cloudShadowDirection",0,1,0)
        gpu.uniform("cloudShadowSlab",120,1,0);gpu.uniform("cloudShadowParams",1,1/200,1,1)
        close(gpu.draw(),(0.875,0.575,0.275,0.1),"actual node pass separates artificial light, leaf backlight and specular sun")
        print(f"PASS: actual node cloud composition preserves lamps and attenuates explicit foliage/specular sunlight; {gpu.renderer}")


def fog_lighting():
    source=(ROOT/"scene_lighting/opengl_fragment.glsl").read_text().replace(
        "CENTROID_ VARYING_ mediump vec2 varTexCoord;", "#define varTexCoord (gl_FragCoord.xy/64.0)")
    source=source.replace("void main(void)","void originalMain(void)").replace("void main()","void originalMain()")
    fragment="#define ENABLE_VOLUMETRIC_FOG\n"+SAMPLE+source+"""
void main(){gl_FragColor=vec4(integrateFog(pow(vec3(0.4,0.5,0.6),vec3(2.2)),vec3(0,0,10)),1);}
"""
    with ShaderTest(fragment) as gpu:
        gpu.sampler("texture7",7)
        gpu.texture(7,tuple(math.exp(-x) for x in (2,4/3,2/3,0)),True)
        gpu.uniform("cloudShadowOrigin",0,100,0);gpu.uniform("cloudShadowDirection",0,1,0)
        gpu.uniform("cloudShadowSlab",120,1,0);gpu.uniform("cloudShadowParams",1,1/200,1,1)
        gpu.matrix("inverseView",[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1])
        gpu.uniform("cameraPosition",0,0,0);gpu.uniform("cameraOffset",0,0,0)
        gpu.uniform("sceneParams",0.1,0,0,0);gpu.uniform("fogColor",0.2,0.3,0.4,1)
        gpu.uniform("volumeParams",10,100,0,24);gpu.uniform("volumeLightDirection",0,1,0)
        gpu.uniform("volumeLightColor",0.8,0.6,0.4)
        phase=(1-0.55**2)/(1+0.55**2)**1.5
        def expected(visibility,sun=(0.8,0.6,0.4)):
            out=[]
            for base,fog,light,sigma in zip((0.4,0.5,0.6),(0.2,0.3,0.4),sun,(0.65,0.9,1.25)):
                t=math.exp(-sigma)
                out.append(base**2.2*t+(fog**2.2*0.65+light*phase*0.25*visibility)*(1-t))
            return out+[1]
        close(gpu.draw(),expected(math.exp(-2)),"actual fog direct sunlight sees cloud transmission")
        gpu.uniform("volumeLightColor",0,0,0)
        close(gpu.draw(),expected(1,(0,0,0)),"cloud shadows preserve ambient fog scattering")
        gpu.uniform("volumeLightColor",0.8,0.6,0.4);gpu.uniform("cloudShadowParams",0,1/200,1,1)
        close(gpu.draw(),expected(1),"unbound cloud maps retain native direct fog")
        print(f"PASS: actual volumetric fog shares cloud extinction and preserves ambient scattering; {gpu.renderer}")


if __name__=="__main__":
    generation()
    receivers()
    end_to_end_map()
    fog_lighting()
    node_light_separation()
