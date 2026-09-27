[<< Index](Findings.md)

## 16. Risks and Safety Notes

> ⚠️ Read this section before touching hardware.

1. **NEVER write the chipkey.** The `jl-uboot-tool` shell exposes **`burnchipkey`** (protocol cmd `FC12`). It is **OTP (one-time programmable) and irreversible.** A wrong value permanently bricks the SoC beyond any recovery. **This unit's key is `0xF181` and it is already burned — there is no reason to ever run that command.**
2. **`erasechip` is the second most dangerous command.** It wipes the entire flash including the bootloader and the VM/settings area — destroying the unit's unique Bluetooth identity and pairing records, which are **not** recoverable from any distributed firmware file ([§12A.7](16-flashing-and-hardware-dump.md#12a7-the-settings--vm-area-at-0x0c9000--plaintext)).
3. **`updata.exe`'s "Update UBOOT" checkbox is the most dangerous control in the GUI toolchain.** Corrupting the bootloader removes the USB recovery path. Leave it unchecked unless you have a hardware programmer attached to the flash.
4. **Dump before you write.** ✅ Done — `Dumps/dump_internal.bin`. **Copy it off this machine.** It is the only copy of this unit's device-specific data (`0x0C8FE0` region + the whole VM area).
5. **Prefer the dual-bank OTA path.** The bootloader implements `jlfs_dual_bank_check` — work with it, not around it.
6. **CRCs are enforced** (`crc error cmd`, `crc error data`, `update failed, crc mismatch`). Any patched image needs valid CRCs or it will be rejected — which is a *safety feature*, not an obstacle.
7. **Legal/regulatory:** modifying TX band limits may place the device outside type acceptance for your jurisdiction. Transmitting outside your licensed allocation is illegal in most countries. Keep modified units on the bench or within your licence privileges.
8. **Keep `BIN/`, `FW/` and `Dumps/` pristine.** All generated artifacts belong in `work/`. These original images are irreplaceable if the vendor pulls them.

---

*[<< Index](Findings.md)*
