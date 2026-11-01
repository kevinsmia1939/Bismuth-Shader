"""Small numeric GLSL test fixture. Hidden SDL context; no image or input APIs."""
# SPDX-License-Identifier: LGPL-2.1-or-later
import ctypes as c
import math
import os


class ShaderTest:
    def __init__(self, fragment, size=64):
        self.sdl = c.CDLL("libSDL2-2.0.so.0")
        self.gl = c.CDLL("libGL.so.1")
        self.size = size
        self.core_shader = int(os.environ.get("LUANTI_TEST_GLSL", "330")) >= 330
        self.window = None
        self.context = None
        self.program = None
        try:
            assert self.sdl_api("SDL_Init", c.c_int, c.c_uint)(32) == 0
            self.window = self.sdl_api("SDL_CreateWindow", c.c_void_p, c.c_char_p,
                                      c.c_int, c.c_int, c.c_int, c.c_int, c.c_uint)(
                b"Luanti numeric shader test", 0, 0, size, size, 2 | 8)
            assert self.window, "Hidden window creation failed"
            self.context = self.sdl_api("SDL_GL_CreateContext", c.c_void_p, c.c_void_p)(self.window)
            assert self.context, "Desktop GL context creation failed"
            self.renderer = self.api("glGetString", c.c_char_p, c.c_uint)(0x1F01).decode()
            self.program = self.api("glCreateProgram", c.c_uint)()
            vertex = "void main(){gl_Position=gl_Vertex;}"
            prefix = "#version 120\n"
            if self.core_shader:
                prefix = "#version 330 core\n"
                vertex = """void main() {
 const vec2 vertices[3] = vec2[3](vec2(-1,-1), vec2(3,-1), vec2(-1,3));
 gl_Position = vec4(vertices[gl_VertexID], 0, 1);
}"""
                fragment = """layout(location=0) out vec4 testOutput;
#define gl_FragColor testOutput
#define texture2D texture
""" + fragment
                vao = c.c_uint()
                self.api("glGenVertexArrays", None, c.c_int, c.POINTER(c.c_uint))(1, c.byref(vao))
                self.api("glBindVertexArray", None, c.c_uint)(vao)
            for kind, body in ((0x8B31, vertex), (0x8B30, fragment)):
                shader = self.api("glCreateShader", c.c_uint, c.c_uint)(kind)
                source = c.c_char_p((prefix + body).encode())
                self.api("glShaderSource", None, c.c_uint, c.c_int, c.POINTER(c.c_char_p), c.c_void_p)(
                    shader, 1, c.byref(source), None)
                self.api("glCompileShader", None, c.c_uint)(shader)
                ok, log = c.c_int(), c.create_string_buffer(16384)
                self.api("glGetShaderiv", None, c.c_uint, c.c_uint, c.POINTER(c.c_int))(
                    shader, 0x8B81, c.byref(ok))
                self.api("glGetShaderInfoLog", None, c.c_uint, c.c_int, c.c_void_p, c.c_char_p)(
                    shader, len(log), None, log)
                assert ok.value, log.value.decode()
                self.api("glAttachShader", None, c.c_uint, c.c_uint)(self.program, shader)
                self.api("glDeleteShader", None, c.c_uint)(shader)
            self.api("glLinkProgram", None, c.c_uint)(self.program)
            ok = c.c_int()
            self.api("glGetProgramiv", None, c.c_uint, c.c_uint, c.POINTER(c.c_int))(
                self.program, 0x8B82, c.byref(ok))
            assert ok.value, "Shader link failed"
            self.api("glUseProgram", None, c.c_uint)(self.program)
            self.api("glBindTexture", None, c.c_uint, c.c_uint)(0x0DE1, 99)
            self.api("glTexImage2D", None, c.c_uint, c.c_int, c.c_int, c.c_int,
                     c.c_int, c.c_int, c.c_uint, c.c_uint, c.c_void_p)(
                0x0DE1, 0, 0x8814, size, size, 0, 0x1908, 0x1406, None)
            fbo = c.c_uint()
            self.api("glGenFramebuffers", None, c.c_int, c.POINTER(c.c_uint))(1, c.byref(fbo))
            self.api("glBindFramebuffer", None, c.c_uint, c.c_uint)(0x8D40, fbo)
            self.api("glFramebufferTexture2D", None, c.c_uint, c.c_uint, c.c_uint, c.c_uint, c.c_int)(
                0x8D40, 0x8CE0, 0x0DE1, 99, 0)
            assert self.api("glCheckFramebufferStatus", c.c_uint, c.c_uint)(0x8D40) == 0x8CD5
            self.api("glViewport", None, *([c.c_int] * 4))(0, 0, size, size)
        except BaseException:
            self.close()
            raise

    @staticmethod
    def function(library, name, result, *args):
        f = getattr(library, name)
        f.restype, f.argtypes = result, list(args)
        return f

    def api(self, name, result, *args):
        return self.function(self.gl, name, result, *args)

    def sdl_api(self, name, result, *args):
        return self.function(self.sdl, name, result, *args)

    def location(self, name):
        loc = self.api("glGetUniformLocation", c.c_int, c.c_uint, c.c_char_p)(self.program, name.encode())
        assert loc >= 0, f"Missing uniform: {name}"
        return loc

    def uniform(self, name, *values):
        self.api(f"glUniform{len(values)}f", None, c.c_int, *([c.c_float] * len(values)))(
            self.location(name), *values)

    def sampler(self, name, unit):
        self.api("glUniform1i", None, c.c_int, c.c_int)(self.location(name), unit)

    def matrix(self, name, values):
        self.api("glUniformMatrix4fv", None, c.c_int, c.c_int, c.c_ubyte, c.POINTER(c.c_float))(
            self.location(name), 1, 0, (c.c_float * 16)(*values))

    def texture(self, unit, values, linear=False, width=None, height=None):
        width = self.size if width is None else width
        height = self.size if height is None else height
        if len(values) == 4:
            values = list(values) * (width * height)
        assert len(values) == width * height * 4
        self.api("glActiveTexture", None, c.c_uint)(0x84C0 + unit)
        self.api("glBindTexture", None, c.c_uint, c.c_uint)(0x0DE1, unit + 1)
        param = self.api("glTexParameteri", None, c.c_uint, c.c_uint, c.c_int)
        for key, value in ((0x2801, 0x2601 if linear else 0x2600),
                           (0x2800, 0x2601 if linear else 0x2600), (0x2802, 0x812F), (0x2803, 0x812F)):
            param(0x0DE1, key, value)
        data = (c.c_float * len(values))(*values)
        self.api("glTexImage2D", None, c.c_uint, c.c_int, c.c_int, c.c_int, c.c_int,
                 c.c_int, c.c_uint, c.c_uint, c.c_void_p)(
            0x0DE1, 0, 0x8814, width, height, 0, 0x1908, 0x1406, data)

    def draw(self, x=None, y=None):
        if self.core_shader:
            self.api("glDrawArrays", None, c.c_uint, c.c_int, c.c_int)(4, 0, 3)
        else:
            self.api("glBegin", None, c.c_uint)(7)
            for vx, vy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                self.api("glVertex2f", None, c.c_float, c.c_float)(vx, vy)
            self.api("glEnd", None)()
        result = (c.c_float * 4)()
        self.api("glReadPixels", None, *([c.c_int] * 4), c.c_uint, c.c_uint, c.c_void_p)(
            self.size // 2 if x is None else x, self.size // 2 if y is None else y,
            1, 1, 0x1908, 0x1406, result)
        assert all(math.isfinite(v) for v in result), list(result)
        assert self.api("glGetError", c.c_uint)() == 0, "OpenGL error"
        return list(result)

    def close(self):
        if self.context:
            self.sdl_api("SDL_GL_DeleteContext", None, c.c_void_p)(self.context)
            self.context = None
        if self.window:
            self.sdl_api("SDL_DestroyWindow", None, c.c_void_p)(self.window)
            self.window = None
        self.sdl_api("SDL_Quit", None)()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
