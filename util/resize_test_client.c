// Luanti
// SPDX-License-Identifier: LGPL-2.1-or-later
// Test-only SDL window resize hook. Loaded only in the disposable client.
// It sends no keyboard, pointer or focus events and accesses no other process.
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

void SDL_GL_SwapWindow(void *window)
{
	static void (*swap)(void *);
	static void (*resize)(void *, int, int);
	static unsigned int applied;
	if (!swap) {
		swap = dlsym(RTLD_NEXT, "SDL_GL_SwapWindow");
		resize = dlsym(RTLD_NEXT, "SDL_SetWindowSize");
		if (!swap || !resize) {
			fprintf(stderr, "Benchmark SDL resize: missing SDL2 entry points\n");
			abort();
		}
	}
	const char *request = getenv("BISMUTH_RESIZE_REQUEST");
	FILE *file = request ? fopen(request, "r") : NULL;
	if (file) {
		unsigned int sequence, width, height;
		int valid = fscanf(file, "%u %u %u", &sequence, &width, &height) == 3;
		fclose(file);
		if (valid && sequence > applied && width >= 64 && height >= 64 && width <= 8192 && height <= 8192) {
			resize(window, (int)width, (int)height);
			applied = sequence;
			fprintf(stderr, "Benchmark SDL resize: pid=%ld sequence=%u size=%ux%u\n",
				(long)getpid(), sequence, width, height);
		}
	}
	swap(window);
}
