# Ch. 29 — Static-Analysis Reference Map: SDK functions, RAM structures, and every patch site

> **Purpose:** one lookup table for everything the decompilation tree, `tools/findva.py`,
> the SDK LLVM-IR fingerprinting (§26.1), and the sub-agent asm censuses (E8–E11,
> ch. 27 §27.14–§27.17) located in `work/app_dec.bin` (v1.0.50). Written 2026-10-21 as
> the standing reference for the rewrite routes (code cave / SDK rebuild, ch. 28 §28.5)
> — so nothing has to be re-found.
>
> **Address math:** VA base `0x01E00000` = app offset 0; `file = VA − 0x01E00000`;
> `flash = file + 0x5000`; sector = `flash & ~0xFFF`. RAM addresses are the JieLi
> data-space words the decompiler names `DAT_000xxxxx` (r14-relative stack globals —
> Ghidra shows `BADSPACEBASE`; see §26.1 method notes).
>
> **Trust notes:** `work/full.lst` / `disassembled/full.lst` **drift** (linear-sweep) in
> `0x01E17xxx–0x01E18xxx` (§9B.10.2) and `0x01E19xxx`/`0x01E21xxx` (§27.12) — use
> `disassembled/disasm/*.asm` or the objdump ELF recipe (ch. 24 §24.5) there.
> `tbh` switch tables: `target = table_base + 2 × entry`.

---

## §29.1 — SDK `btstack.a` functions identified in our image

Identified by structural fingerprint against the br23 SDK IR (§26.1); the IR source
column names the `.c` whose compiled form matches. "First located" points at the write-up.

| SDK function | VA in our image | Role | IR source | First located |
|---|---|---|---|---|
| `user_send_cmd_prepare` | `0x01E1792E` | app BT-API dispatcher (je-code-chain, 67 call sites; codes incl. `0x4a` = close channels, 8/10 = disconnect-by-addr) | `user_interface.c` | §26.6 census / §27.10 |
| `disconnect` wrapper (→ `hci_disconnect_cmd`) | `0x01E07B08` | the **only** funnel to HCI Disconnect from host code; callers table §29.2 | `hci.c` (IR) | §27.4 |
| disconnect thunk | `0x01E19492` | bare `ff ea 39 73` = `goto 0x01E07B08` | — | §27.12 |
| disconnect-current | `0x01E178B2` | find conn (`0x01E17420` modes 0/2) → `disconnect(handle,0x13)` @`0x01E178CE`; returns "disconnected" when NOP'd | `user_interface.c` | §27.10 |
| find-conn | `0x01E17420` | conn lookup by mode (0/2 used) | — | §27.10 |
| `l2cap_disconnect` | `0x01E173D0` | close one L2CAP channel by CID: channel lookup `FUN_01e16938`, skip states {1,9}, force state `0xd`, pump `l2cap_run` | `l2cap.c` | §27.16 |
| `l2cap_disconnect_all_channel` (inlined body) | `0x01E17B20` | dispatcher `0x4a` body: `FUN_01e16878(0)` then ≤100× loop over channel list `[[0x1A4E0]]+8`, force `0xd` + pump — **the E10 "walk"** | `l2cap.c` | §27.15 |
| `l2cap_run` | `0x01E16F60` | L2CAP engine; state `0xd` = `l2cap_next_sig_id` + `l2cap_send_signaling_packet(code 6 …)` = **L2CAP Disconnect Request** | `l2cap.c` | §27.15 |
| `l2cap_run` call sites (12) | `0x01E173E6` `0x01E17506` `0x01E17B60` `0x01E194CE` `0x01E19994` `0x01E19C04` `0x01E19C90` `0x01E1A750` `0x01E1A75A` `0x01E1B68A` `0x01E1B69E` `0x01E229E6` | every pump point in the stack | `l2cap.c` | §27.16 |
| `spp_channel_disconnect` | `0x01E173EC` | SPP close: SPP control block `0x1A740`, live CID `[cb+2]` → `l2cap_disconnect` | `spp_profile.c` | §27.16 |
| `spp_connect` | `0x01E1750C` | **single-SPP-session chokepoint**: if `[cb+2]` BUSY → close incumbent @`0x01E1751E`, return −2, retry | `spp_profile.c` | §27.16 |
| SPP state machine `l2cap_disconnect` callers (4) | `0x01E235B8` `0x01E2376A` `0x01E23A50` `0x01E23BF4` | direct closes from the SPP SM | `spp_profile.c` | §27.17 |
| stack command dispatcher | `0x01E21AF8` | stack BT-task command loop: cases 8/10 disconnect-by-addr (`0x01E21F2C`/`0x01E21F56`), `0xB` = `DISCONN_SDP_MASTER` consumer @`0x01E21F5C` → `FUN_01e1782c(0,1,0)` → call `0x01E1786C` → `spp_channel_disconnect`; reason-`0x16` pair-kick sites `0x01E21DE4` (disconnect-ALL loop) + `0x01E21EC4` (single) | `user_interface.c` | §27.12 |
| stack task event switch | `0x01E19E44` | HCI event pump: **case 4** Connection Request (always accept, role `1` / `0xAA` if `DAT_0000c02b & 8`; SCO role 1; eSCO → accept-sync; else reject `0x0A`), case 5 Connection Complete (notify app `FUN_01e19a78(4,10)`), case 6 Disconnection Complete (cleanup only) | `hci_vendor.c` | §27.6 |
| stack event handler | `0x01E19A78` | forwarded-event handler: jumptable disconnect `(handle, msg[2])` @`0x01E19AD0`; subtype `0x73` orphan-ACL cleanup @`0x01E19B14` | `user_interface.c` | §27.14 |
| profile-record cleanup | `0x01E20962` | BT-task callback (registered file `0x018C90`): `disconnect(record.handle, 0x13)` @`0x01E20AB2` for profile types `&2`/`==0x40`, clears record | `user_interface.c` | §27.14 |
| `get_conn_for_addr` | `0x01E1682A` | 6-byte compare over conn array `0x1A5B8` (stride `0x1C`) | `user_interface.c` | §27.2 |
| `get_bt_current_conn` | `0x01E16878` | current conn getter | `user_interface.c` | §27.2 |
| conn-entry allocator | `0x01E17414` | pool `[0x1A4D8]+4`, **20 × 0x38 B** | `btstack_memory.c` | §26.9 |
| `is_1t2_connection` | `0x01E1787C` | `(h[0x1A662] & 7) == conn_num(0xBF39 b4–5)`; 6 callers `0x01E17A26` `0x01E21BC4` `0x01E21E58` `0x01E21F7E` `0x01E21FA6` `0x01E60CB0` (scan-management gates only) | `user_interface.c` | §9B.10.2 |
| `__set_user_ctrl_conn_num(1)` | `0x01E182B0` | inlined-arg setter; RMW @`0x01E182CC`, **patch byte `0x01E182DC` `0x24→0x25`**; single caller `0x01E60EB0` (init family `0x01E182E2`/`0x01E18310`/`0x01E18340`/`0x01E18376`) | `bt_configs.c` | §9B.10.2 |
| page-scan setter | `0x01E18AFC` | sets scan state `0xBEC8` (bit0 inquiry, bit1 page); disable branch @`0x01E18B0E` | `user_interface.c` | §26.9 |
| pool-create | `0x01E18AC6` | `(head, storage, count, block_size)`; bredr pool init `0x01E18B92–0x01E18BDA`: `malloc(0x76C)` wrapper `0x01E30F36`, `memset` `0x021127B4` | `btstack_memory.c` | §27.2 |
| `update_multi_bd_status` | — (weak stub → 0) | ops slot `[0xBF48+0x24]` never written; `multi_bd.c` **compiled EMPTY** (2 stray globals only) | `multi_bd.c` | §9B.11 / §26.6 |
| `user_operation_control` | (IR-side) | `USER_CTRL_START_CONNEC_VIA_ADDR`: `create_bt_new_conn(mac)` returns **NULL when slot held**; op 4 `USER_CTRL_DISCONNECTION_HCI` never posted by our app | `avctp_user.c` | §26.6 |

## §29.2 — HCI Disconnect executors and callers (complete enumeration)

All 13 sites of controller opcode `0x406` (§26.11 correction) and every caller of wrapper
`0x01E07B08` — the eviction-chain census that ran E6→E11:

| Path | VA | Reason | Reached from | Status |
|---|---|---|---|---|
| app kick executor | `0x01E074DE` (send @`0x01E074EE`) | `0x13` baked | relay case 5 `0x01E22996` ← kick `0x01E5B22A` | **NOP'd** `--no-kick` (E-era) |
| L2CAP timeout | `0x01E07606` | `0x0F` | caller `0x01E02FC0` | untouched (timeout only) |
| `0x01E178CE` | in `0x01E178B2` | `0x13` | dispatcher `0x4A` (mode-set `0x01E60188`, UI-connect `0x01E61E22`) + stack cmd 8/10 | **NOP'd** `--no-disconnect-13` (E6) |
| `0x01E1A100`, `0x01E1A300` | ACL setup paths | `0x5` | `FUN_01e19e44` region | untouched (explicit) |
| `0x01E21DE4` / `0x01E21EC4` | stack dispatcher | `0x16` | pairing-prep command (poster callback ptr file `0x018CBE`, untraced) | **NOP'd** `--no-pairing-kick` (E7) |
| `0x01E19AD0` | event handler | variable | forwarded HCI events | **NOP'd** `--no-cleanup-kick` (E8) |
| `0x01E19B14` | event handler | `0x13` | subtype `0x73` orphan-ACL cleanup | **NOP'd** (E8) |
| `0x01E20AB2` | `FUN_01e20962` | `0x13` | profile-record cleanup | **NOP'd** (E8) |

L2CAP-layer closers (one level up — what E8 exposed): dispatcher branch `je r11,#0x4a`
@`0x01E17974` → walk body `0x01E17B20` (§29.1); `0x4a` posters `0x01E61E22` (UI
connect-selected, **unconditional**) + `0x01E60188` (mode change with link up) — both
NOP'd by `--no-l2cap-teardown` (E9, co-actors only); `spp_channel_disconnect` entry
no-op'd by `--no-spp-close` (E10); branch + `l2cap_disconnect` entry no-op'd by
`--no-l2cap-disconnect` (E11). **Pointer scans: zero 32-bit LE refs to `0x01E17B20`,
`0x01E173D0`, `0x01E173EC`** — direct calls only (§27.17).

## §29.3 — Controller (btctrler) interface

| Item | VA / value | Note |
|---|---|---|
| controller command poster | `0x01E1664E` | `FUN_01e1664e(cmd, nargs, …)` → queue `0x1A688`; 12 call sites; only the kick posts cmd 5 |
| controller queue relay | `0x01E22890` | registered consumer (ptr at `0x01E18F68`); queue obj `0x1A688`, mailbox `0x1A694`, `0xB8` entries, handle stored `0x1A6AC`; created @`0x01E18F4A`, registered via `0x02003BBC` |
| relay cases | — | 1/3/4 = param writes (`0x01E07386`/`0x01E073F4`/`0x01E07440`); **5 = disconnect** (`0x01E22996`); 8 = profile state; 0xb = remote-name cache; 0x15 = LE adv config (`0xC54C`); 0x16 = accept/reject window `0x200C`; 0x82 = create-connection; 7/9/10/13/14/20/24/25/26 = no-ops |
| generic send-to-controller | `0x01E029DE` | `(module_desc, n, code, args…)`; `0x400006` = LMP module; HCI Disconnect = code **`0x406`** (= 1030; IR `lmp_hci_disconnect` → `lmp_hci_cmd_to_conn_for_handle(handle, 2, 1030, reason)`) |
| HCI command wrapper | `0x01E02C56` | below: `0x01E086F2` Accept Conn Req (`0x409`), `0x01E08726` Reject (`0x40A`, reason `0x0A`), `0x01E086FE` Accept Sync (`0x429`), `FUN_01e08672` `write_scan_enable` (`0x0C1A`) |
| controller link table | IR `bredr_table[4]` | controller built for 4 ACLs; **behaves single-link for incoming pages** (ch. 27 §27.5/§27.7) |

## §29.4 — RAM data structures (stack globals, app device struct, config)

| Address | Structure / field | Notes |
|---|---|---|
| `0x102F0` | **app device struct** (809 refs) | single remote-device model (ch. 22); handle `+0x82` (= `0x10372`); TX-active guard `+0x24C`; BT-mic flag `gp+0xC7` (ch. 23) |
| `0x1A520` | `__user_info` base (per §26.7 field math: queue `0x1A688 = +0x168`, connect-pending `[+0x142]` bit 7 set @`0x01E61DEA`) | §27.2 implies `0x1A53C` from the conn array (`0x1A5B8 − 0x7C`) — two estimates; treat as `~0x1A520–0x1A53C` |
| `0x1A5B8`–`0x1A5F0` | **conn_info array: 2 slots**, stride `0x1C` | `addr[6]@+0`, HCI handle `i16@+6`, `inused` = bit 29 of word `+0xE`; iteration sites `0x01E1682A`/`0x01E16878`/`0x01E17CEE`/`0x01E20F58`/`0x01E2136E` |
| `0x1A662` | conn-count word (bits 0–2 = count; slot bits 3–5) | read by `is_1t2_connection` |
| `0x1A4D8` | conn-entry pool head (`+4` = storage) | 20 × `0x38` B (§26.9) |
| `0x1A4E0` | L2CAP channel-list head | walk iterates `[[0x1A4E0]]+8` |
| `0x1A740` | **SPP control block** | live L2CAP CID at `[cb+2]`; single-session — the E11 wall (last-connection-wins) |
| `0xBF24` | `_stack_config` RAM base | blob image @file `0x01EC2064` (+21 = `0x11` = `auto_conn_device_num`+`user_ctrl_conn_num` = 1) |
| `0xBF39` | conn_num byte (bits 4–5) | setter §29.1; scan-state byte `0xBEC8` (bit0 inquiry / bit1 page) |
| `0xBF48` | ops table | `[+0x4]` = classifier entry; `[+0x24]` = `update_multi_bd_status` slot (**never written** → veto hook `FUN_01e18ffa` dead) |
| `0xC02B` | config flag byte (`DAT_0000c02b`) | bit 3 = keep-role select (stock `0x00` → role 1); gates 4 more accept decisions |
| `0xC54C` | BLE advertising config byte | **ruled out** as conn gate (§9B.10) — recorded so it is not chased again |
| `0xB464` | routing-mode byte | `b[0xB390+0xD4]`; modes 1–4 from classifier, 5–6 via patch tool |

bredr pool layout (1900 B block, init `0x01E18B92`–`0x01E18BDA`): `l2cap_service` 18×16 B
@`+0x14`, `l2cap_channel` 20×56 B @`+0x134`, `rfcomm_multiplexer` 2×20 B @`+0x594`,
`rfcomm_service` 6×20 B @`+0x5BC`, `rfcomm_channel` 6×52 B @`+0x634` — **all doubled vs
SDK defaults** (4/5/1/3/3, 600 B pool); `hfp_con`/`spp_conn` profile structs are `[1 x]`
but that suffices for 1×HFP + 1×SPP (§27.2).

## §29.5 — App-side functions (BT UI/state/protocol)

| Function | VA | Role |
|---|---|---|
| kick (eviction decision) | `0x01E5B22A` | `if (handle) { state=4; post cmd 5 }` — callers: BT on/off toggle `FUN_01e6076c` (`0x01E6076C`, off-path @`0x01E61D42`, on @`0x01E611CE`, callbacks `0x01E7EF1A`/`0x01E7F00A`/`0x01E83D9E`), BT power API `FUN_01e83d84` (`0x01E83D84`, callers `0x01E83DE2`/`0x01E83E12`), command table `0x01E9C9DC` entry[1] |
| command table | `0x01E9C9DC` | 7 entries `[0x01E4E2E4, **kick**, 0x01E50248, 0x01E5B25C, 0x01E5B262, 0x01E5B26E, 0x01E5B27C]` after `"tsk_read:"`; **dispatcher untraced** (no pointer — computed/ROM-side) |
| BT on/off toggle | `0x01E6076C` | on → flag + `FUN_01e4e3d6(1)`; off → kick |
| BT state get/set | `0x01E4E2BA` / `0x01E4E2C4` | state 4 = "disconnecting" (shallow) |
| BT event dispatcher | `0x01E83DB4` | case 7 = SPP data → parser |
| SPP/AT parser | `0x01E5B2F4` | `+SPP=P`→key `0x2A`, `+SPP=R`→`0x2B`, `AT+MPTT=1/0`, `CH_KEY=+/-`, `+POWER=0` → key queue; **device-agnostic** (§26.11) |
| BT-task UI state machine | `FUN_01e60e44` | "connect selected device" posts `0xc,0xe,0x12,5,0x4a` (string `Connecting` @`&DAT_01E9C7E0`); `0x4a` post @`0x01E61E22`; connect-pending bit set @`0x01E61DEA` |
| routing-mode setter | `FUN_01e60120` | posts `0x4a` @`0x01E60188` on mode change while link up |
| classifier | `0x01E7EC28` | name → routing mode 1–4; reached **only** via ops table `[0xBF48+0x4]`; mode imm @`0x01E7EC86` (duplex patch) |
| key-event call | `0x01E60A7E` | PTT-remap injection point (ctx `0x01E60A74`); pressed-key set-remove `0x01E4BAEA`; SPP ring enqueue `0x01E52362` |
| OD-PTT machinery | setup `0x01E72C38`, refresh `0x01E56D3C`, teardown `0x01E72DC4`, TX-stop `0x01E5A138` (self-guards `b[+0x24C]`) | ch. 13/23 |
| release dispatch window | `0x01E75E78` (32 B) | tbb table `0x01E75DDC` (entries `(target−table)/2`); bodies `0x01E75E38`/`0x01E75E42`; OD tail `0x01E75E4A`, VFO tail `0x01E75E50`, `b[+0x46]`+TX-start `0x01E75E56`; rel slots `0x01E75E82` OD / `0x01E75E8C` BT-alt / `0x01E75E92` TX-stop |
| **code cave** | `0x01EA76DE` (364 B, ALLZERO v44/v45/v50, pointer-scan clean) | carries BT-PTT2 code (press `+36`, release `+48`); ch. 23 |

## §29.6 — Patch-site master table (all multipoint options, current bytes)

Authoritative source: `tools/patch_h3plus_firmware_bluetooth.py` (site constants) —
both suites green. "HW" = hardware verdict.

| Option | VA(s) | flash sector(s) | stock → patched | HW verdict |
|---|---|---|---|---|
| `--conn-num=2` | `0x01E182DC` | `0x01D000` | `24 → 25` (byte) | insufficient (2026-10-03) |
| `--no-kick` | `0x01E5B22A` | `0x060000` | `7504c5ff → 40238000` (`r0=3;rts`) | kick dead (2026-10-05) |
| `--force-page-scan` | `0x01E18B0E` | `0x01D000` | `80412416 → 00000000` | **works** (2026-10-06) |
| `--force-role-keep` | `0x01E1A03A` | `0x01F000` | `50ee970161ff08004202 → c0ea4502` + 6×`00` | FAILED (2026-10-07) — role not the trigger |
| `--no-disconnect-13` | `0x01E178CE` | `0x01C000` | `bfea1b81 → 00000000` | **E6 PASSED** (2026-10-08) |
| `--no-pairing-kick` | `0x01E21DE4`, `0x01E21EC4` | `0x026000` | `bfea55bb`, `bfeae5ba` → `00000000` ×2 | E7 field-FAILED (2026-10-09) |
| `--no-cleanup-kick` | `0x01E19AD0`, `0x01E19B14`, `0x01E20AB2` | `0x01E000`, `0x025000` | `bfeadffc`, `bfeabdfc`, `bfeaeec4` → `00000000` ×3 | E8 partial — HCI eviction dead (2026-10-19) |
| `--no-l2cap-teardown` | `0x01E61E22`, `0x01E60188` | `0x066000`, `0x065000` | `bdea84ad`, `bdead1bb` → `00000000` ×2 | E9 FAILED (2026-10-20) — co-actors |
| `--no-spp-close` | `0x01E173EE` | `0x01C000` | `c0ff40a7 → 40200004` (`mov r0,#0; pop pc`) | E10 FAILED (2026-10-20) — walk bypasses |
| `--no-l2cap-disconnect` | `0x01E17974`, `0x01E173D0` | `0x01C000` | `0bf8d494 → 00000000`; `1004bfea → 00238000` (`mov r0,#0; rts`) | **E11: evictor DEAD** (2026-10-20) but corrupts normal ops (§27.19) → rollback prepared |
| key remaps | `0x01E60A74`/`0x01E60A7E`, `0x01E4BAEA`, `0x01E52362`, `0x01E7EC82`/`0x01E7EC86` | `0x061000`–`0x062000`, `0x04E000`, `0x056000`, `0x083000` | mode imm + call-arg rewrites | HW-confirmed (ch. 13) |
| BT-PTT2 | cave `0x01EA76DE` + trampoline window `0x01E75E38`–`0x01E75E92` | `0x0A7000` + `0x07A000` | direct rewrite, tbb untouched | **HW-confirmed** (ch. 23) |

**Rollback:** E11 → E7 = 32 B across five sectors (`0x01C000`/`0x01E000`/`0x025000`/
`0x065000`/`0x066000`), sector files `work/e7rb_*.bin` (§27.19).

## §29.7 — LLVM-IR reference material (regenerate on demand)

- The IR working set lived at `/tmp/opencode/btsdk/` (`uoc.ll` + 69 `.ll` files from
  `btstack.a` members: `spp_profile.c`, `l2cap.c`, `rfcomm.c`, `hci_vendor.c`,
  `user_interface.c`, `avctp_user.c`, `multi_bd.c`, `btstack_memory.c`, …).
  **`/tmp` is ephemeral** — regenerate: `ar p cpu/br23/liba/btstack.a <m>.c.o > m.o`
  then `llvm-dis-8 m.o` (bitcode version 53; the bundled JieLi clang 4.0.1 refuses
  several members). `btctrler.a` members are IR too (ch. 28 §28.4).
- IR ≠ our build byte-for-byte (reason 22 in 2025 IR vs 19 baked in v50) — fingerprint
  on **constants + structure**, never byte equality (§26.1).
- Compiling SDK IR to match our image: **blocked** (ISel segfault on
  `hci_emit_remote_name_cached`, §26.1) — but a from-scratch *app* build for br23 is
  externally proven (ch. 28 §28.4).

## §29.8 — Wire-protocol facts pinned by the captures

- PTT events: `+SPP=P`/`+SPP=R` (NUL-terminated) over SPP RFCOMM **ch 2**; HFP AG ch 6;
  the radio *sends* `AT+MPTT=1/0` (RX-squelch notification; never accepts it inbound).
- E6 side effect: after a second device joins, `AT+MPTT` notifications arrive on the
  first device's channel with the RFCOMM **`cr` bit flipped** (Address `0x11` vs `0x13`,
  CID 65 / DLCI 4) and payloads interleaved (`…4d 50` = `+MP`) — root-cause open
  (§27.11). The `+SPP=P/R` echo path is unaffected.
- Eviction signatures: app-level = graceful L2CAP Disconnection Request/Response → HCI
  Disconnect Complete `0x13`; controller incoming-page = `Connect Complete 0x13`
  ~644–722 ms after page, **no** prior success event; PC-side drop after channel-only
  close = Disconnect Complete `0x16` / MGMT `0x02` (local host).
- btmon decode: `btmon -r file.hcd` (no root for world-readable files); raw btsnoop
  parsers choke on btmon's mixed HCI+MGMT framing (§27.10).
- Test rig gotcha: BlueZ auto-connects paired accessories — keep the PC adapter **off**
  for radio-side pairing tests (§26.11 Result 3).

---

*[<< Index](Findings.md)* · [Ch. 26 (mechanism)](26-bluetooth-9-eviction-decision.md) ·
[Ch. 27 (experiment log E1–E11)](27-firmware-2slot-stack-controller-wall.md) ·
[Ch. 28 (fork survey)](28-sdk-forks-survey.md) ·
[Ch. 25 (decompile⇒compile route)](25-ghidra-decompile-compile-route.md)
