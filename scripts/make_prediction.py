from pathlib import Path
import json

task = "aws-cloudformation__cfn-lint-3965"

patch = Path(
    f"tasks/{task}/agent.patch"
).read_text(encoding="utf-8")

prediction = [
    {
        "instance_id": task,
        "patch": patch,
    }
]

Path(
    f"tasks/{task}/agent_prediction.json"
).write_text(
    json.dumps(prediction, indent=2),
    encoding="utf-8"
)

print("Created agent_prediction.json")