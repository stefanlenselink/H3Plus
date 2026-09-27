[<< Index](Findings.md)

## 9. The App Region — SOLVED

> **SOLVED.** The app region is descrambled by the **SFC ENC hardware block**, not by the continuous LFSR stream used for UBOOT. The sections below are kept in order: first the answer, then the historical negative results (retained so the dead ends are not re-walked).

### 9.0 The solution

The `jielie` documentation for the **SFC** (SPI Flash Controller) peripheral describes the data path:

```
mem
||                                 _____                     ____________
||      ________       _____      |     | ---> CLK =======> | SPI flash  |
|| <== | icache | <== | ENC | <== | SFC | <--> DAT ========>|            |
||     |________|     |_____|     |_____|                   |____________|
```

Between the cache and the flash controller sits an **ENC** block that descrambles data on the fly. The critical sentence (from `periph/sfc.md`):

> *"Due to the cache line size, the data is scrambled in **32-byte blocks**, additionally the key used for scrambling is the actual key set up in the ENC/SFCENC **XORed with the absolute memory address shifted right by 2**, i.e. `key = key ^ (addr >> 2)`."*

That single line explains everything that was previously mysterious:

| Earlier observation | Explanation |
|---|---|
| Coincidence spikes at multiples of 32 only | Cache line size = 32 bytes; the cipher reseeds every line |
| Lag 16 flat at random baseline | Sub-line lags carry no structure — correct |
| Index of coincidence exactly random | The seed changes every 32 bytes, flattening all global statistics |
| Zero duplicate 32-byte blocks | Every line has a *different* key (address-dependent) |
| All continuous-LFSR phases failed | It was never a continuous stream |
| Chip key `0xF181` failed as a plain seed | It is the **ENC key**, but must be XORed with `addr >> 2` per line |

#### The algorithm

```python
POLY = 0x1021
LINE = 32

def sfc_enc_decrypt(data, base=0, chipkey=0xF181):
    out = bytearray(data)
    for off in range(0, len(data), LINE):
        k = (chipkey ^ ((base + off) >> 2)) & 0xFFFF   # reseed every cache line
        for i in range(off, min(off + LINE, len(data))):
            out[i] ^= k & 0xFF
            k = ((k << 1) ^ (POLY if k & 0x8000 else 0)) & 0xFFFF
    return bytes(out)
```

The LFSR itself is **identical** to the UBOOT one (poly `0x1021`, low byte as keystream). Only the seeding differs.

#### Parameters for the H3 Plus

| Parameter | Value | How determined |
|---|---|---|
| `chipkey` | **`0xF181`** | Read from hardware via `jl-uboot-tool` |
| App region start | `0x5000` | Region boundary from the UBOOT phase map |
| Address base | **`0`** (relative to app start) | Brute-forced; see below |

The SFC has a *"configurable base address offset"*, and it is programmed so the app begins at mapped address `0`. Confirmed by scanning all bases and counting zero bytes:

```
top bases by zero count: [(4646, '0x0'), (1450, '0x40'), (1396, '0x80'),
                          (1366, '0x20'), (1345, '0x100'), (1311, '0x200')]
```

`base = 0` wins by a factor of 3.2 — unambiguous.

#### Result

```
$ python tools/jl_sfcenc.py Dumps/dump_internal.bin work/app_dec.bin --start=0x5000 --end=0xC8FE0
in : 802784 bytes  entropy=7.9976 zeros=3023   ff=5428
out: 802784 bytes  entropy=6.9067 zeros=105074 ff=19566
key=0xF181 start=0x5000 base=0x0
```

| Metric | Before | After |
|---|---|---|
| Entropy | 7.9976 | **6.9067** |
| Zero bytes | 3,023 | **105,074** (35×) |
| `0xFF` bytes | 5,428 | **19,566** |
| ASCII strings (≥6 chars) | ~0 meaningful | **3,942** |

The residual entropy of 6.9 is expected — a large part of the image is **compressed audio** (voice prompts and tones under `storage/res_nor/C/tone/`), which is incompressible by nature.

#### Immediate confirmation

The first strings in the decrypted region are exactly the JieLi structures the bootloader referenced:

```
0x005010  app_area_head
0x005030  app.bin
0x005b28  fm_inside
```

`app_area_head` was a string in the **decrypted UBOOT** ([§8](06-decrypted-bootloader.md#8-decrypted-bootloader-contents)) — finding it at the head of the app region independently validates the decryption.

> **Note on the chip key's role:** `0xF181` is the **ENC/SFCENC key**, held in OTP. It is the same key the updater checks with `ERROR: Chip key does not match firmware key.` — the firmware is pre-scrambled at build time for one specific chip key, which is why images are not portable between devices with different keys.

---

### 9.1 Historical: baseline statistics (pre-solution)

```
app region 0x5000, 65536 bytes, entropy=7.9944, zeros=222
```

### 9.2 Historical: ciphers tested and rejected

| Cipher | Zeros after decrypt | Entropy after | Verdict |
|---|---|---|---|
| (baseline, untouched) | 222 | 7.9944 | — |
| JieLi ENC LFSR, **all 32767 phases** | 33–47 per 4K block | ~7.99 | ❌ reject |
| `CrcDecode` / "MengLi" | 233 | 7.9968 | ❌ reject |
| `RxGp` (RNG seed `0x70477852`) | 228 | 7.9971 | ❌ reject |
| Chip key `0xF181` as a plain LFSR seed | 274 | 7.9972 | ❌ reject |

All of these failed for the same reason: **they assumed a continuous keystream.** The cipher reseeds every 32 bytes.

### 9.3 Historical: the "period-32 red herring" — it was not a red herring

An initial XOR self-correlation showed spikes at multiples of 32, which was written off as an artifact of `0xFF` padding. Re-running with `0xFF`-dominated blocks excluded:

```
clean bytes: 758528
top lags: [(0.02953, 32), (0.0275, 64), (0.02626, 128), (0.02545, 256), ...]
lag 16 = 0.00393   (= random baseline)
overall IC: 0.003912   (= perfectly flat)
```

**Lesson learned:** the period-32 signal was the single most important clue in the entire analysis, and it was correctly measured twice but mis-attributed both times. The conclusion recorded at the time — *"32-byte block alignment in the underlying structure ... consistent with the hardware flash-decryption engine working in 32-byte granules"* — was **exactly right**. The mistake was not pursuing the SFC/ENC hardware documentation immediately.

> **Generalisable lesson:** when a statistical signal appears at a hardware-natural granularity (cache line, page, sector), look up the *hardware* documentation before trying more software ciphers.

---

*[<< Index](Findings.md)*
