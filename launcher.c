#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <mach-o/dyld.h>
#include <limits.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>

#ifndef WHISPERMAC_PROJECT_DIR
#define WHISPERMAC_PROJECT_DIR ""
#endif

#ifndef WHISPERMAC_PYTHON_VERSION
#define WHISPERMAC_PYTHON_VERSION ""
#endif

static void strip_last_component(char *path) {
    char *last = strrchr(path, '/');
    if (last && last != path) {
        *last = '\0';
    }
}

static int copy_realpath_or_raw(const char *path, char *out, size_t out_size) {
    char real[PATH_MAX];
    if (realpath(path, real)) {
        strncpy(out, real, out_size);
    } else {
        strncpy(out, path, out_size);
    }
    out[out_size - 1] = '\0';
    return 0;
}

static int file_exists(const char *path) {
    FILE *fp = fopen(path, "r");
    if (!fp) {
        return 0;
    }
    fclose(fp);
    return 1;
}

static int dir_contains_app(const char *dir) {
    char script[PATH_MAX];
    snprintf(script, sizeof(script), "%s/whisper_mac.py", dir);
    return file_exists(script);
}

static int get_executable_path(char *out, size_t out_size) {
    char exec_path[PATH_MAX];
    uint32_t size = sizeof(exec_path);
    if (_NSGetExecutablePath(exec_path, &size) != 0) {
        return -1;
    }

    char real[PATH_MAX];
    if (!realpath(exec_path, real)) {
        return -1;
    }

    strncpy(out, real, out_size);
    out[out_size - 1] = '\0';
    return 0;
}

static int get_project_dir(char *out, size_t out_size) {
    const char *env_dir = getenv("WHISPERMAC_PROJECT_DIR");
    if (env_dir && env_dir[0]) {
        return copy_realpath_or_raw(env_dir, out, out_size);
    }

    if (WHISPERMAC_PROJECT_DIR[0]) {
        return copy_realpath_or_raw(WHISPERMAC_PROJECT_DIR, out, out_size);
    }

    char path[PATH_MAX];
    if (get_executable_path(path, sizeof(path)) != 0) {
        return -1;
    }

    /* .app/Contents/MacOS/WhisperMac -> directory containing the app bundle. */
    strip_last_component(path); /* remove binary name  */
    strip_last_component(path); /* remove MacOS         */
    strip_last_component(path); /* remove Contents      */
    strip_last_component(path); /* remove WhisperMac.app */

    if (dir_contains_app(path)) {
        strncpy(out, path, out_size);
        out[out_size - 1] = '\0';
        return 0;
    }

    char parent[PATH_MAX];
    strncpy(parent, path, sizeof(parent));
    parent[sizeof(parent) - 1] = '\0';
    strip_last_component(parent);
    if (dir_contains_app(parent)) {
        strncpy(out, parent, out_size);
        out[out_size - 1] = '\0';
        return 0;
    }

    return -1;
}

static void setenv_default(const char *name, const char *value) {
    const char *existing = getenv(name);
    if (!existing || !existing[0]) {
        setenv(name, value, 1);
    }
}

static void prepend_env_path(const char *name, const char *path) {
    const char *existing = getenv(name);
    if (existing && existing[0]) {
        size_t needed = strlen(path) + 1 + strlen(existing) + 1;
        char *joined = malloc(needed);
        if (!joined) {
            return;
        }
        snprintf(joined, needed, "%s:%s", path, existing);
        setenv(name, joined, 1);
        free(joined);
    } else {
        setenv(name, path, 1);
    }
}

static int get_site_packages(char *out, size_t out_size, const char *project_dir) {
    if (!WHISPERMAC_PYTHON_VERSION[0]) {
        return -1;
    }
    snprintf(
        out,
        out_size,
        "%s/venv/lib/python%s/site-packages",
        project_dir,
        WHISPERMAC_PYTHON_VERSION
    );
    return dir_contains_app(project_dir) ? 0 : -1;
}

static void configure_environment(const char *project_dir, const char *site_packages) {
    char venv_dir[PATH_MAX];
    char venv_bin[PATH_MAX];
    snprintf(venv_dir, sizeof(venv_dir), "%s/venv", project_dir);
    snprintf(venv_bin, sizeof(venv_bin), "%s/venv/bin", project_dir);

    setenv("WHISPERMAC_PROJECT_DIR", project_dir, 1);
    setenv("VIRTUAL_ENV", venv_dir, 1);
    prepend_env_path("PATH", venv_bin);
    prepend_env_path("PYTHONPATH", site_packages);
    prepend_env_path("PYTHONPATH", project_dir);

    setenv_default("PYTHONUTF8", "1");
    setenv_default("PYTHONIOENCODING", "UTF-8");
    setenv_default("HF_HUB_DISABLE_TELEMETRY", "1");
    setenv_default("WHISPERMAC_STRICT_LOCAL", "auto");
    setenv_default("WHISPERMAC_SAVE_TRANSCRIPTS", "1");
    setenv_default("WHISPERMAC_SAVE_PERF_LOG", "1");
    setenv_default("WHISPERMAC_DOCK_MODE", "regular");
    setenv_default("WHISPERMAC_CHUNK_SEC", "5");
    setenv_default("WHISPERMAC_FINAL_PASS_MIN_SEC", "18");
    setenv_default("WHISPERMAC_FINAL_PASS_MAX_SEC", "3600");
    setenv_default("WHISPERMAC_USE_PNG_MIC_ICON", "1");
    setenv_default("WHISPERMAC_HOLD_KEY", "right_option");
}

static int run_python_snippet(const char *code) {
    int rc = PyRun_SimpleString(code);
    if (rc != 0) {
        fprintf(stderr, "WhisperMac: Python setup snippet failed\n");
    }
    return rc;
}

static int resolve_strict_local_mode(void) {
    const char *code =
        "import os\n"
        "raw = os.environ.get('WHISPERMAC_STRICT_LOCAL', 'auto').strip().lower()\n"
        "repo = os.environ.get('WHISPERMAC_MODEL_REPO', 'mlx-community/whisper-large-v3-mlx-4bit')\n"
        "truthy = {'1', 'true', 'yes', 'on'}\n"
        "def is_cached():\n"
        "    try:\n"
        "        from huggingface_hub import snapshot_download\n"
        "        snapshot_download(repo_id=repo, local_files_only=True)\n"
        "        return True\n"
        "    except Exception:\n"
        "        return False\n"
        "cached = None\n"
        "if raw == 'auto' or raw in truthy:\n"
        "    cached = is_cached()\n"
        "if raw == 'auto':\n"
        "    final = '1' if cached else '0'\n"
        "elif raw in truthy:\n"
        "    if cached:\n"
        "        final = '1'\n"
        "    else:\n"
        "        print('Предупреждение: запрошен strict local, но кэш модели не найден. Для первого запуска включаю online-режим.', flush=True)\n"
        "        final = '0'\n"
        "else:\n"
        "    final = '0'\n"
        "os.environ['WHISPERMAC_STRICT_LOCAL'] = final\n"
        "print(f'WhisperMac: strict_local={final} (запрошено: {raw})', flush=True)\n";

    return run_python_snippet(code);
}

static int report_python_error(const char *message) {
    if (PyErr_Occurred()) {
        PyErr_Print();
    }
    fprintf(stderr, "WhisperMac: %s\n", message);
    return -1;
}

static int prepend_sys_path(const char *path) {
    PyObject *sys_path = PySys_GetObject("path");
    if (!sys_path || !PyList_Check(sys_path)) {
        return report_python_error("sys.path is unavailable");
    }

    PyObject *py_path = PyUnicode_FromString(path);
    if (!py_path) {
        return report_python_error("cannot create sys.path entry");
    }

    int contains = PySequence_Contains(sys_path, py_path);
    if (contains < 0) {
        Py_DECREF(py_path);
        return report_python_error("cannot inspect sys.path");
    }

    if (contains == 0 && PyList_Insert(sys_path, 0, py_path) != 0) {
        Py_DECREF(py_path);
        return report_python_error("cannot update sys.path");
    }

    Py_DECREF(py_path);
    return 0;
}

static int configure_python_paths(const char *project_dir, const char *site_packages, const char *script) {
    if (prepend_sys_path(site_packages) != 0 || prepend_sys_path(project_dir) != 0) {
        return -1;
    }

    PyObject *os_module = PyImport_ImportModule("os");
    if (!os_module) {
        return report_python_error("cannot import os module");
    }

    PyObject *chdir_result = PyObject_CallMethod(os_module, "chdir", "s", project_dir);
    Py_DECREF(os_module);
    if (!chdir_result) {
        return report_python_error("cannot change working directory");
    }
    Py_DECREF(chdir_result);

    PyObject *argv = PyList_New(1);
    if (!argv) {
        return report_python_error("cannot create sys.argv");
    }

    PyObject *script_arg = PyUnicode_FromString(script);
    if (!script_arg) {
        Py_DECREF(argv);
        return report_python_error("cannot create sys.argv item");
    }
    PyList_SET_ITEM(argv, 0, script_arg);

    if (PySys_SetObject("argv", argv) != 0) {
        Py_DECREF(argv);
        return report_python_error("cannot set sys.argv");
    }

    Py_DECREF(argv);
    return 0;
}

static int set_sys_argv_from_args(int argc, char *argv[]) {
    PyObject *py_argv = PyList_New(argc);
    if (!py_argv) {
        return report_python_error("cannot create sys.argv");
    }

    for (int i = 0; i < argc; i++) {
        PyObject *item = PyUnicode_FromString(argv[i]);
        if (!item) {
            Py_DECREF(py_argv);
            return report_python_error("cannot create sys.argv item");
        }
        PyList_SET_ITEM(py_argv, i, item);
    }

    if (PySys_SetObject("argv", py_argv) != 0) {
        Py_DECREF(py_argv);
        return report_python_error("cannot set sys.argv");
    }

    Py_DECREF(py_argv);
    return 0;
}

int main(int argc, char *argv[]) {
    char project_dir[PATH_MAX];
    if (get_project_dir(project_dir, sizeof(project_dir)) != 0) {
        fprintf(stderr, "WhisperMac: cannot determine project directory\n");
        return 1;
    }

    char venv_sp[PATH_MAX];
    if (get_site_packages(venv_sp, sizeof(venv_sp), project_dir) != 0) {
        fprintf(stderr, "WhisperMac: cannot determine Python site-packages\n");
        return 1;
    }

    char script[PATH_MAX];
    snprintf(script, sizeof(script), "%s/whisper_mac.py", project_dir);
    if (!file_exists(script)) {
        fprintf(stderr, "WhisperMac: cannot open %s\n", script);
        return 1;
    }

    configure_environment(project_dir, venv_sp);
    Py_Initialize();

    if (configure_python_paths(project_dir, venv_sp, script) != 0) {
        Py_Finalize();
        return 1;
    }

    if (argc > 1 && strcmp(argv[1], "-c") == 0) {
        if (argc < 3) {
            fprintf(stderr, "WhisperMac: -c requires Python code\n");
            Py_Finalize();
            return 1;
        }
        if (set_sys_argv_from_args(argc - 1, argv + 1) != 0) {
            Py_Finalize();
            return 1;
        }
        int rc = PyRun_SimpleString(argv[2]);
        Py_Finalize();
        return rc == 0 ? 0 : 1;
    }

    if (resolve_strict_local_mode() != 0) {
        Py_Finalize();
        return 1;
    }

    if (argc > 1 && strcmp(argv[1], "--check") == 0) {
        int rc = run_python_snippet(
            "import tkinter, mlx_whisper, pynput, Quartz, AppKit, sounddevice, numpy\n"
            "print('WhisperMac launcher check: ok', flush=True)\n"
        );
        Py_Finalize();
        return rc == 0 ? 0 : 1;
    }

    FILE *fp = fopen(script, "r");
    if (!fp) {
        fprintf(stderr, "WhisperMac: cannot open %s\n", script);
        Py_Finalize();
        return 1;
    }

    int rc = PyRun_SimpleFile(fp, script);
    fclose(fp);
    Py_Finalize();
    return rc;
}
