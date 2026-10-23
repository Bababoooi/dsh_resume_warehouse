# dsh-plugin-resume-warehouse

DSH host bundle for **Resume Warehouse** — a local-first app that turns your work into reusable
packages, imports an existing resume into a template, analyses a job description (including the
school-tier preference it implies), assembles a tailored Chinese/English resume and exports a PDF
named `position-name-school`.

This npm package is only the **shell**: it registers one tool so the agent can start, stop or
inspect the local app. The app itself is Python and ships in the same repository
(`server/`, `web/`, `skills/`).

## What gets added

| item | detail |
| --- | --- |
| tool | `resume_warehouse` with `action` ∈ `status` / `start` / `stop` / `open` |
| config | `repoPath` (default `$DSH_RESUME_WAREHOUSE_DIR`, then the current directory), `startTimeoutMs` (default 30000) |
| network | none on its own — it only talks to `127.0.0.1` |

## Privacy

Your files never leave the machine. The only outbound connection is the LLM call the app performs
after you confirm the exact field list it is about to send (name / phone / email / photo are never
included; the school name is, because it drives the school-tier judgement). The key stays in
`resume-warehouse/.env` with `600` permissions.

## Requirements

- DSH `>= 0.1.0`
- macOS or Linux with `bash`
- Python 3.11+ and the checkout this bundle points at

## Install

```
dsh plugin --profile <profile> add <this package>
```

then set `repoPath` to your checkout if it is not the current working directory.

## Usage

Ask the agent to “打开简历仓库” / “检查简历仓库是否在跑” — it calls `resume_warehouse`. `start`
waits for `data/runtime/app_port` and a `200` from `/api/v1/health`, then returns the URL.

## Development

```
npm test        # 13 contract tests, no network, no Python needed
```

The tests cover the manifest/marketplace requirements, the patch shape, locale metadata, the tool
definition contract, the `apply()` registration + disposer, and every action through injected
seams (spawn / bash / fetch are all replaceable, so nothing is launched).

## License

MIT
