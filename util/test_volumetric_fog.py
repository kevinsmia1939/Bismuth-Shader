#!/usr/bin/env python3
"""Numeric tests of the actual fog GLSL in a hidden SDL/OpenGL context.

Requires Python 3, SDL2 and desktop OpenGL. No input automation or image capture.
"""
# SPDX-License-Identifier: LGPL-2.1-or-later
import ctypes as c
import math
from pathlib import Path


def run():
    sdl = c.CDLL("libSDL2-2.0.so.0")
    gl = c.CDLL("libGL.so.1")
    uint, integer, real, pointer = c.c_uint, c.c_int, c.c_float, c.c_void_p

    def function(library, name, result, *arguments):
        f = getattr(library, name)
        f.restype, f.argtypes = result, list(arguments)
        return f

    def api(name, result, *arguments):
        return function(gl, name, result, *arguments)

    init = function(sdl, "SDL_Init", integer, uint)
    create_window = function(sdl, "SDL_CreateWindow", pointer,
                             c.c_char_p, integer, integer, integer, integer, uint)
    create_context = function(sdl, "SDL_GL_CreateContext", pointer, pointer)
    assert init(32) == 0, "SDL video initialization failed"
    window = create_window(b"Luanti numeric shader test", 0, 0, 8, 8, 2 | 8)
    assert window, "Hidden SDL window creation failed"
    context = create_context(window)
    assert context, "Desktop GL context creation failed"
    try:
        shader_source = api("glShaderSource", None, uint, integer,
                            c.POINTER(c.c_char_p), pointer)
        get_shader = api("glGetShaderiv", None, uint, uint, c.POINTER(integer))
        get_shader_log = api("glGetShaderInfoLog", None, uint, integer, pointer, c.c_char_p)
        shader_path = Path(__file__).resolve().parents[1] / "client/shaders/scene_lighting/opengl_fragment.glsl"
        fragment = shader_path.read_text()
        vertex = """varying vec2 varTexCoord;
void main() { gl_Position = gl_Vertex; varTexCoord = gl_Vertex.xy * 0.5 + 0.5; }
"""
        prefix = """#version 120
#define ENABLE_ATMOSPHERE
#define ENABLE_VOLUMETRIC_FOG
#define ENABLE_DYNAMIC_SHADOWS
#define COLORED_SHADOWS
#define CENTROID_
#define VARYING_ varying
#define mediump
"""
        program = api("glCreateProgram", uint)()
        for kind, body in ((0x8B31, vertex), (0x8B30, fragment)):
            shader = api("glCreateShader", uint, uint)(kind)
            source = c.c_char_p((prefix + body).encode())
            shader_source(shader, 1, c.byref(source), None)
            api("glCompileShader", None, uint)(shader)
            ok, log = integer(), c.create_string_buffer(16384)
            get_shader(shader, 0x8B81, c.byref(ok))
            get_shader_log(shader, len(log), None, log)
            assert ok.value, log.value.decode()
            api("glAttachShader", None, uint, uint)(program, shader)
            api("glDeleteShader", None, uint)(shader)
        api("glLinkProgram", None, uint)(program)
        ok = integer()
        api("glGetProgramiv", None, uint, uint, c.POINTER(integer))(program, 0x8B82, c.byref(ok))
        assert ok.value, "GLSL link failed"
        api("glUseProgram", None, uint)(program)
        location = api("glGetUniformLocation", integer, uint, c.c_char_p)

        def uniform(name, *values):
            loc = location(program, name.encode())
            assert loc >= 0, f"Missing active uniform {name}"
            api(f"glUniform{len(values)}f", None, integer, *([real] * len(values)))(loc, *values)

        def matrix(name, values):
            loc = location(program, name.encode())
            assert loc >= 0, name
            data = (real * 16)(*values)
            api("glUniformMatrix4fv", None, integer, integer, c.c_ubyte, c.POINTER(real))(loc, 1, 0, data)

        identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
        for name in ("inverseProjection", "inverseView", "m_ShadowViewProj"):
            matrix(name, identity)
        uniform("cameraPosition", 0, 0, 0)
        uniform("cameraOffset", 0, 0, 0)
        uniform("CameraPos", 0, 0, 0, 1)
        uniform("volumeLightDirection", 0, 0, 1)
        uniform("xyPerspectiveBias0", 0.9)
        uniform("xyPerspectiveBias1", 0.10001)
        uniform("zPerspectiveBias", 0.5)
        uniform("fogColor", 0.2, 0.3, 0.4, 1)
        uniform("volumeParams", 10, 100, 0, 24)
        uniform("sceneParams", 0.5, 0, 0, 0)
        uniform("atmosphereEnabled", 1)
        uniform("volumeShadowReady", 1)
        uniform("volumeLightColor", 0.8, 0.6, 0.4)
        bind_texture = api("glBindTexture", None, uint, uint)
        tex_image = api("glTexImage2D", None, uint, integer, integer, integer, integer,
                        integer, uint, uint, pointer)
        param = api("glTexParameteri", None, uint, uint, integer)

        def texture(unit, values):
            api("glActiveTexture", None, uint)(0x84C0 + unit)
            bind_texture(0x0DE1, unit + 1)
            for key, value in ((0x2801, 0x2600), (0x2800, 0x2600),
                               (0x2802, 0x812F), (0x2803, 0x812F)):
                param(0x0DE1, key, value)
            pixels = (real * 4)(*values)
            tex_image(0x0DE1, 0, 0x8814, 1, 1, 0, 0x1908, 0x1406, pixels)

        for name, unit in (("texture0", 0), ("texture1", 1), ("ShadowMapSampler", 3)):
            api("glUniform1i", None, integer, integer)(location(program, name.encode()), unit)
        texture(0, (0.4, 0.5, 0.6, 0.7))
        texture(1, (0.75, 0, 0, 1))
        texture(3, (1, 0, 1, 0))
        bind_texture(0x0DE1, 99)
        tex_image(0x0DE1, 0, 0x8814, 1, 1, 0, 0x1908, 0x1406, None)
        fbo = uint()
        api("glGenFramebuffers", None, integer, c.POINTER(uint))(1, c.byref(fbo))
        api("glBindFramebuffer", None, uint, uint)(0x8D40, fbo)
        api("glFramebufferTexture2D", None, uint, uint, uint, uint, integer)(0x8D40, 0x8CE0, 0x0DE1, 99, 0)
        assert api("glCheckFramebufferStatus", uint, uint)(0x8D40) == 0x8CD5
        # Restore sampler 3 after allocating the output attachment.
        bind_texture(0x0DE1, 4)
        api("glViewport", None, integer, integer, integer, integer)(0, 0, 1, 1)

        def draw():
            api("glBegin", None, uint)(7)
            for x, y in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                api("glVertex2f", None, real, real)(x, y)
            api("glEnd", None)()
            result = (real * 4)()
            api("glReadPixels", None, integer, integer, integer, integer, uint, uint, pointer)(
                0, 0, 1, 1, 0x1908, 0x1406, result)
            assert all(math.isfinite(x) for x in result), list(result)
            assert abs(result[3] - 0.7) < 1e-5, "Alpha changed"
            assert api("glGetError", uint)() == 0, "OpenGL error"
            return list(result)[:3]

        def close(actual, expected, label, tolerance=2e-5):
            assert max(abs(a - b) for a, b in zip(actual, expected)) < tolerance, (label, actual, expected)

        def expected(direct, distance=0.5, density=0.5):
            # Constant density has an exact analytic single-scattering solution.
            phase = (1 + 0.55) / (1 - 0.55) ** 2
            answer = []
            for base, fog, sun, extinction, visibility in zip(
                    (0.4, 0.5, 0.6), (0.2, 0.3, 0.4), (0.8, 0.6, 0.4),
                    (0.65, 0.9, 1.25), direct):
                transmission = math.exp(-density * distance * extinction)
                source = fog ** 2.2 * 0.65 + sun * phase * 0.25 * visibility
                answer.append((base ** 2.2 * transmission + source * (1 - transmission)) ** (1 / 2.2))
            return answer

        lit = draw()
        close(lit, expected((1, 1, 1)), "homogeneous integral")
        texture(3, (0.1, 0, 1, 0))
        blocked = draw()
        close(blocked, expected((0, 0, 0)), "opaque occlusion")
        assert all(a > b for a, b in zip(lit, blocked)), "Blocked sunlight leaked"
        texture(3, (1, 0, 0.1, 64 * 129 * 129))
        close(draw(), expected((0.5, 0, 0)), "colored transparent shadow")
        texture(3, (float("nan"),) * 4)
        uniform("volumeShadowReady", 0)
        close(draw(), lit, "absent map bypass")
        uniform("volumeShadowReady", 1)
        uniform("sceneParams", 0, 0, 0, 0)
        close(draw(), (0.4, 0.5, 0.6), "zero density bypass")
        uniform("sceneParams", 0.5, 0, 0, 0)
        uniform("atmosphereEnabled", 0)
        close(draw(), (0.4, 0.5, 0.6), "underwater/solid bypass")
        uniform("atmosphereEnabled", 1)
        texture(3, (1, 0, 1, 0))
        texture(1, (1, 0, 0, 1))
        close(draw(), expected((1, 1, 1), 0.99998), "sky integration")
        texture(1, (0.75, 0, 0, 1))
        uniform("volumeParams", 0.1, 100, 0, 24)
        close(draw(), expected((1, 1, 1), 0.1), "distance cap")
        uniform("volumeParams", 10, 100, 0, 8)
        close(draw(), lit, "sample count invariance")
        uniform("volumeParams", 10, 100, 0, 64)
        close(draw(), lit, "high sample count invariance")
        uniform("cameraPosition", 0, 100, 0)
        close(draw(), expected((1, 1, 1), density=0.5 / math.e), "height falloff")
        uniform("cameraPosition", 0, 0, 0)
        translated = identity[:]
        translated[12] = 3
        matrix("m_ShadowViewProj", translated)
        close(draw(), blocked, "outside shadow coverage")
        matrix("m_ShadowViewProj", identity)
        uniform("volumeParams", 10, 100, 0.8, 24)
        noisy = draw()
        translated = identity[:]
        translated[12], translated[14] = -200, -100
        matrix("inverseView", translated)
        uniform("cameraOffset", 200, 0, 100)
        uniform("volumeShadowReady", 0)
        close(draw(), noisy, "density stability across camera offset")
        renderer = api("glGetString", c.c_char_p, uint)(0x1F01).decode()
        print(f"Renderer: {renderer}; GLSL 120")
        print("PASS: volumetric fog GLSL; analytic transmission, opaque/colored occlusion, "
              "shadow guard, zero density, underwater bypass, sky, distance/height, "
              "sample counts and camera offset. No images captured.")
    finally:
        function(sdl, "SDL_GL_DeleteContext", None, pointer)(context)
        function(sdl, "SDL_DestroyWindow", None, pointer)(window)
        function(sdl, "SDL_Quit", None)()


if __name__ == "__main__":
    run()
