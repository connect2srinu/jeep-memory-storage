# Domain memory contract template

Copy this directory to `config/contracts/<domain>` and replace every `replace_me` value.
All five files describe one domain onboarding request. Do not edit generated runtime JSON.

```bash
python scripts/validate_memory_contract.py
python scripts/compile_memory_contract.py
git diff -- app/shared_memory config/generated config/schemas
```
