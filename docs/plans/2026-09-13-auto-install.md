# Automatic installation

Goal: a novice gives an agent a ZIP or repository URL and asks to install.
The agent copies the skill to its own supported discovery directory, runs the
platform bootstrap, verifies PDF output, and reports completion without
asking dependency questions. Host-mandated approval cannot be bypassed.

- Add macOS/Linux shell and Windows PowerShell bootstrap scripts. Download a
  checksum-pinned micromamba from conda-forge with a Tsinghua mirror fallback.
  Create an isolated user-owned Python/Pango environment; never change global
  Python, shell profiles, security policy, or user package-manager settings.
- Add shared setup/verification: install pinned requirements with PyPI/Tsinghua
  fallback, install licensed Chinese fonts with verified downloads, generate
  English and both Chinese PDFs, reopen and rasterize, then save runtime paths.
- Route ZIP and GitHub installations through INSTALL.md; reuse the environment
  for reports and repair it automatically when needed. Keep technical logs
  internal. Existing unrelated/customized skill files must not be overwritten.
- Add download-integrity regression tests and real macOS/Windows installation
  smoke jobs. Run existing tests and a clean local install before merging.
- Merge, push, sync installed skill, and rebuild the desktop ZIP under 10 MB,
  excluding downloaded runtimes, fonts, logs, tests, and development files.
