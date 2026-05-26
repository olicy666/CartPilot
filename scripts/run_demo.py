from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.agents.workflow import CommerceAgent


DEFAULT_QUERY = "预算2000以内，通勤和办公室用，想买降噪耳机，不要入耳式，戴久不要太累"


def main() -> None:
    query = " ".join(sys.argv[1:]).strip() or DEFAULT_QUERY
    agent = CommerceAgent()
    response = agent.run(query=query)
    print(json.dumps(response.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
