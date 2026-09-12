#!/bin/sh
# Bootstrap without requiring an existing Python or package manager.
set -eu
skill_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
runtime=${ALEXANDRIA_RUNTIME_DIR:-"$HOME/.alexandria/runtime"}
mkdir -p "$runtime"
exec 3>&1
exec >>"$runtime/install.log" 2>&1
case "$(uname -s)-$(uname -m)" in
  Darwin-arm64) target=osx-arm64; digest=500f5074feb8d02c4296ef9921c3650ed2874171805a9fbb8fbb53896433646b ;;
  Darwin-x86_64) target=osx-64; digest=0426ecdc41636d369f57b8fe6acbf4385a69eca45b56d9ee7d3a840a9965d44f ;;
  Linux-x86_64) target=linux-64; digest=8761c382127e6363bd9e0a2451aa3ef90d071a79133f736e2f759a3bf13040dd ;;
  *) echo 'Unsupported platform.' >&3; exit 1 ;;
esac
channels='https://conda.anaconda.org/conda-forge https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge'
if [ "${ALEXANDRIA_MIRROR_FIRST:-0}" = 1 ]; then
  channels='https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud/conda-forge https://conda.anaconda.org/conda-forge'
fi
mamba="$runtime/bin/micromamba"
if [ ! -x "$mamba" ]; then
  archive="$runtime/micromamba.tar.bz2"
  downloaded=0
  for channel in $channels; do
    if curl --fail --location --connect-timeout 15 --max-time 180 --proto '=https' --proto-redir '=https' \
      "$channel/$target/micromamba-2.9.0-0.tar.bz2" -o "$archive"; then
      if command -v shasum >/dev/null 2>&1; then actual=$(shasum -a 256 "$archive"); else actual=$(sha256sum "$archive"); fi
      if [ "${actual%% *}" = "$digest" ]; then downloaded=1; break; fi
    fi
  done
  [ "$downloaded" = 1 ] || { echo "Installation failed; see $runtime/install.log" >&3; exit 1; }
  tar -xjf "$archive" -C "$runtime" bin/micromamba
  rm "$archive"
fi
export MAMBA_ROOT_PREFIX="$runtime/mamba"
prefix="$runtime/env"
action=create
[ ! -f "$prefix/conda-meta/history" ] || action=install
installed=0
for channel in $channels; do
  if "$mamba" --no-rc "$action" --yes --prefix "$prefix" --override-channels --channel "$channel" python=3.12 pip pango fontconfig; then
    installed=1; break
  fi
done
[ "$installed" = 1 ] || { echo "Installation failed; see $runtime/install.log" >&3; exit 1; }
if "$mamba" --no-rc run --prefix "$prefix" python "$skill_root/scripts/install_runtime.py" --runtime "$runtime"; then
  echo "Installed and verified. Runtime: $skill_root/.runtime.json" >&3
else
  echo "Installation failed; see $runtime/install.log" >&3
  exit 1
fi
