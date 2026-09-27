[<< Index](Findings.md)

## 11. Official Tooling Analysis

### 11.1 `Update App.exe` → `work/UpdateApp_unpacked.exe`

**Identification:** UPX-packed (sections `UPX0`/`UPX1`) Qt/MSVC PE32. Unpacked with UPX 5.0.2 → 14,513,568 bytes, 8 sections, `.qtmetad` present.

Internal original filename: **`firmware_upgrade_utility.exe`**. This is **JieLi's own official Firmware Upgrade Utility, v1.4.42** — not something TIDRADIO wrote. That means public JieLi documentation and community knowledge applies directly.

Accepts: `*.fw *.ufw *.bin`

#### Undocumented CLI (strings at `0x936C8C`)

```
Usage:
   %1 -d <device path> -f <firmware file> [-r] [-e|-a]
   %1 --help
   -d,--device       set target device drive letter label, eg: --device F
   -f,--firmware     set firmware file
   -e,--erase        Erase the entire flash
   -a,--fast         Fast download mode, donot erase flash first
   -r,--reset        reboot device if upgrade is successful
   -h,--help         show this help
```

Also present: `--target`, `--merge`, `Packing File: [length=0x%1] %2`, `PROGRESS: %1`, `SUCCESS!!!`

> `--merge` / `--target` / `Packing File` means **this tool can also *build* packages**, not just flash them. That is the intended repack path for custom firmware.

Note `-d` takes a **drive letter** — the device enumerates as a **USB Mass Storage** volume in bootloader mode. This matches the `jl-uboot-tool` transport.

#### Class / method symbols

```
jl_fw::package                        jl_fw::unpackage
jl_fw::generateFilesHead              jl_fw::setFileItem
jl_fw::hasTailInfo                    jl_format_ufw
jl_format_ufw::generateFilesHead
JL_PACKAGE_FORMAT_COMMON::decrypt     ::encrypt
JL_PACKAGE_FORMAT_COMMON::setChipKey  ::getChipKey    ::setFileItem
jl_crypto::decode_key                 jl_key::getMappingKey
jl_key::keyToByteArrayData            jl_key::byteArrayDataToKey
jl_key::handleKeyData                 JL_ARGSPARSE::removeKey
```

#### Package members / tokens

```
isd_config.ini   uboot.boot   uboot.part   uboot_head.part   uboot_data.part   app.bin
UBOOT_HEAD_ALIGN   TRIPLE_UBOOT   uboot1.00   uboot2.00
AU_KEY   V2_AU_KEY   "AC4600 New Key"   AC104N   EXTRA_CFG_PARAM/SERIAL_SEND_KEY
```

#### Error strings (reveal the security model)

```
ERROR: Chip key does not match firmware key.
ERROR: Chip key mismatch.
ERROR: Key not supported
ERROR: The chip has been burned key.
ERROR: Failed to get device chip key, error code:%1
ERROR: Invalid key string
ERROR: Invalid key data.
ERROR: Failed to verify uboot file data.
ERROR: The firmware chip type does not match the chip of the device.
Key matched
```

#### UI fields

```
Firmware CRC:      Firmware PID:      Firmware VID:
Firmware CPU_A version:      Dual Uboot      Key Blank
```

#### Embedded loader resources

```
:/loader/   loader.bin   loader.enc   loader.uart
LOADER-v1.0.0-$-@20240628-$0346277
```

`loader.enc` is the encrypted second-stage loader pushed to the chip; `loader.uart` is the serial variant. Extracting these from the Qt resource section would give clean, small `pi32` code samples — **ideal for bootstrapping a disassembler**, since they're small and their function is known.

#### Network functionality

```
getFirmwareFromServer      doGetFirmwareFromServer
form-data; name="apikey"
Download the burner firmware successfully
```

A partial URL `https://fmup.g...` was visible at `0x0042542B` in the still-packed original — a firmware update server endpoint.

### 11.2 `updata.exe` — Kenwood serial updater

Qt/MinGW PE, **not packed**, 15,936,000 bytes. Application string table at **`0xA28E00–0xA29A00`**.

#### Protocol strings

```
send device init cmd: %1
[Error, invalid reply, rspStatus %1]
send device check cmd
after uboot write 64K, crc mismatch
erase reply %1          write reply %1
after write flash: len = , writeLen =
app_dir_head            uboot_zone
4K.bin                  0K.bin
should erase , off = , size =
failed to erase app zone        failed to erase 64K addr
failed to erase 0K addr         failed to write flash
failed to switch to app zone    send reboot
update failed, crc mismatch     update ok

isReplyWriteCmd     isReplyEraseCmd     isReplyFlashCrcCmd
isReplyDeviceCheckCmd               isReplyDeviceInitCmd

already read buf:   after remove:   payloadLen =   , buffer.size
recv invalid packet:    open failed:    portName=   , baudRate
uboot_update_log_%1.txt     MMddHHmmss
```

#### Inferred command set

`DeviceInit` → `DeviceCheck` → `Erase` → `Write` → `FlashCrc` → `Reboot`, each with a matching reply. Payload-length-prefixed packets with CRC. The `0K.bin` / `4K.bin` / `switch to app zone` / `erase 0K addr` / `erase 64K addr` strings describe a careful bootloader-update ordering (write the 0K sector last so a mid-update failure is recoverable).

#### UI elements

```
checkBoxUpdateUBoot   btnSelectFile   btnStart   btnClearLog
comboBoxSerials       btnRefresh      spinBoxBaudRate
editLog               editKey

"uboot serial update"   "Update UBOOT"   "Select File"   "Start Update"
"Serial Port"   "Refresh Serial Port"   "BaudRate"   "ENCRYPT NUMBER"
"update file (*.bin)"   "select update file"

threads: PhySerialThread  UpdateThread
         on_openRequest  on_reOpenRequest  on_writeBuffer
         shouldReplyFake  on_readReady
```

**`editKey` is labelled `ENCRYPT NUMBER`** — and `X12345678` sits in the BIN header at `0x10`. These are the same field. The user is expected to type the encrypt number; the tool matches it against the image.

> `shouldReplyFake` is an interesting symbol — suggests a debug/simulation mode that fakes device replies. Useful for protocol testing without hardware.

### 11.3 `TIDRadioCPS.exe` — .NET CPS

| Attribute | Value |
|---|---|
| Size | 636,416 bytes |
| Type | PE32, .NET (`BSJB` metadata, `_CorExeMain`, `mscoree`) |
| Sections | 3 |
| CLR directory | RVA `0x2008` |
| Status | **Not yet decompiled** |

Ships with:

```
WeifenLuo.WinFormsUI.Docking.dll     Toub.Sound.Midi.dll
help.xml    Tone.txt    DockPanel.config    language XMLs
```

**Codeplug templates in `td/` — each exactly 65,536 bytes (64 KB):**

```
H3_Plus(GMRS).td    H3_Plus(HAM).td    H3_Plus(Normal).td
638UV variants      H7_Plus            H8-4rd             H9
```

The uniform 64 KB size means these are **raw EEPROM/codeplug images**, and the three H3_Plus variants differ only in configuration. **Diffing `H3_Plus(GMRS).td` against `H3_Plus(HAM).td` should directly expose the band-restriction fields** — this is by far the lowest-effort, lowest-risk path to unlocking TX coverage, and requires no firmware modification at all.

Being plain .NET with no obfuscation noted, ILSpy/dnSpy will produce near-original C#.

---

*[<< Index](Findings.md)*
