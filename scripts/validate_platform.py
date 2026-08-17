from __future__ import annotations

import asyncio
import json

from app.shared_memory.demo import build_final_validation_context


async def main() -> None:
    context = await build_final_validation_context()
    expected = {
        "preferred_store": ("Store-084", "customer"),
        "preferred_product_type": ("organic", "grocery"),
        "preferred_window": ("6PM-8PM", "delivery"),
        "banana_ripeness": ("slightly_green", "grocery"),
        "allow_substitutions": (True, "grocery"),
    }
    for key, (value, owner_domain) in expected.items():
        selected = context.preferences[key].preference
        if selected.value != value or selected.owner_domain != owner_domain:
            raise SystemExit(
                f"validation failed for {key}: {selected.value!r}/{selected.owner_domain}"
            )
    print(json.dumps(context.to_dict(), indent=2, default=str))
    print("\nShared Memory Platform final scenario: PASS")


if __name__ == "__main__":
    asyncio.run(main())

