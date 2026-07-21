# SemixCRM README design

## Goal

Create a Russian-language root `README.md` that explains what SemixCRM is, how much of it is operational, how to run it locally, and which optional external components are required for live parsing.

## Audience

The primary audience is the repository owner and developers returning to the project later. The document must also give a new developer enough context to start the local application without reading the source first.

## Document structure

The README will contain:

1. A concise product description and a prominent local-MVP status note.
2. A module table that distinguishes persistent features from in-memory/demo UI.
3. A compact architecture diagram showing React/Vite, FastAPI, SQLite, freelance sources, Telegram, and the optional client parsers.
4. The technology stack and runtime prerequisites.
5. Windows-first installation and startup instructions, including frontend and backend URLs.
6. Environment-variable documentation, with secrets and generated data explicitly excluded from Git.
7. Separate explanations of the client parser and freelance sniper.
8. An exact description of the current 2GIS integration: SemixCRM expects a local adapter directory (`PARSER2GIC_ROOT`) and a copy of `interlark/parser-2gis` under the LeadHunt tree; these components are not bundled with the repository.
9. Data-storage, API, testing, directory-structure, limitations, and security sections.
10. Attribution to `interlark/parser-2gis` and its LGPL-3.0 license without implying that SemixCRM itself currently has a declared license.

## Accuracy rules

- Do not describe the Projects, Jobs, dashboard statistics, or Settings page as persisted production features.
- Do not imply that the client parser works from a clean clone: its local adapter dependencies must be called out.
- Do not claim CAPTCHA bypass, cloud operation, automatic freelance responses, or storage of marketplace passwords.
- Document the Vite runtime requirement from the lockfile: Node.js `^20.19.0` or `>=22.12.0`.
- State that Python 3.13 is the verified runtime, while keeping dependency installation tied to `backend/requirements.txt`.
- Explain that the backend is intended for localhost and has no user authentication.

## Verification

- Check all documented commands and paths against `package.json`, `.env.example`, `backend/requirements.txt`, and the source.
- Run the frontend production build.
- Run the backend unit test suite and disclose the missing external `parser2gic` path if it remains the only failure.
- Scan the finished README for placeholders, secrets, broken relative links, and claims that contradict the code.
