# Suites

Each JSON file in this directory defines an independently versioned benchmark
suite. The filename is the short value accepted by `--suite`.

To create one safely:

```powershell
rebench suite copy hard20 my-suite
rebench suite validate my-suite
```

Run gold validation after editing tasks and before benchmarking agents.
