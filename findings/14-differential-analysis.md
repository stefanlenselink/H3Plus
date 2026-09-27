[<< Index](Findings.md)

## 10. Differential Analysis Across Versions

XOR of `TID-H3-PlusV1.0.44.bin` against `TID-H3-PlusV1.0.45.bin` (both 782,336 bytes, identical size):

```
XOR zeros: 451,446 / 782,336 = 57.70%
longest zero run: 22,863 bytes at offset 0x37CA9
```

### Why this is the most important practical result

If the cipher used any chaining (CBC/CTR with a nonce), a single differing byte early in the image would randomise everything after it. Instead, **57.7% of bytes are identical and there is a contiguous 22 KB identical stretch**.

**Therefore the encryption is position-deterministic:**

```
C[i] = E(P[i], i)     — depends only on plaintext and offset
```

No chaining. No nonce. No IV.

**Consequences:**
- A byte patched at offset `i` affects **only** offset `i` in the ciphertext.
- Version-to-version diffing localises features precisely — the 42.3% differing bytes are the actual v44→v45 changes.
- **Targeted binary patching is feasible without ever recovering the key**, provided you can find the right offsets (e.g. by diffing a GMRS image against a HAM image) and fix up the CRCs.

### Suggested follow-up diffs

- v1.0.41 (0xE3000) vs v1.0.42 (0xBD000) — explains the 152 KB size drop.
- The two `1.0.42` files (`.42.bin` vs `.42(1).bin`) — same size; are they byte-identical, or is one a regional variant? **If they differ, that diff is gold** for locating region-lock data.
- GMRS vs HAM `td` codeplug templates.

---

*[<< Index](Findings.md)*
