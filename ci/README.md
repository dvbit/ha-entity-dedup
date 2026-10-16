# CI workflows

Copy both files into `.github/workflows/`:

```bash
mkdir -p .github/workflows
cp ci/*.yml .github/workflows/
git add .github/workflows && git commit -m "ci: enable workflows" && git push
```

- `validate.yml`: hassfest + HACS validation
- `tests.yml`: ruff, consistency check, pytest (Python 3.14, HA 2026.10.1)
