# Contributing to CrackedPDFs

CrackedPDFs is a security benchmark. Changes must preserve provenance, paired evaluation, and narrow claim boundaries.

## Before opening a change

Open an issue before making a large change to the dataset schema, attack taxonomy, split logic, metric definitions, or paper-facing claims. Small fixes to documentation, tests, and reproducibility metadata can go straight to a pull request.

Do not commit:

- generated PDFs outside a reviewed example bundle;
- local databases, feature tables, model binaries, or logs;
- access tokens, `.env` files, machine credentials, or private paths not already present in a frozen provenance record; or
- results that cannot be traced to a command, configuration, split, and source commit.

## Development setup

The current end-to-end runner targets Windows PowerShell and Python 3.13.

```powershell
git clone https://github.com/volkthienpreecha/crackedpdfs.git
cd crackedpdfs
Copy-Item .env.example .env
npm run experiment:smoke
```

For focused Python generator tests:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .\tools\PDFautogenerator
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest .\tools\PDFautogenerator\tests
```

For TypeScript tests:

```powershell
npm install
npx --yes tsx --test `
  src/lib/prompt-injection-message-library.test.ts `
  src/backend/services/dataset-mode/index.test.ts `
  src/backend/services/processing/layers/02-watermarking/injection-config.contract.test.ts
```

## Pull request rules

A pull request should state:

1. what changed;
2. why the change is needed;
3. which benchmark claims or artifacts it can affect;
4. the exact validation commands run; and
5. whether any generated output changed.

If results change, include the old and new split identifiers, metrics, confusion matrices, paired-control results, shortcut audits, and the source commit used to create them.

Do not describe a balanced paired-set classification score as a ranking score. Keep metric names aligned with the artifact fields that produced them.

## Paper artifact changes

Files under `paper-v1/` are a frozen research record. Change them only to:

- correct a documented error;
- add missing provenance without altering the underlying result; or
- publish a clearly versioned replacement.

Never overwrite a frozen split or metric file in place and keep the same version label. Add a new versioned directory instead.

## Reporting security issues

Do not open a public issue for a vulnerability that exposes secrets, enables unsafe file processing, or affects users of the code. Email `volk_thienpreecha@berkeley.edu` with reproduction details and the affected commit.

## Conduct

By participating, you agree to follow [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
