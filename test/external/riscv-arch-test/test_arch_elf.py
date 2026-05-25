import sys
from pathlib import Path

# Ensure repo root is on sys.path when executed directly from the external tree
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from test.regression.arch_elf import main  # noqa: E402


if __name__ == "__main__":
    main()
