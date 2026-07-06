"""Build the in-process libmgba binding (cffi).

Compiles `game/_mgba_native` against the Homebrew-installed libmgba
(`brew install mgba`). Run once to (re)generate the extension:

    python -m game._mgba_build

This replaces the entire mGBA-http / Lua / .NET transport stack: the agent
drives the emulator directly, in-process, at many times real-time.

The cdef exposes only a small set of flat wrapper functions (opaque `void*`
handle) — all struct layouts live in the real headers pulled in by set_source,
so nothing here depends on libmgba's internal ABI details.
"""
import os
import cffi

# Homebrew prefix — override with MGBA_PREFIX if libmgba lives elsewhere.
PREFIX = os.environ.get("MGBA_PREFIX", "/opt/homebrew")
INCLUDE = os.path.join(PREFIX, "include")
LIBDIR = os.path.join(PREFIX, "lib")

ffi = cffi.FFI()

ffi.cdef("""
    void*    pycore_load(const char* path);
    void     pycore_destroy(void* h);
    void     pycore_set_keys(void* h, uint32_t keys);
    void     pycore_run_frame(void* h);
    uint32_t pycore_read8(void* h, uint32_t address);
    uint32_t pycore_read16(void* h, uint32_t address);
    uint32_t pycore_read32(void* h, uint32_t address);
    void     pycore_read_range(void* h, uint32_t address, uint32_t length, uint8_t* out);
    void     pycore_write8(void* h, uint32_t address, uint8_t value);
    void     pycore_write16(void* h, uint32_t address, uint16_t value);
    void     pycore_write32(void* h, uint32_t address, uint32_t value);
    int      pycore_save_state(void* h, const char* path);
    int      pycore_load_state(void* h, const char* path);
    int      pycore_screenshot(void* h, const char* path);
    void     pycore_video_dims(void* h, uint32_t* w, uint32_t* ht);
    void*    pycore_video_ptr(void* h);
    int      pycore_load_save(void* h, const char* path);
    void     pycore_reset(void* h);
""")

ffi.set_source(
    "game._mgba_native",
    r"""
    #include <mgba/core/core.h>
    #include <mgba/core/config.h>
    #include <mgba/core/interface.h>
    #include <mgba/core/serialize.h>
    #include <mgba/core/log.h>
    #include <mgba-util/vfs.h>
    #include <stdlib.h>
    #include <stdarg.h>
    #include <fcntl.h>

    /* Swallow libmgba's very chatty BIOS/DMA logging. */
    static void _silent_log(struct mLogger* l, int c, enum mLogLevel lv,
                            const char* fmt, va_list a) { (void)l;(void)c;(void)lv;(void)fmt;(void)a; }
    static struct mLogger _silent = { .log = _silent_log };

    typedef struct { struct mCore* core; color_t* video; unsigned vw, vh; } PyCore;

    /* Save/load state flag masks (match project's documented defaults):
       SCREENSHOT=1 SAVEDATA=2 CHEATS=4 RTC=8 METADATA=16 */
    static const int SAVE_FLAGS = 31;   /* everything */
    static const int LOAD_FLAGS = 29;   /* everything except screenshot */

    void* pycore_load(const char* path) {
        mLogSetDefaultLogger(&_silent);
        struct mCore* core = mCoreFind(path);
        if (!core) return NULL;
        if (!core->init(core)) return NULL;
        mCoreInitConfig(core, NULL);
        if (!mCoreLoadFile(core, path)) { core->deinit(core); return NULL; }
        unsigned w = 0, h = 0;
        core->desiredVideoDimensions(core, &w, &h);
        color_t* buf = calloc((size_t)w * h, sizeof(color_t));
        core->setVideoBuffer(core, buf, w);
        core->reset(core);
        PyCore* pc = malloc(sizeof(PyCore));
        pc->core = core; pc->video = buf; pc->vw = w; pc->vh = h;
        return pc;
    }
    void pycore_destroy(void* h) {
        PyCore* pc = (PyCore*)h;
        if (!pc) return;
        pc->core->deinit(pc->core);
        free(pc->video);
        free(pc);
    }
    void pycore_set_keys(void* h, uint32_t keys) {
        PyCore* pc = (PyCore*)h; pc->core->setKeys(pc->core, keys);
    }
    void pycore_run_frame(void* h) {
        PyCore* pc = (PyCore*)h; pc->core->runFrame(pc->core);
    }
    uint32_t pycore_read8(void* h, uint32_t a)  { PyCore* pc=(PyCore*)h; return pc->core->busRead8(pc->core, a); }
    uint32_t pycore_read16(void* h, uint32_t a) { PyCore* pc=(PyCore*)h; return pc->core->busRead16(pc->core, a); }
    uint32_t pycore_read32(void* h, uint32_t a) { PyCore* pc=(PyCore*)h; return pc->core->busRead32(pc->core, a); }
    void pycore_read_range(void* h, uint32_t a, uint32_t len, uint8_t* out) {
        PyCore* pc = (PyCore*)h;
        for (uint32_t i = 0; i < len; i++) out[i] = (uint8_t)pc->core->busRead8(pc->core, a + i);
    }
    void pycore_write8(void* h, uint32_t a, uint8_t v)   { PyCore* pc=(PyCore*)h; pc->core->busWrite8(pc->core, a, v); }
    void pycore_write16(void* h, uint32_t a, uint16_t v) { PyCore* pc=(PyCore*)h; pc->core->busWrite16(pc->core, a, v); }
    void pycore_write32(void* h, uint32_t a, uint32_t v) { PyCore* pc=(PyCore*)h; pc->core->busWrite32(pc->core, a, v); }

    int pycore_save_state(void* h, const char* path) {
        PyCore* pc = (PyCore*)h;
        struct VFile* vf = VFileOpen(path, O_WRONLY | O_CREAT | O_TRUNC);
        if (!vf) return 0;
        int ok = mCoreSaveStateNamed(pc->core, vf, SAVE_FLAGS);
        vf->close(vf);
        return ok;
    }
    int pycore_load_state(void* h, const char* path) {
        PyCore* pc = (PyCore*)h;
        struct VFile* vf = VFileOpen(path, O_RDONLY);
        if (!vf) return 0;
        int ok = mCoreLoadStateNamed(pc->core, vf, LOAD_FLAGS);
        vf->close(vf);
        return ok;
    }
    int pycore_screenshot(void* h, const char* path) {
        PyCore* pc = (PyCore*)h;
        struct VFile* vf = VFileOpen(path, O_WRONLY | O_CREAT | O_TRUNC);
        if (!vf) return 0;
        int ok = mCoreTakeScreenshotVF(pc->core, vf);
        vf->close(vf);
        return ok;
    }
    /* Live framebuffer access for the viewer. On this (32-bit color) build each
       pixel is laid out [R, G, B, pad] in memory, i.e. directly usable as RGBX.
       The buffer is persistent — libmgba writes the latest frame into it. */
    void pycore_video_dims(void* h, uint32_t* w, uint32_t* ht) {
        PyCore* pc = (PyCore*)h; *w = pc->vw; *ht = pc->vh;
    }
    void* pycore_video_ptr(void* h) { PyCore* pc = (PyCore*)h; return pc->video; }
    int pycore_load_save(void* h, const char* path) {
        PyCore* pc = (PyCore*)h;
        return mCoreLoadSaveFile(pc->core, path, 0);
    }
    void pycore_reset(void* h) { PyCore* pc = (PyCore*)h; pc->core->reset(pc->core); }
    """,
    include_dirs=[INCLUDE],
    library_dirs=[LIBDIR],
    libraries=["mgba"],
    extra_link_args=[f"-Wl,-rpath,{LIBDIR}"],
)

if __name__ == "__main__":
    ffi.compile(verbose=True)
    print("built game/_mgba_native")
