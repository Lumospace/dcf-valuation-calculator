"""生成演示用样本数据库。

用法：python scripts/build_sample_db.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dcf.sample_data import generate_sample_db

DEFAULT_DB = ROOT / "data" / "sample_financials.db"


def main() -> None:
    path = generate_sample_db(DEFAULT_DB)
    print(f"sample database generated: {path}")


if __name__ == "__main__":
    main()
