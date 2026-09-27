[<< Index](Findings.md)

## 6. The Encryption — JieLi "ENC" LFSR Cipher

### 6.1 The algorithm

A 16-bit Galois-style LFSR with polynomial `0x1021` (the CCITT CRC-16 polynomial). The **low byte** of each state is XORed into the plaintext, and the register steps once per byte:

```python
def jl_enc_cipher(buff, off, size, key=0xFFFF):
    """JieLi 'ENC' stream cipher. Symmetric — same function encrypts and decrypts."""
    for i in range(size):
        buff[off + i] ^= key & 0xFF
        key = ((key << 1) ^ (0x1021 if key & 0x8000 else 0)) & 0xFFFF
```

### 6.2 Properties

| Property | Value |
|---|---|
| State size | 16 bits |
| Polynomial | `0x1021` |
| Default seed | `0xFFFF` |
| **Cycle length from `0xFFFF`** | **32767** (= 2¹⁵ − 1) |
| Keystream | low byte of each state, applied continuously |
| Keyspace | 65536 (trivially brute-forceable) |

**Critical correction recorded here to save future time:** the keystream is **NOT** a 32-byte repeating table. That hypothesis was explicitly tested (`tools/jl_recover_key.py`) and **disproved** — per-phase mode confidence came out at avg 0.007, i.e. pure noise. The apparent "period 32" correlation in the initial entropy scan was an **artifact of the 363 all-`0xFF` blocks**, which match at *every* period.

### 6.3 The recurrence that identified it

The decisive manual insight. Because the register shifts left by one each step, consecutive keystream bytes obey:

```
b[i+1] == ((b[i] << 1) & 0xFF) ^ (0x21 if <carry> else 0x00)
```

So each keystream byte has only **two possible successors**. Verifying this recurrence held across long runs of repeated 16-byte blocks in the ciphertext confirmed the cipher immediately. (The repeated blocks were raw keystream exposed by runs of `0x00` plaintext.)

**Caveat:** because there are only 2 successors, an 8-byte window match is strong but not conclusive. Contiguous-run consistency is the reliable filter — see [§7](#7-key-recovery-methodology).

### 6.4 Related JieLi primitives (for reference)

From `kagaimiq/jl-uboot-tool`:

```python
jl_crc16 = crcmod.mkCrcFun(0x11021,     initCrc=0x0000,     rev=False)
jl_crc32 = crcmod.mkCrcFun(0x104C11DB7, initCrc=0x26536734, rev=True)
```

- `jl_rxgp_cipher` — uses an RNG seeded with `0x70477852`.
- `jl_crc_cipher` — the "MengLi" crypt, keyed with the GB2312 string `孟黎我爱你，玉林`.

Both were tested against the app region and **both failed** (see [§9](07-app-region-solved.md#9-the-app-region--solved)).

---

## 7. Key Recovery Methodology

Documented because it generalises to any other JieLi image.

### 7.1 Step 1 — Detect encryption

`tools/analyze.py` computes Shannon entropy, index of coincidence, byte histogram, per-4K-block entropy, XOR-period correlation, and duplicate-16-byte-block counts.

Result: entropy **7.99**, flat histogram → encrypted or compressed.

### 7.2 Step 2 — Find exposed keystream

Look for **repeated non-`0xFF` 16-byte blocks**. In a stream cipher these occur where the plaintext is a run of `0x00` — the ciphertext *is* the raw keystream there. This is the crack.

### 7.3 Step 3 — Build the full cycle and index it

```python
POLY = 0x1021

def step(k):
    return ((k << 1) ^ (POLY if k & 0x8000 else 0)) & 0xFFFF

def build_cycle(seed=0xFFFF):
    states, seen, k = [], {}, seed
    while k not in seen:
        seen[k] = len(states)
        states.append(k)
        k = step(k)
    return states, bytes(s & 0xFF for s in states)   # P = 32767
```

### 7.4 Step 4 — Window matching and run grouping (`tools/jl_map.py`)

Index every 8-byte window of the 32767-byte keystream cycle into a dict. Slide over the file; every match yields a candidate phase `(cycle_index − file_offset) mod P`. Group *contiguous* runs of consistent candidates — this filters the false positives inherent to the 2-successor property.

**This is the step that found delta = 32591.**

### 7.5 Step 5 — Per-block phase map (`tools/jl_phasemap.py`)

A numpy histogram-vote solver. For each byte value `v` at file index `i`, every phase `(index_of_v − i) mod P` receives a vote. The argmax is the block's phase. Fast enough to test all 32767 phases per block.

> Pure-Python brute force (65536 × 12 files × 8192 bytes) was written as `tools/jl_bruteforce.py` but was far too slow. The numpy approach replaced it. Requires numpy (2.5.3 installed).

### 7.6 Results

`python tools\jl_phasemap.py "BIN\TID-H3-PlusV1.0.45.bin" 0x1000`

| Offset range | Delta (phase) | Zeros in decrypted block |
|---|---|---|
| `0x0000`–`0x4000` | **32591** (consistent) | 180–430 ✅ |
| `0x5000`+ | varies randomly | 33–47 ❌ (noise — expect ~16 for random) |

`python tools\jl_phasemap.py "FW\TID-H3-PlusV1.0.45.fw" 0x1000`

| Offset range | Delta (phase) | Zeros |
|---|---|---|
| `0x0000`–`0x4000` | **31567** (consistent) | 201–344 ✅ |
| `0x5000`+ | varies randomly | 34–47 ❌ |

**Final recovered values:**

| File | Phase @ offset 0 | LFSR state | Valid range |
|---|---|---|---|
| `BIN/TID-H3-PlusV1.0.45.bin` | **32591** | `0x0AB8` | `0x0000–0x4FFF` |
| `FW/TID-H3-PlusV1.0.45.fw` | **31567** | `0x2F2A` | `0x0000–0x4FFF` |

---

*[<< Index](Findings.md)*
