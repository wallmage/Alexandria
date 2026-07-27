# Bundled Rewild profiles

Alexandria carries three complete Rewild profiles so its human-voice gate does not depend on another installed skill or repository:

- `rewild/` — English
- `rewild-zh/` — Simplified Chinese
- `rewild-hk/` — Traditional Chinese for Hong Kong

The files are vendored from [wallmage/rewild](https://github.com/wallmage/rewild) at commit `ae781ee48c7f1eb27047de433bc13048d0e6b766` (2026-07-28). Each profile retains its operating guide, language-specific pattern catalog, and zero-dependency checker. The checker copies are intentionally identical; keeping each profile complete preserves its original relative paths and makes the package portable.

The upstream profiles normally activate only when a user explicitly requests de-AI editing. Inside Alexandria, the root `SKILL.md` deliberately overrides that trigger condition: the appropriate profile is a mandatory production gate for every report. All other profile rules remain unchanged.

Rewild is MIT licensed. See `LICENSE` in this directory.

The `opencc/STCharacters.txt` character map is vendored from
[OpenCC](https://github.com/BYVoid/OpenCC) commit
`fd8e6bfe1a73ada14e9e654b7df27b51c49f6ba2`. Alexandria uses it only to
enforce Simplified-Chinese script consistency without a runtime dependency.
OpenCC is Apache-2.0 licensed; its license is in `opencc/LICENSE`.
