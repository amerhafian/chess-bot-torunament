#!/bin/sh
# Build the C++ search extension into backend/engine so Python can import it.
set -eu
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"
SUFFIX="$("$PY" -c "import sysconfig; print(sysconfig.get_config_var('EXT_SUFFIX'))")"
INCLUDE="$("$PY" -c "import sysconfig; print(sysconfig.get_path('include'))")"
PYBIND="$("$PY" -c "import pybind11, pathlib; print(pathlib.Path(pybind11.get_include()))")"
c++ -O3 -std=c++17 -shared -fPIC -undefined dynamic_lookup \
  -I "$INCLUDE" -I "$PYBIND" -I engine/cpp -I engine/cpp/third_party \
  engine/cpp/native.cpp -o "backend/engine/native${SUFFIX}"
echo "built backend/engine/native${SUFFIX}"
