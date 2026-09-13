from importlib.machinery import EXTENSION_SUFFIXES
from pathlib import Path


BUILD_DIR = Path(__file__).resolve().parent / "build" / "cxxsim"
MODULE_NAME = "coreblocks_cxxsim"
MODULE_PATH = BUILD_DIR / (MODULE_NAME + EXTENSION_SUFFIXES[0])
