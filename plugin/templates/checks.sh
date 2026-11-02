#!/usr/bin/env bash
# Project checks for the software factory. Contract (plugin DESIGN.md · "Contrato de checks.sh"):
# - non-interactive; installs dependencies on a fresh worktree
# - runs lint, typecheck, tests and build
# - never rewrites tracked files (no --fix, no snapshot updates)
# - exits non-zero on any failure
# It runs with the job's worktree as the CURRENT WORKING DIRECTORY, and the gate always uses
# the copy on origin/<base_branch>, never the one on the job's branch.
set -euo pipefail

echo "factory/checks.sh is still the template written by factory-init." >&2
echo "Replace it with this project's lint, typecheck, tests and build." >&2
exit 1
