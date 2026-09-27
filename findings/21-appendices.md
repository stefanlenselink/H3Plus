[<< Index](Findings.md)

## Appendix A — Constants Cheat Sheet

```
=== HARDWARE (read from a live unit) ===
Chip family              BR23  ->  AC635N / AC695N series
UBOOT version            UBOOT1.00 (1.00)
CHIP KEY                 0xF181     (burned, NOT blank)
Flash JEDEC ID           0x856014   (SPI NOR on SPI0, 1 MiB)
Device firmware          v1.0.50  == TD-H3-PlusV1.0.50.bin
Transport                USB MSC, /dev/sgN on Linux (needs sudo)
BT Classic name          "TD-H3-Plus-3511"      @ 0x0C9012
BT LE name               "TD-H3-Plus-3511-ble"  @ 0x0C9036

=== Flash map (confirmed) ===
0x000000 - 0x0C8FDF   firmware image (== distributed .bin, byte-identical)
0x0C8FE0 - 0x0C8FFF   32 B device-specific runtime data (0xFF in the file)
0x0C9000 - 0x0C9FFF   JieLi VM / settings, PLAINTEXT, magic 55 AA AA 55
0x0CA000 - 0x0FFFFF   erased (0xFF)

=== Cipher 1: UBOOT (continuous stream) ===
LFSR polynomial          0x1021
LFSR default seed        0xFFFF
LFSR cycle length (P)    32767
Step:  k = ((k << 1) ^ (0x1021 if k & 0x8000 else 0)) & 0xFFFF
Apply: out[i] = in[i] ^ (k & 0xFF)

=== Cipher 2: APP REGION — SFC/ENC hardware scrambler ⭐ ===
Same LFSR, but RESEEDED EVERY 32 BYTES (= icache line size):
    for each 32-byte line at mapped address `addr`:
        k = (chipkey ^ (addr >> 2)) & 0xFFFF
        then step the LFSR per byte as above
chipkey                  0xF181
mapped base              0        (relative to app start 0x5000)
line size                32 bytes
key wraps every          262144 bytes (65536 * 4)
Symmetric — the same function encrypts and decrypts.
Result: entropy 7.9976 -> 6.9067, zeros 3023 -> 105074
Tool:   tools/jl_sfcenc.py   Output: work/app_dec.bin (802,784 B)
NOTE: 0xF181 is NOT on the 0xFFFF cycle — irrelevant; any 16-bit seed is valid.

=== Recovered phases (v1.0.45) ===
BIN phase @ offset 0     32591    (LFSR state 0x0AB8)
FW  phase @ offset 0     31567    (LFSR state 0x2F2A)
Difference               1024 = 0x400

=== Regions ===
UBOOT region             0x0000 - 0x4FFF   (decrypted ✅, continuous LFSR)
App region               0x5000 - 0xC8FDF  (decrypted ✅, SFC/ENC)
.fw payload offset       = .bin offset + 0x400

=== Magics ===
BIN magic                b3 69 bf 1d
BIN version string       "0.01"       @ 0x04
BIN key string           "X12345678"  @ 0x10
FW trailer magic         "JL_FW"      @ len-16

=== CRCs (from jl-uboot-tool) ===
jl_crc16   poly 0x11021      init 0x0000       rev False
jl_crc32   poly 0x104C11DB7  init 0x26536734   rev True

=== Other JieLi ciphers (both rejected for app region) ===
jl_rxgp_cipher    RNG seed 0x70477852
jl_crc_cipher     "MengLi", key = gb2312 "孟黎我爱你，玉林"

=== Bluetooth offsets in work/app_dec.bin (flash addresses) ===
LOAD BASE (VA)  = 0x01E00000 + offset_in_app_dec.bin
                = flash_addr + 0x01DFB000
0x01AE04  AT+BCS=2 ... AT+VGM=07   full HFP AT command set
0x01B03A  JL_A2DP_SRC
0x01B090  JL_HFP_AG      <- HFP Audio Gateway service record
0x01B0E0  JL_A2DP
0x01B12E  JL_HFP
0x01B300  JL_SPP
0x08BB39  mic_stream
0x083C5A  *** WHITELIST CHECK *** inline ptr 0x01E9B968 -> "TID-PTT"
0x091F98  "BT Int Mic"   (menu tbl 0x0C22A0)
0x091FAF  "BT Mic Gain"  (menu tbl 0x0C22A8)
0x091FBB  "BT Spk Gain"  (menu tbl 0x0C22AC)
0x097F8D  audio_enc
0x0A0580  msbc           <- wideband HFP codec
0x0A0968  TID-PTT        <- whitelist slot, 7 chars max, PREFIX match
0x0A0970  TID-MIC        <- whitelist slot, 7 chars max, PREFIX match
0x0A0C3C  AT+MPTT=0      <- vendor PTT release (xrefs 0x05FDE2, 0x07834C)
0x0A0C46  AT+MPTT=1      <- vendor PTT press
0x0A0E18  AT+BGMODE=1
0x0A0F5C  TID-MIC-EAR    <- whitelist slot, 11 chars max
0x0C2288  BT menu pointer table (12 entries, 4-byte stride)

PREFIX MATCH PROOF: real accessory advertises "TID-PTT0cd28a" (13 chars)
  but firmware stores only "TID-PTT" (7). It works => bounded/prefix compare.
  => writing the first 7 chars of ANY headset name whitelists it.
Patch tool: tools/patch_btname.py   Example output: work/dump_jabra.bin
  ('TID-MIC' -> 'Jabra E' = 7 bytes changed in the whole 1 MB image)

=== Useful addresses ===
jl_key::getMappingKey      ~0x9F0570  in work/UpdateApp_unpacked.exe
CLI usage strings           0x936C8C  in work/UpdateApp_unpacked.exe
updata.exe string table     0xA28E00 - 0xA29A00
Partial server URL          0x0042542B (in packed original)

=== Statistics ===
v1.0.44 XOR v1.0.45        57.70% identical, longest run 22,863 @ 0x37CA9
App region entropy          7.9944
App region IC               0.003912  (= random)
Coincidence spikes          at multiples of 32 only (lag 16 = baseline)
Distinct 32B blocks         23,706 (zero non-FF duplicates)
Flash dump entropy          6.9841   (low only due to 232,515 trailing 0xFF)
Flash dump IC               0.051548 (same cause)
Dump vs v1.0.50 .bin        31 differing bytes out of 823,296
```

---

## Appendix B — Raw Header/Footer Dumps

### B.1 `.bin` header — identical across all 12 BIN files

```
00000000  b3 69 bf 1d 30 2e 30 31  f0 31 ac 67 cc ad ff 68  |.i..0.01.1.g...h|
00000010  58 31 32 33 34 35 36 37  38 ff ff ff ff ff ff ff  |X12345678.......|
00000020  1e 5a 6e c5 bf 3e 7c f8  e0 84 a3 67 ce bd 5b 97  |.Zn..>|....g..[.|
00000030  7a 7c 53 17 a5 ad 45 21  f3 6d 13 d9 b3 67 cf 9f  |z|S...E!.m...g..|
```

### B.2 `.fw` footer — identical across all 12 FW files (last 64 bytes)

```
-0x40  20 34 13 d6 59 97 fa 2e  6f 41 76 89 28 f0 1e b8  | 4..Y...oAv.(...|
-0x30  1c e7 15 da 24 a5 8a 0a  5a 09 4c a7 57 0b 2e 22  |....$...Z.L.W.."|
-0x20  3d 9a 13 92 65 36 73 42  00 00 00 00 00 00 00 00  |=...e6sB........|
-0x10  4a 4c 5f 46 57 00 00 00  00 00 00 00 00 00 00 00  |JL_FW...........|
```

Note `65 36 73 42` at `-0x1C` — that is `0x26536734` byte-reversed-ish; compare the `jl_crc32` init constant `0x26536734`. Likely not a coincidence; worth checking whether the preceding bytes are a `jl_crc32` over the payload.

### B.3 Decrypted `.fw` header `0x000–0x200` (phase 31567) — **suspected wrong phase**

Retained as a negative result so it isn't re-derived. Note the LFSR-like runs, indicating double-XOR:

```
00000000  b8 76 e1 62 7d 65 64 c9  b4 47 8a 1c 38 53 a2 44  |.v.b}ed..G..8S.D|
00000010  e8 11 92 50 c6 be cc 98  11 03 06 2d 7b f6 cd 9a  |...P.......-{...|
00000020  34 68 f1 e2 c4 88 10 01  23 46 8c 18 30 41 a3 46  |4h......#F..0A.F|
00000030  8c 39 53 87 0e 3d 5b b6  6c d8 91 22 65 ca b5 6a  |.9S..=[.l.."e..j|
00000040  93 07 2f 5e 11 6a f0 c1  82 21 4a b5 6a 24 a3 50  |../^.j...!J.j$.P|
00000050  81 d3 4d 8c 18 11 03 27  4e 9c 19 13 07 0e 3d 5b  |..M....'N.....=[|
00000060  97 2e 5c 99 13 26 4c b9  53 87 0e 3d 7a d5 aa 75  |..\..&L.S..=z..u|
00000070  cb b7 4f bf 5f 9f 3e 7c  d9 b2 45 8a 14 28 50 a0  |..O._.>|..E..(P.|
00000080  26 cd 02 b5 c5 55 b5 c7  32 99 32 64 e9 d2 a4 69  |&....U..2.2d...i|
00000090  30 45 8b 14 09 12 05 2b  56 58 72 f2 e4 c8 b1 62  |0E.....+VXr....b|
000000a0  c4 88 10 20 61 e3 e7 ef  ff fe fc d9 93 26 6d da  |... a........&m.|
000000b0  b4 49 92 05 2b 56 ac 79  f2 c5 8a 14 28 71 e2 e5  |.I..+V.y....(q..|
000000c0  ca 94 09 12 24 48 b1 43  a7 6f de 9d 1b 17 2e 5c  |....$H.C.o.....\|
000000d0  f0 5c 02 86 fc c8 27 d6  62 e5 ca b5 4b 96 0d 3b  |.\....'.b...K..;|
000000e0  a1 0d 39 57 80 ef fa d5  8b e2 27 79 93 87 0e 1c  |..9W......'y....|
000000f0  78 70 e0 c0 80 21 63 c6  cc 39 53 87 2f 5e 9d 1b  |xp...!c..9S./^..|
00000100  36 4d bb 57 8f 3f 5f be  5d 9b 17 0f 3f 7e dd 9b  |6M.W.?_.]...?~..|
00000110  36 6c d8 91 22 44 88 10  01 02 04 29 52 a4 48 90  |6l.."D.....)R.H.|
00000120  55 22 ef 6f 74 2e 57 27  d7 39 dc 24 d9 6e fd db  |U".ot.W'.9.$.n..|
00000130  43 ee df 99 85 85 8a 14  68 85 c8 a7 61 f0 df be  |C.......h...a...|
00000140  7d 94 17 0f 1e 1d 3a 74  e9 bc 47 8e 3d 5b 97 2e  |}.....:t..G.=[..|
00000150  7d fa f4 e8 d0 a0 40 a1  42 84 29 52 85 2b 56 ac  |}.....@.B.)R.+V.|
00000160  58 91 03 06 0c 18 11 22  65 ca 94 28 71 e2 c4 88  |X......"e..(q...|
00000170  58 11 81 b4 94 81 b2 de  19 87 ee c8 0d 8e ef de  |X...............|
00000180  38 b8 55 a2 a3 35 10 01  62 07 25 73 51 d5 18 19  |8.U..5..b.%sQ...|
00000190  b3 7d 48 b9 53 87 2f 7f  df 9f 1f 1f 3e 5d ba 55  |.}H.S./.....>].U|
000001a0  aa 54 89 33 66 cc b9 72  e4 e9 f3 c7 8e 3d 7a f4  |.T.3f..r.....=z.|
000001b0  e8 d0 81 23 67 ef ff df  be 7c f8 f0 e0 c0 a1 63  |...#g....|.....c|
000001c0  88 9b 9e d0 9e 91 9e c1  82 25 6b d6 8d 1a 34 49  |.........%k...4I|
000001d0  89 e4 ec d2 8b 71 f3 e6  ed a4 e6 cd 81 34 68 d0  |.....q.......4h.|
000001e0  a1 23 67 ef de bc 59 93  07 2f 7f df be 7c f8 d1  |.#g...Y../...|..|
000001f0  83 06 0c 39 72 c5 8a 14  09 12 24 48 b1 62 e5 eb  |...9r.....$H.b..|
```

### B.4 Decrypted bootloader banner region (v1.0.45 `.bin`, ~`0x3D50–0x4600`)

```
<Error> [hid]ASSERT-FAILD: 0 hid set interface_hander fail
<Error> [hid]ASSERT-FAILD: 0 hid set interface_reset_hander fail
******************BootLoader*****************
<Error> [usb]usb suspend / usb reset / usb resume
<Error> [flash]wait flash pgm ready fail!
<Error> [upgrade]open ota_file failed !
<Error> [usb]usb_setup NULL
<Error> [usb]ep0 TXCSRP_TxPktRdy busy
isd_config.ini, PLL_SRC, ubootZst, hid_reset, uboot_zone, UARTUPDATE
jump to %x, app_dir_head, wait uart cmd, app_area_head, app_dir_head2
crc_tmp = 0x%x, setup_interface, exception_analyze, UART_UPDATE_CUSTOM
jlfs_check_all_head, jlfs_dual_bank_check, jlfs_dual_bank_get_entry_addr
crc error cmd: %x--%x, crc error data: %x--%x
<Error> [main]ssp %x / usp %x / reti %x / rets %x
wait uart loader %x %d, drivers/usb/usb_setup.c, @JLUA, USBDP, USBDM
```

---

*End of document.*

---

*[<< Index](Findings.md)*
