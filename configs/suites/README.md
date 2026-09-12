# Suites

Each JSON file in this directory defines an independently versioned benchmark
suite. The filename is the short value accepted by `--suite`.

Generate a new suite from reproducible filters with:

```powershell
rebench suite generate hard30 --count 30 --difficulty hard --seed 20260912
```

To create one safely:

```powershell
rebench suite copy hard20 my-suite
rebench suite validate my-suite
```

Run gold validation after editing tasks and before benchmarking agents.
