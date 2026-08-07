# Bundled Rewild profiles

Alexandria carries three complete Rewild profiles so its human-voice gate does not depend on another installed skill or repository:

- `rewild/` — English
- `rewild-zh/` — Simplified Chinese
- `rewild-hk/` — Traditional Chinese for Hong Kong

The files are vendored from [wallmage/rewild](https://github.com/wallmage/rewild) at commit `391ec24754dc5e5e62c56d2ebc3925a2bd266e9d` (2026-08-07). Each profile retains its operating guide, language-specific pattern catalog, and zero-dependency checker. The checker copies are intentionally identical; keeping each profile complete preserves its original relative paths and makes the package portable.

Alexandria keeps two report-specific checker extensions on top of that version:
English serial-enumeration detection and repeated short paragraph-closer detection.

The upstream profiles normally activate only when a user explicitly requests de-AI editing. Inside Alexandria, the root `SKILL.md` deliberately overrides that trigger condition: the appropriate profile is a mandatory production gate for every report. All other profile rules remain unchanged.

Rewild is MIT licensed. See `LICENSE` in this directory.

The `opencc/STCharacters.txt` character map is vendored from
[OpenCC](https://github.com/BYVoid/OpenCC) commit
`fd8e6bfe1a73ada14e9e654b7df27b51c49f6ba2`. Alexandria uses it only to
enforce Simplified-Chinese script consistency without a runtime dependency.
OpenCC is Apache-2.0 licensed; its license is in `opencc/LICENSE`.
