#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <mach-o/dyld.h>
#include <limits.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>

static void strip_last_component(char *path) {
    char *last = strrchr(path, '/');
    if (last && last != path) {
        *last = '\0';
    }
}

static int get_project_dir(char *out, size_t out_size) {
    char exec_path[PATH_MAX];
    uint32_t size = sizeof(exec_path);
    if (_NSGetExecutablePath(exec_path, &size) != 0) {
        return -1;
    }

    char real[PATH_MAX];
    if (!realpath(exec_path, real)) {
        return -1;
    }

    /* .app/Contents/MacOS/WhisperMac → project_dir */
    strip_last_component(real); /* remove binary name  */
    strip_last_component(real); /* remove MacOS         */
    strip_last_component(real); /* remove Contents      */
    strip_last_component(real); /* remove WhisperMac.app */

    strncpy(out, real, out_size);
    out[out_size - 1] = '\0';
    return 0;
}

int main(int argc, char *argv[]) {
    char project_dir[PATH_MAX];
    if (get_project_dir(project_dir, sizeof(project_dir)) != 0) {
        fprintf(stderr, "WhisperMac: cannot determine project directory\n");
        return 1;
    }

    /* Point PYTHONPATH at the venv's site-packages */
    char venv_sp[PATH_MAX];
    snprintf(venv_sp, sizeof(venv_sp),
             "%s/venv/lib/python3.14/site-packages", project_dir);
    setenv("PYTHONPATH", venv_sp, 1);

    Py_Initialize();

    /* Make sure site-packages is in sys.path */
    char pysetup[PATH_MAX * 2];
    snprintf(pysetup, sizeof(pysetup),
        "import sys, os\n"
        "sp = '%s'\n"
        "if sp not in sys.path:\n"
        "    sys.path.insert(0, sp)\n"
        "os.chdir('%s')\n",
        venv_sp, project_dir);
    PyRun_SimpleString(pysetup);

    /* Run whisper_mac.py */
    char script[PATH_MAX];
    snprintf(script, sizeof(script), "%s/whisper_mac.py", project_dir);

    FILE *fp = fopen(script, "r");
    if (!fp) {
        fprintf(stderr, "WhisperMac: cannot open %s\n", script);
        Py_Finalize();
        return 1;
    }

    /* Set sys.argv so the script sees its own path */
    snprintf(pysetup, sizeof(pysetup),
        "import sys; sys.argv = ['%s']", script);
    PyRun_SimpleString(pysetup);

    int rc = PyRun_SimpleFile(fp, script);
    fclose(fp);
    Py_Finalize();
    return rc;
}
