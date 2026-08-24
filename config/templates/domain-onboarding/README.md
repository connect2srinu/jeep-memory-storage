# Domain Memory Contract Template

The Admin Console is the preferred interactive onboarding path. Use this template when the domain
requires pull-request review, bulk onboarding, or explicit schema-version governance.

Copy the directory to `config/contracts/<domain>` and complete the domain, preferences, resolution,
memory-profile, and consumer YAML files. Keep canonical attributes domain-prefixed and grant write
access only to the owning domain.

```bash
python scripts/validate_memory_contract.py --source config/contracts/<domain>
python scripts/compile_memory_contract.py --source config/contracts --output config/generated
python scripts/compile_memory_contract.py --source config/contracts --output config/generated --check
```

Generated artifacts are reviewed outputs; agents do not read these YAML files and do not receive
schema IDs. Runtime authorization and schema selection come from the activated control plane.
