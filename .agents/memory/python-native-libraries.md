---
name: Python native libraries on Replit
description: Replit Nix dependencies needed when Python 3.13 native wheels cannot find shared libraries.
---

For this Replit Python 3.13 environment, native wheels such as NumPy may need both `libgcc` and `zlib` in the `.replit` Nix package list; adding only `gcc` or relying on the Python base runtime's separate library path was insufficient.

**Why:** The managed Python process resolves the Replit Nix library path separately, so NumPy can fail first on `libstdc++.so.6` and then on `libz.so.1` even when those libraries exist elsewhere in the base runtime.

**How to apply:** When plain `python` cannot import a native package, add the indexed Nix packages `libgcc` and `zlib` through the Replit dependency configuration, allow the environment to reload, then verify the exact user command and the complete test suite.