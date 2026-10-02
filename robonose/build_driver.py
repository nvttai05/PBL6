"""Compile only; does not load the library or open any device."""
from pathlib import Path
import subprocess

def main():
    root = Path(__file__).parent / "native"
    target = root / "librobonose_bme.so"
    subprocess.run(["cc", "-shared", "-fPIC", "-O2", "-Wall", "-Wextra", "-Werror",
                    str(root / "bridge.c"), str(root / "vendor/bme68x.c"),
                    "-o", str(target)], check=True)
    print(target)

if __name__ == "__main__":
    main()
