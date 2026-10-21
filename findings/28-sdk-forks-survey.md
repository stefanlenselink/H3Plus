# Ch. 28 — SDK-Forks Survey: the `fw-AC63_BT_SDK` fork network, and a **proven Linux build for br23**

> Survey run 2026-10-20 late (data persisted to `work/fork_survey/` + `work/sdk-forks/`).
> Motivation: [ch. 27 §27.19](27-firmware-2slot-stack-controller-wall.md) closed the NOP
> era — two-SPP requires **rewriting** the SPP session layer, and the SDK-rebuild route
> (open item 4 since ch. 24) became a leading candidate. Question: has anyone published a
> multipoint-capable or otherwise useful build of the JieLi BT stack, and is the br23
> build actually feasible outside JieLi's Windows toolchain?

---

## §28.1 — Method

- GitHub fork network of **`Jieli-Tech/fw-AC63_BT_SDK`** enumerated via the REST API
  (metadata: [`work/fork_survey/fork_api.json`](../work/fork_survey/fork_api.json)).
  Quirk: the API reports `parent: hhy-ccj/fw-AC630N_BT_SDK` for every fork — a
  fork-network artifact; the true upstream is `Jieli-Tech` (per the README badges).
  `JieLi-IC/fw-AC63_BT_SDK` returns **404** (renamed/deleted vendor mirror).
- 12 forks shallow-cloned to `work/sdk-forks/` (~814 MiB, gitignored) + the official
  tree at commit `fdc018d` (3,319 blobs; 37 `.a` libs under `cpu/br23/liba/`).
- Full `git ls-tree -r --long` listings for all 13 trees saved under
  `work/fork_survey/trees/`; comparison = blob-SHA set diff per fork vs official.

## §28.2 — Fork-by-fork verdicts

| Fork (owner) | Last push | Blobs | +add / −del / ~mod vs official | `cpu/br23/` | Verdict |
|---|---|---|---|---|---|
| **Acy19888** | 2026-04-04 | 3345 | +26 / 0 / 8 | 283 | **The prize**: `zuupah_pen` product app on **br23** + **green Linux CI build** (§28.4) |
| SunnyKlara | 2026-04-22 | 3347 | +30 / 2 / 9 | 273 | bd19 HID GPS-keyboard app — wrong chip (bd19), irrelevant |
| iot-eco-system | 2026-04-13 | 3326 | +7 / 0 / 7 | 274 | `spp_and_le` `serialble` example + bd19 download tooling — minor |
| stevemao | 2026-03-14 | 3321 | +2 / 0 / 0 | 274 | Mirror + `ai_earbuds` BLE example |
| Glebka | 2025-05-03 | 3319 | 0 / 0 / 3 | 274 | Mirror (three bd19/app config edits) |
| lingyi1105 | 2024-11-18 | 3100 | +8 / 227 / 286 | 269 | Older SDK **base** (version drift, not authoring) |
| Urbanmovez | 2023-08-23 | 2986 | +31 / 364 / 526 | 263 | Older base |
| mikewen | 2022-12-03 | 3023 | +77 / 373 / 525 | 263 | Older base |
| ACCount12 | 2022-10-20 | 2832 | +100 / 587 / 647 | 261 | Older base |
| Yennoccm | 2022-07-25 | 2833 | +103 / 589 / 650 | 261 | Older base |
| ruidian | 2022-05-18 | 2661 | +97 / 755 / 650 | 261 | Older base |
| hhy-ccj (`fw-AC630N_BT_SDK`) | — | 562 | (different product) | **0** | AC630N SDK — q32s/bd29 cores, wrong core for us (ch. 24 §24.1) |

## §28.3 — The BT libraries: nobody touched them

Blob-SHA comparison of the multipoint-critical br23 libraries across all forks:

- `cpu/br23/liba/btstack.a` = `808bffb8bf`, `btctrler.a` = `be3e6be8f0`,
  `rcsp_stack.a` = `9916656fa8` — **byte-identical to official in every recent fork**
  (Acy19888, Glebka, SunnyKlara, iot-eco-system, stevemao).
- The 2022–2024 forks carry *different* SHAs — **older SDK versions**, not rebuilds
  (their whole trees drift by 500–750 files).
- Path grep across all 13 trees for `multi_bd|1t2|dual_conn|multipoint|two_dev`:
  **zero code hits anywhere.** The only 1拖2 artifact in the entire network is
  `doc/stuff/AC690x_1T2测试盒使用说明书.pdf` in the 2022-era forks — an AC690x
  1-to-2 *test-box* manual (different chip, docs only).

**Verdict: no published fork solves multipoint, widens the pools, or ships stack
source.** Every public artifact links the same prebuilt vendor libraries we already have.

## §28.4 — Acy19888 deep-dive: an externally-proven br23 Linux build

The one fork with real engineering value. A German "Zuupah Lernstift" product
(AC6956C8 — **br23 family, same as our AC635N**; BLE + SPP + MP3 on 8 GB flash) built
from `spp_and_le` with a **GitHub Actions Linux pipeline that is green**: 5/5
`completed success` runs on 2026-04-04 (Actions API, workflow `build-zuupah.yml`).

Key facts extracted (all verified in the clone `work/sdk-forks/Acy19888_fw-AC63_BT_SDK/`):

1. **Official JieLi Linux toolchain** downloads from
   `https://pkgman.jieliapp.com/s/linux-toolchain` → currently
   `jieli-linux-toolchains-20260730.1.tar.xz` (302 redirect **verified live
   2026-10-21**). Two layouts exist — old: everything in `/opt/jieli/pi32v2/bin`;
   new: LLVM frontend in `/opt/jieli/common/bin`, target tools in
   `/opt/jieli/pi32v2/bin`.
2. **Build recipe**: `cd apps/zuupah_pen/board/br23 && ulimit -n 8096 && make` →
   `cpu/br23/tools/sdk.elf` + `app.bin`. The board config they modified is
   **`apps/spp_and_le/board/br23/board_ac635n_demo_cfg.h`** — the AC635N demo board,
   i.e. our exact chip.
3. **CI gotchas they solved** (all reusable): `lto-wrapper` invokes bare `ld`/`nm`/
   `strip` → symlink `common/bin → pi32v2/bin`; `download.sh` post-script externals
   (`host-client`, `strip-ini`, `lz4_packet`) stubbed out; `llvm-size` fallback via
   apt `llvm-14`.
4. **The SDK libraries are LLVM IR bitcode**: `ar p cpu/br23/liba/btstack.a
   btstack_task.c.o | file -` → `LLVM IR bitcode` (same for `btctrler.a`; members
   `tws_host.c.o`, `hci_vendor.c.o`, `btstack_memory.c.o`, …). This confirms ch. 22
   §9B.10's bitcode observation and means **LTO links the IR — the libraries are
   patchable at the IR level before link**.
5. **IR-surgery precedent**: their `.github/scripts/patch_bitcode.py` edits
   `power_hw.ll` (adds `section ".volatile_ram_code"` to `delay_nus` to fix an
   LTO-promotion relocation bug) — a working, minimal example of modify-IR-then-relink.
6. They also touched `cpu/br23/sdk_ld.c`, `maskrom_stubs.ld`,
   `include_lib/driver/cpu/br23/asm/cpu.h`, `include_lib/system/os/os_api.h` —
   evidence the whole link/config surface is open to us.
7. Their "hybrid v2 builder" (`create_hybrid_v2.ps1`: OEM chip header + SDK uboot +
   SDK app) is the same concept as our dump-splice sector flashing (ARTIFACTS.md §4) —
   but Windows-only scripts; we borrow the concept, never the scripts (platform rule).

## §28.5 — What this means for the two-SPP goal

1. **The SDK-rebuild route is feasible and externally proven** — a third party builds
   shippable br23 firmware on plain Linux with the official toolchain, against the same
   prebuilt BT libraries our firmware links. Open item 4 (feasibility build) has an
   off-the-shelf template.
2. **No shortcut exists in the wild**: the controller one-link policy (incoming pages,
   ch. 27) and the single-SPP-session app layer (ch. 27 §27.18) are vendor artifacts —
   every public SDK carries them unchanged.
3. Two concrete sub-routes, in cost order:
   - **(a) Bitcode surgery + relink** — patch the IR of `btctrler.a`
     (incoming-page/ACL policy) and/or `btstack.a` (session pools) and relink a
     TID-compatible app via LTO. Precedent: `patch_bitcode.py`; our pi32v2/IR tooling
     (ch. 24/25) transfers. Medium effort, highest fidelity to the stock app.
   - **(b) App rebuild** — build our own app from `apps/spp_and_le` (br23 board) with
     a proper multi-session SPP layer + per-device routing, keeping vendor bitcode for
     stack/controller. Full control, but re-implements the H3 app surface (UI, RF,
     menus) — largest effort; the code-cave alternative (ch. 23 cave + ch. 25 compile
     route) remains the cheaper way to get *just* the SPP multi-session rewrite into
     the existing app.
   - The ESP32 combo-device workaround (ch. 22 §9B.6.1 profile coexistence) stays the
     zero-firmware-change fallback.

## §28.6 — Next actions

1. **Feasibility build** (open item 4): clone `Jieli-Tech/fw-AC63_BT_SDK`, download the
   Linux toolchain (URL §28.4), `make` in `apps/spp_and_le/board/br23` with the CI
   gotchas applied. Success = `app.bin` byte-plausibly linking (we don't need to flash
   it yet). The §28.7 diary pre-solves every known wall (toolchain layouts, lto-wrapper
   symlinks, LTO relocation trampolines, libc quirks, Linux `isd_download` packaging).
2. Prototype the IR route: `llvm-dis` a `btctrler.a` member, locate the incoming-ACL
   policy (the ~644–722 ms LL teardown, ch. 27), assess patchability.
3. Repro: tree listings `work/fork_survey/trees/*.txt` (`git ls-tree -r --long`
   format); API metadata `work/fork_survey/fork_api.json`; clones `work/sdk-forks/`
   (shallow, single-commit — `git checkout -f master` to materialize a working tree).

## §28.7 — Git-history deep-dive (2026-10-21): every fork, every commit

Follow-up to the user's prompt to *grind through the full git history* of the fork
network (not just trees). All 12 clones were un-shallowed
(`git fetch --unshallow --filter=blob:none` — full history, blobs on demand), the missing
`jobitjoseph` clone was added, and the official repo was attached to every fork as a
local remote (`official` = `/home/stefan/h3plus/fw-AC63_BT_SDK`, master `fdc018d`,
248 commits, tags v0.2.0→v2.4.0). Unique work per fork =
`git log HEAD --not official/master`.

**Network topology.** All 12 forks descend from `hhy-ccj/fw-AC630N_BT_SDK` (the GitHub
network root; itself 82 commits ending 2020-07-06, **zero unique content**). Common root
commit 2020-06-16. No hidden branches anywhere in the network (every fork is master-only;
the official repo has one `feature/issue_attach` branch = issue-attachment stubs +
hogp-battery-push + sd-driver patch demos). `lingyi1105` and `jobitjoseph` are byte-equal
(HEAD `2607215b`).

**Unique-commit census vs official:** Acy19888 = **104**, Yennoccm = 18, iot-eco-system = 5,
stevemao / Glebka / SunnyKlara / Urbanmovez = 1 each, ACCount12 / mikewen / ruidian /
hhy-ccj / jobitjoseph / lingyi1105 = 0 (pure mirrors). **Zero commits in the entire
352-commit network history touch `cpu/br23/liba/`, `include_lib/btstack/` or
`isd_config_rule.c`** — git-level proof corroborating the §28.2 tree-hash finding (nobody
modified the BT libraries), and **zero multipoint-related commits exist anywhere**.

### Acy19888 — a complete Linux-build diary for br23 (the gold vein)

Cem (Bring2day), 2026-03-26 → 04-04, product app `zuupah_pen` on the AC635N demo board.
Beyond the §28.4 CI summary, the commit log is a step-by-step debug diary — effectively a
dry-run of our feasibility build, with every wall and fix already solved:

- **Toolchain install:** `curl https://pkgman.jieliapp.com/s/linux-toolchain` →
  `/opt/jieli`. Their CI script supports **both toolchain layouts** (old
  `/opt/jieli/pi32v2/bin`, new `/opt/jieli/common/bin`). `lto-wrapper` invokes bare
  `ld`/`nm`/`strip` → symlink from `pi32v2/bin` onto PATH; `apt install llvm-14` for
  `llvm-size`; `ulimit -n 8096`; stub `/usr/local/bin/host-client`, `/opt/utils/strip-ini`
  and `/usr/local/bin/lz4_packet` (the makefiles tolerate post-script failure via `-`).
- **The LTO Flash→RAM 23-bit relocation overflow saga** (their biggest wall, ~a dozen
  commits): LTO clones/inlines ROM-resident functions (`delay_nus.636`, `ldo13_on`,
  `pmu_analog.c`, p33 accessors, `os_current_task`, `os_taskq_post_type`, `os_mutex`) out
  of range. Fixes used: volatile-function-pointer wrappers, linker `--wrap=`, C
  trampolines at absolute ROM addresses (e.g. `spi_get_port` ROM@`0x1117f8`),
  `AT_VOLATILE_RAM_CODE`, compiling `ram_stubs.c` *without* LTO, `-code-model=large`,
  IR-patching `power_hw.c.o` (section attribute) and finally removing `power_hw.c.o`
  from `cpu.a`. The SDK's own link flags carry the same scars:
  `--plugin-opt=-inline-normal-into-special-section=true`,
  `--dont-complain-call-overflow`, `--allow-multiple-definition`. Extracted:
  `work/fork_deepdive/acy/ram_stubs.c`.
- **JieLi libc quirks** (no standard POSIX): no `fprintf` (use `snprintf` + `fwrite`);
  `fwrite(FILE*, buf, len)` is 3-arg non-POSIX; `fmkdir`/`fdelete` do not exist;
  `get_sfc_bit_mode()` stub must return **4** on AC635N (Quad-SPI).
- **Board-config deltas** worth copying: `TCFG_USER_EDR_ENABLE 0→1` ("SPP braucht EDR" —
  SPP requires EDR enabled); `VM_LEN` 8K→64K when using BLE RCSP OTA; `CHIP_NAME`
  AC6956C→AC693X "for packaging-tool compatibility"; PRCT section removed from
  `isd_config.ini`; LVD disabled at startup; `REGISTER_APPLICATION` (not `APP_REGISTER`),
  no `SYS_CALL_REGISTER`; `CONFIG_LITE_AUDIO` to skip audio-encoder headers.
- **Flash base / entry per chip — resolves the ch. 24 §24.7 entry-point question:**
  AC635N (br23) flash base `0x1E00000`, entry offset `+0x120` (⇒ `0x1E00120`);
  AC695N/AC6956C base `0x1D00000` entry `+0xC0`. Mechanism: `CONFIG_ENTRY_ADDRESS` in
  `board_ac635n_demo_global_build_cfg.h` feeds both the `sdk_ld.c` `CODE_BEG` and the
  `ENTRY` key in `isd_config.ini`. **Our H3 entry `0x1E00100` is a TID override of this
  knob** (or an older SDK default) — a build-config constant, not a hardware fact.
- **Hybrid-image recipe** (`cpu/br23/tools/create_hybrid_v2.ps1`, extracted): to run an
  SDK-built app under the **OEM uboot** — take the OEM chip-info header (first `0xC0`
  bytes), place SDK `uboot.boot` at `0xC0` and the SDK app at `0x12000` (extracted from
  `jl_isd.fw` at `0x400+0x12000`), because the OEM uboot does not understand the SDK app
  format. Their note: the chip has an **OTP key → USB flashing needs the vendor key
  file; alternative is OTA over Bluetooth**. (We already hold full-chip read/write via
  the decrypted dump route, but this is the packaging template if we ever build an app.)
- **Working br23 SPP example:** `zuupah_spp.c` (~700 KB/s file transfer over SPP + BLE
  5.1 dual mode) — extracted to `work/fork_deepdive/acy/`. Output image:
  `cpu/br23/tools/sdk.ufw`. Full CI recipe: `work/fork_deepdive/acy/build-zuupah.yml`.

### iot-eco-system — native-Linux packaging (no Windows host needed)

Enix Yu, 5 commits 2026-03-11 → 04-13 (bd19 target, but the tools are shared):

- `7306492` "fix: linux env build failed" adds a **native Linux x86-64 `isd_download`
  ELF binary** (10,277,648 B, `cpu/bd19/tools/isd_download`) + a Linux download script —
  the full packaging flow **without the Windows `host-client`**:
  `isd_download isd_config.ini -tonorflash -dev <chip> -boot 0x2000 -div8 -wait 300
  -uboot uboot.boot -app app.bin cfg_tool.bin -res <res>.bin -uboot_compress
  -flash-params flash_params.bin`, then `fw_add -noenc` for the OTA bin + `script.ver`,
  then `ufw_maker -fw_to_ufw`. Script: `work/fork_deepdive/iot/download_linux_data_trans.sh`.
- `8264521`: call `./lz4_packet` relatively + `cd $(dirname $0)`; bank-loop fix
  (`bank.bin` naming in the `cat`).
- `a3af23c`/`2f26c0c`: `serialble` app — BLE↔UART bidirectional bridge built on
  `apps/spp_and_le` (UUID `0xFF01` READ|WRITE|NOTIFY, `le_controller_get_mac` for the
  `serialble_XXXX` name). App-level, single-link; useful as a minimal SPP+BLE template
  (`work/fork_deepdive/iot/ble_serialble.c`).

### Yennoccm — the English SDK documentation set

18 commits, all README/doc uploads (2022-07), but valuable: **7 English-translated vendor
PDFs**, extracted to `work/fork_deepdive/yennoccm_docs/` (gitignored):

| Document | Pages | Note |
|---|---|---|
| `AC630N_bt_data_transfer_sdk_EN.pdf` | 187 | the BT data-transfer SDK manual (restored from `d367301` — deleted upstream later) |
| `AC630N_bt_data_transfer_sdk_introduce_EN.pdf` | 187 | near-duplicate intro edition |
| `AC630N_bt_data_transfer_sdk_version_info_EN.pdf` | 17 | version/changelog |
| `ISD_CONFIG_file_descrip_EN.pdf` | 10 | **`isd_config.ini` key-by-key reference** (from `doc/stuff/`) |
| `toolchain_guide_EN.pdf` | 4 | toolchain install |
| `Mode_management_interface_description.pdf` | 10 | sleep/mode management (from `doc/architure/`) |
| `System_Timer_Interface_Design_Instruction.pdf` | 12 | timer API |

### The remaining one-commit forks

- **stevemao** `b4a96b4`: `apps/hid/examples/ai_earbuds/ble_ai_earbuds.c/h` (1,637 lines) —
  a BLE-GATT cloud-AI channel running **during HFP calls** (audio mixer, wake-word/in-ear/
  app triggers, iOS CoreBluetooth protocol). Single-link app demo, not multipoint, but the
  best public example of BLE+HFP coexistence scheduling on this stack.
- **SunnyKlara** `b15b579` "SDK初始化": a **bd19** (wrong chip) GPS-keyboard product with
  committed build artifacts (`AC632N app.bin`, `bd19loader.bin`, `jl_isd.bin`, an
  `AC690X-8029.key` file) — no br23 insight.
- **Glebka** `b198366`: English comment-translation of bd19 `spp_and_le` board configs.
- **Urbanmovez**: README +2 lines.

### Official `patch_release/` inventory (for completeness)

Only four patch topics exist: AC632N/AE632N BT + low-power compatibility fix (2025-01-10),
**AC63N OTA-upgrade 4K-offset patch (2022-05-31 — contains `AC635N/br23loader.bin`,
`uboot.boot` and OTA bins: official release loaders for our exact chip)**, the AC63-series
VM compatibility fix (2025-02-24, = HEAD `fdc018d`), and a v2.2.1→v2.3.0 patch archive.
Nothing multipoint.

### §28.7 verdict

The history mining **confirms §28.2/§28.3 at the commit level** (nobody in the network
touched the BT stack, its config rules, or the controller libs; no multipoint work exists
to be found) while **upgrading the SDK-rebuild route from "externally proven" to
"externally debugged"**: Acy19888's diary pre-solves the toolchain install, the LTO
relocation wall, the libc quirks and the board-config deltas, and iot-eco-system supplies
the missing native-Linux `isd_download` packaging step. Entry-point question from
ch. 24 §24.7: **answered** (`CONFIG_ENTRY_ADDRESS` knob; AC635N default `0x1E00120`;
ours `0x1E00100` = TID override).

---

*[<< Index](Findings.md)* · [Ch. 27 §27.19 (why this survey)](27-firmware-2slot-stack-controller-wall.md#2719--e11-follow-up-checks-2026-10-20-deadlock-is-generic-sequential-pairing-avoids-it--but-e11-corrupts-normal-operation-nop-route-exhausted-rollback-to-e7-prepared) · [Ch. 24 (ecosystem)](24-jieli-ecosystem-sdk-toolchain.md) · [Ch. 25 (compile route)](25-ghidra-decompile-compile-route.md) · [Ch. 18 (priorities)](18-open-questions-next-steps.md)
