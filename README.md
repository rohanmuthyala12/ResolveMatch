# ResolveMatch

ResolveMatch is an evidence-backed engineering incident routing system that combines a React dashboard, a FastAPI backend, authenticated MCP tools, SQLite persistence, and human approval enforcement.

## Project structure

```text
.
├── README.md
├── .git/
├── .venv/
├── outputs/
│   ├── archive/
│   │   └── ResolveMatch-source.zip
│   └── ResolveMatch/
│       ├── backend/
│       ├── frontend/
│       ├── scripts/
│       ├── tests/
│       ├── .env.example
│       ├── README.md
│       ├── START_HERE.md
│       ├── SECURITY.md
│       ├── VALIDATION.md
│       ├── compose.yaml
│       ├── Dockerfile
│       ├── pyproject.toml
│       └── requirements.txt
├── work/
└── .DS_Store
```

## What is included

- React + TypeScript dashboard for manager and engineer workflows
- FastAPI API with approval-gated assignment logic
- SQLite-backed data storage with audit history
- Deterministic incident ranking based on evidence and workload
- TrueForge integration and MCP tool orchestration
- Test suite and operational scripts

## Main app location

The project implementation lives in [outputs/ResolveMatch](outputs/ResolveMatch).

For the detailed app documentation, start with:

- [outputs/ResolveMatch/README.md](outputs/ResolveMatch/README.md)
- [outputs/ResolveMatch/START_HERE.md](outputs/ResolveMatch/START_HERE.md)

## Quick start

1. Open the app folder: [outputs/ResolveMatch](outputs/ResolveMatch)
2. Review the setup instructions in [outputs/ResolveMatch/START_HERE.md](outputs/ResolveMatch/START_HERE.md)
3. Start the backend and frontend using the project scripts
4. Run the validation checks described in the project README

## Notes

- The original packaged zip file was moved into [outputs/archive/ResolveMatch-source.zip](outputs/archive/ResolveMatch-source.zip) so the working project remains clean and readable.
- The active project folder is named ResolveMatch instead of the older lowercase form.
