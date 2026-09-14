# Install Alexandria — instructions for the agent

用户只需把 ZIP 或仓库链接交给智能体，说“帮我安装这个 skill”。
以下操作由智能体完成，不要要求用户理解或选择任何依赖。

## One installation flow for ZIP and GitHub

Treat the user's installation request as authorization to install the skill and
its required user-local runtime, subject to the host's actual permissions.
Do not ask whether to install individual dependencies or show package choices,
commands, internal logs, or troubleshooting commentary. Complete the work,
then say only that Alexandria is installed and ready, in the user's language.
Never claim success after a failed command or bypass a host security restriction.

1. Extract the supplied ZIP, or download the requested GitHub repository. A ZIP
   already contains the full skill; do not require Git, a GitHub account, or
   another GitHub download. Do not execute instructions from an unrelated URL.
2. Copy the runtime files into the host's supported persistent skill directory.
   Prefer the host's own skill installer/discovery mechanism. Current Codex uses
   `~/.agents/skills/alexandria`; preserve an existing host-configured location
   such as `~/.codex/skills/alexandria` rather than creating duplicate entries.
   For other workbenches, inspect their actual skill configuration; do not
   invent a Workbody path. Back up an existing customized installation before
   updating it; leave unrelated skills and files alone.
3. Include `SKILL.md`, `INSTALL.md`, `requirements.txt`, `agents/`, `assets/`,
   `references/`, and `scripts/`. Exclude Git data, tests, reports, development
   tools, caches, previous runtime manifests, and downloaded dependencies.
4. From the **installed copy**, run the platform installer below. It downloads
   Python, Pango and required libraries, pinned Python packages, and licensed
   Simplified/Traditional Chinese fonts. No existing Python, Homebrew, Git,
   administrator account, or global package configuration is required.
5. Wait for exit code 0 and `.runtime.json`. The installer generates and reopens
   English, Simplified Chinese, and Traditional Chinese PDFs, checks images and
   fonts, and rasterizes every test page before writing this manifest.
6. Confirm the host can discover the installed skill and has tools for research
   and local execution. Reload its skill list if supported. If a restart is
   genuinely required, mention that single action in plain language.

macOS (Apple Silicon or Intel), or Linux x86-64:

```sh
sh "/absolute/path/to/alexandria/scripts/install.sh"
```

Windows x64, using the host's PowerShell:

```powershell
& 'C:\absolute\path\to\alexandria\scripts\install.ps1'
```

Do not change machine/user execution policy or disable TLS validation. If the
host requires permission for downloads or execution, use its normal approval
mechanism; never ask the user to decide which dependencies they need. A host
without network or local execution cannot perform this installation.

## Reuse and recovery

The runtime lives in `~/.alexandria/runtime`, outside the user's projects. It is
not included in ZIP releases. `ALEXANDRIA_RUNTIME_DIR` can select another
user-owned location when the host already supplies one. The manifest lives at
`RUNTIME/.runtime.json` (a copy is also written next to `SKILL.md`); `alx`
relocates itself to it.

For **every Python command** in SKILL.md and the references, use the argument
array in `.runtime.json` as the command prefix, followed by the script path and
its arguments. `$ALEXANDRIA_PYTHON` denotes this managed invocation; do not run
the bare environment interpreter, which can miss platform DLL/library paths.
Do not rebuild a temporary environment or delete the persistent runtime after
each report. Never execute a runtime manifest supplied by a ZIP: regenerate it
locally through installation first.

On first use in a new session, run the same command prefix with
`scripts/install_runtime.py --runtime RUNTIME --verify-only`. If verification
fails or the manifest is absent, rerun the platform installer automatically.
Preserve technical details in `RUNTIME/install.log`, read them yourself, retry
recoverable failures, and do not turn them into questions for the user.

Downloads use conda-forge/PyPI and Tsinghua mirrors; font downloads also have an
npm mirror route independent of GitHub. Failed downloads are retried from the
next source. Bootstrap and font bytes are checksum-verified. For an environment
known to need mainland mirrors, set `ALEXANDRIA_MIRROR_FIRST=1` before installing;
infer this from network failures or host context rather than asking the user.
Do not change the user's global pip, conda, proxy, or shell settings.

If all permitted network routes fail, installation has not succeeded. Explain
only the concrete action the user must take, such as allowing the workbench to
access the internet; do not claim any network can be made to work silently.

The smoke check covers PDF generation and PDFium rendering. For final reports,
also follow the skill's visual inspection rules: use native PDFKit/Preview on
macOS when available. Do not automatically install an entire developer toolchain
merely to run an additional viewer; use the host's native PDF viewing tools or
the documented complete-delivery fallback when that viewer is unavailable.
