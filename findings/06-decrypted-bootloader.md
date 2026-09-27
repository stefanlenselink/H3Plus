[<< Index](Findings.md)

## 8. Decrypted Bootloader Contents

Region `0x0000–0x4FFF` of `BIN/TID-H3-PlusV1.0.45.bin` decrypts to working UBOOT code. Strings recovered from `~0x3D50–0x4600`:

```
******************BootLoader*****************

<Error> [hid]ASSERT-FAILD: 0 hid set interface_hander fail
<Error> [hid]ASSERT-FAILD: 0 hid set interface_reset_hander fail
<Error> [usb]usb suspend / usb reset / usb resume
<Error> [usb]usb_setup NULL
<Error> [usb]ep0 TXCSRP_TxPktRdy busy
<Error> [flash]wait flash pgm ready fail!
<Error> [upgrade]open ota_file failed !
<Error> [main]ssp %x / usp %x / reti %x / rets %x

isd_config.ini      PLL_SRC             ubootZst
hid_reset           uboot_zone          UARTUPDATE
UART_UPDATE_CUSTOM  jump to %x          wait uart cmd
app_dir_head        app_dir_head2       app_area_head
crc_tmp = 0x%x      setup_interface     exception_analyze
jlfs_check_all_head
jlfs_dual_bank_check
jlfs_dual_bank_get_entry_addr
crc error cmd: %x--%x
crc error data: %x--%x
wait uart loader %x %d
drivers/usb/usb_setup.c
@JLUA    USBDP    USBDM
```

### What this tells us

- **`jlfs_dual_bank_check` / `jlfs_dual_bank_get_entry_addr`** → the device uses a **dual-bank (A/B) OTA scheme**. This is excellent news for safe custom firmware development: a failed update should fall back to the other bank.
- **`UARTUPDATE` / `UART_UPDATE_CUSTOM` / `wait uart cmd` / `wait uart loader`** → a UART-based recovery/update path exists in the bootloader, matching `updata.exe`'s Kenwood serial protocol.
- **`isd_config.ini`** → the JieLi standard config blob is present on-device and defines flash layout, PLL, and bank addresses. Recovering it would give the full memory map.
- **`app_dir_head` / `app_area_head`** → there is a directory structure describing the app area. Locating this in the decrypted image would map the app region.
- **`crc_tmp` / `crc error cmd` / `crc error data`** → CRC is checked on both command and data. Any patched image must have its CRC fixed (`jl_crc16`/`jl_crc32` above).
- **`exception_analyze`** → there's a crash handler; useful for debugging custom code.

---

*[<< Index](Findings.md)*
