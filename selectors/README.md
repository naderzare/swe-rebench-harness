# Custom selectors

Create a selector template with:

```powershell
rebench selector create my_algorithm
```

This creates `selectors/my_algorithm.py`. Edit its `select_tasks` function and
use it when generating a suite:

```powershell
rebench suite generate experimental30 `
  --count 30 `
  --difficulty hard `
  --languages python go java js ts rust `
  --unique-repositories `
  --seed 20260912 `
  --selector selectors/my_algorithm.py
```

The function receives candidates after the common filters are applied. It must
return exactly the requested number of candidate dictionaries. Rebench then
checks that all returned tasks came from the filtered pool and that requested
repository and language constraints were respected.

Selectors are ordinary versioned Python files, so an experiment can record and
share its exact selection algorithm.

Custom selectors execute as local Python code. Only run files you trust and
have reviewed.
