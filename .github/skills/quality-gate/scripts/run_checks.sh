#!/usr/bin/env bash
# Run the PortfolioUtils quality targets one by one and print a compact summary.
# Usage: run_checks.sh [all|check_format|check_lint|mypy|tests|licensecheck|docs ...]
set -u

if [[ $# -eq 0 || "$1" == "all" ]]; then
  targets=(check_format check_lint mypy licensecheck tests)
else
  targets=("$@")
fi

declare -A status
failed=0
for target in "${targets[@]}"; do
  echo "================ make ${target} ================"
  if make --no-print-directory "${target}"; then
    status[$target]="PASS"
  else
    status[$target]="FAIL"
    failed=1
  fi
done

echo
echo "================ SUMMARY ================"
for target in "${targets[@]}"; do
  printf '%-14s %s\n' "${target}" "${status[$target]}"
done
exit "${failed}"
