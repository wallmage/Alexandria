# Alexandria release-quality implementation plan

1. Add failing tests for evidence independence, date integrity, adversarial
   testing, coverage semantics, and section-level value review.
2. Add failing tests for accessible template tokens, PDF metadata/tagging/A4
   output, file permissions, and cover-image resolution.
3. Upgrade the schemas and validators, then update fixtures and documentation.
4. Upgrade PDF generation and validation without changing visual composition.
5. Upgrade vulnerable dependencies and add CI security plus all-template smoke
   coverage.
6. Run lint, unit, schema, compile, security, real PDF, visual, and installed-copy
   verification; then commit and push `main`.
