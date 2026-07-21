# Root README Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a truthful Russian root README that explains SemixCRM and provides verified local setup and development instructions.

**Architecture:** This is a documentation-only change. The README derives product behavior from the React pages, FastAPI routes, SQLite schema, environment example, package manifests, tests, and the inspected upstream `interlark/parser-2gis` repository.

**Tech Stack:** Markdown, React 19/Vite 8/TypeScript frontend, FastAPI/Python backend, SQLite, Playwright, `interlark/parser-2gis`

## Global Constraints

- Write the document in Russian.
- Distinguish persistent modules from in-memory or placeholder UI.
- Document Node.js `^20.19.0` or `>=22.12.0` and Python 3.13 as the verified Python runtime.
- Treat the client parsers as optional local integrations that are not bundled with SemixCRM.
- Do not expose secrets, claim CAPTCHA bypass, or imply that the unauthenticated backend is safe for public deployment.

---

### Task 1: Create the root product and setup documentation

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: commands from `package.json`, variables from `.env.example` and backend source, routes from `backend/main.py`, paths from `backend/parser.py`, and module behavior from `src/pages/`.
- Produces: the repository entry-point documentation for users and developers.

- [x] **Step 1: Write the README**

Create `README.md` with these exact sections: overview, project status, module matrix, architecture, technology stack, requirements, quick start, environment variables, data storage, client parser, freelance sniper, API, scripts, testing, directory structure, known limitations, security, and attribution.

- [x] **Step 2: Check every command and path against source**

Run:

```powershell
Select-String -Path README.md -Pattern 'npm run dev|npm run build|backend\\.venv|PARSER2GIC_ROOT|LEADHUNT_ROOT|interlark/parser-2gis'
```

Expected: all setup commands and parser-integration identifiers appear with explanations.

- [x] **Step 3: Commit the documentation**

```powershell
git add README.md docs/superpowers/plans/2026-07-21-root-readme.md
git commit -m "docs: add project readme"
```

### Task 2: Verify the documentation against the project

**Files:**
- Verify: `README.md`

**Interfaces:**
- Consumes: the completed README and current repository checkout.
- Produces: build/test evidence and a clean documentation handoff.

- [x] **Step 1: Build the frontend**

Run:

```powershell
npm run build
```

Expected: TypeScript and Vite finish successfully and write `dist/`.

- [x] **Step 2: Run backend tests**

Run:

```powershell
backend\.venv\Scripts\python.exe -m unittest discover -s backend\tests -v
```

Expected in a fully configured environment: 39 tests pass. In this checkout, disclose the single `parser2gic/parse_runner.py` path failure if the external adapter has not been installed.

- [x] **Step 3: Scan documentation and Git state**

Run:

```powershell
Select-String -Path README.md -Pattern 'TBD|TODO|PLACEHOLDER|TELEGRAM_BOT_TOKEN=.+'
git status --short
```

Expected: no placeholders or embedded Telegram token; only intentional documentation changes before commit, then a clean worktree.
