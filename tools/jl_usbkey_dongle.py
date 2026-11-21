# MicroPython firmware for the JieLi USB_KEY boot-mode dongle (RP2040).
"""
jl_usbkey_dongle.py — drive the JieLi MaskROM USB_KEY handshake on a target's
USB data lines so its ROM bootloader enumerates on the PC.

Protocol (authoritative: kagaimiq/jielie `isp/usb/usb-key.md`, fetched 2026-11-18;
recorded with corrections in findings/39 §39.13):
  * 16-bit key 0x16EF, MSB-first, **D+ = clock** (chip latches on the rising
    edge), **D- = data**, ~50 kHz (software RX, no strict timing).
  * Sent repeatedly at every power-on until the chip ACKs by pulling BOTH
    lines low 1-2 ms. External pull-ups <= 4.7k required (the chip's 15k
    pulldowns during key RX + MCU-internal ~20k pull-ups form a false-ACK
    divider; a directly-attached PC adds another 15k).
  * After ACK the chip pulls D+ high and measures falling-edge periods for
    its PLL/reference-clock calibration, expecting 1 ms SOF pulses. The
    dongle emits SOF-alike negative pulses on D+ until D+ goes low, THEN
    closes the pass-through switch so the PC bus attaches.

This is FIRMWARE, not a host tool: it runs on an RP2040 under MicroPython
(copy to the board as `main.py`, or run from Thonny). It is the deliberate
exception to the repo's "pure-stdlib host tool" rule, like the Linux/BlueZ
rig is the exception to platform independence.

Wiring (full table + BOM: findings/39 §39.13):
  GP0   CLK   -> target D+ node   (open-drain, external 4.7k pull-up to 3V3)
  GP1   DATA  -> target D- node   (open-drain, external 4.7k pull-up to 3V3)
  GP2   SW_EN -> 2x SPST analog switch gate (PC-side D+/D- <-> target node)
  GP25  LED   -> blink = streaming key, fast = ACK/SOF, solid = PC attached

Safety: the dongle only drives its own 3V3-referenced open-drain pins through
4.7k pull-ups and switches the PC's D+/D- — VBUS is passed through for
charging only; never feed 3V3 into VBUS or the puck's battery rail.

SWITCHLESS variant (set SWITCHLESS = True below): the FIELD-PROVEN simpler topology
(findings/38 SS38.26-1, tmon.ch BR28 hack + christian-kramer issue #12) — the PC
stays PERMANENTLY attached in parallel with our pins (no analog switch, GP2 unused)
and after the ACK we merely release the lines: the host's REAL 1 ms SOF packets
calibrate the chip, so the SOF_PULSE phase is skipped. MANDATORY ordering: the PC
must already be connected BEFORE the target is powered on ("no host means no
calibration, and newer chips only try a few times"). The switched design remains
the isolated-bus fallback.
"""
# SPDX-License-Identifier: MIT
# Copyright 2026 Stefan Lenselink.

from machine import Pin
from time import ticks_us, ticks_diff, sleep_ms, sleep_us

KEY = 0x16EF          # JieLi USB_KEY, 16 bits, MSB first
HALF_US = 10          # 50 kHz clock: 10 us high + 10 us low per bit
PACKET_GAP_MS = 2     # idle between key packets (and the ACK-sense window)
ACK_LOW_US = 800      # both lines held low this long => acknowledge
SOF_PULSE_US = 10     # negative pulse width on D+ during SOF calibration
SOF_MS = 1            # SOF period (USB full-speed frame)
SOF_TIMEOUT_MS = 300  # give up on the calibration phase, re-stream the key
DPLUS_LOW_MS = 2      # D+ held low this long => chip moved on: connect the bus
SWITCHLESS = False    # True = field-proven parallel wiring (findings/38 SS38.26-1):
                      # PC permanently attached, GP2/switch unused, no SOF injection —
                      # after ACK release the lines and let the host's real SOFs
                      # calibrate the chip (PC MUST be attached before target power-on)

LED = Pin(25, Pin.OUT)
CLK = Pin(0, Pin.OPEN_DRAIN, value=1)    # open-drain: value 1 = release (high-Z)
DATA = Pin(1, Pin.OPEN_DRAIN, value=1)
SW_EN = Pin(2, Pin.OUT, value=0)         # 0 = PC isolated (normal while streaming)


def send_packet():
    """One 0x16EF packet, MSB first. Chip latches DATA on CLK rising edges."""
    for i in range(15, -1, -1):
        DATA.value((KEY >> i) & 1)
        CLK.value(0)
        sleep_us(HALF_US)
        CLK.value(1)                      # rising edge = latch
        sleep_us(HALF_US)
    CLK.value(0)
    DATA.value(0)


def ack_seen():
    """Release both lines and look for the chip driving BOTH low >= ACK_LOW_US.

    With 4.7k external pull-ups: puck-off => lines float high (no ACK);
    chip key-RX mode (15k pulldowns) => ~2.5 V, still read high (no ACK);
    chip ACK (strong pulldown) => < 0.8 V on both => ACK.
    """
    CLK.value(1)
    DATA.value(1)
    t0 = ticks_us()
    while ticks_diff(ticks_us(), t0) < PACKET_GAP_MS * 1000:
        if CLK.value() == 0 and DATA.value() == 0:
            t1 = ticks_us()
            while ticks_diff(ticks_us(), t1) < ACK_LOW_US:
                if CLK.value() or DATA.value():
                    return False
            return True
        sleep_us(50)
    return False


def sof_phase():
    """Chip pulls D+ high and measures falling-edge periods (wants 1 ms SOFs).

    Emit 10 us low pulses on D+ every 1 ms until D+ is held low by the chip
    (it stops pulling up as it initializes its USB interface) for
    DPLUS_LOW_MS, then release the line. Returns True if the calibration
    phase completed, False on timeout (caller re-streams the key).
    """
    t0 = ticks_ms()
    while True:
        if ticks_diff(ticks_ms(), t0) > SOF_TIMEOUT_MS:
            return False
        CLK.value(0)                      # pull D+ low (SOF-like edge)
        sleep_us(SOF_PULSE_US)
        CLK.value(1)                      # release -> pull-up / chip pull-up
        # watch D+ stay high for one frame period
        t1 = ticks_ms()
        low_since = None
        while ticks_diff(ticks_ms(), t1) < SOF_MS:
            if CLK.value() == 0:
                if low_since is None:
                    low_since = ticks_ms()
                elif ticks_diff(ticks_ms(), low_since) >= DPLUS_LOW_MS:
                    return True           # chip dropped D+ -> bus is ours
            else:
                low_since = None
        sleep_ms(0)


def main():
    SW_EN.value(0)                        # PC isolated until calibration done
    print("jl_usbkey_dongle: streaming USB_KEY 0x%04X (D+=clock, D-=data)%s"
          % (KEY, " [SWITCHLESS]" if SWITCHLESS else ""))
    if SWITCHLESS:
        print("SWITCHLESS: keep the PC attached BEFORE powering the target")
    print("now power on the target (hold its button >1 s); waiting for ACK ...")
    while True:
        # --- KEY_STREAM: blink = waiting --------------------------------
        LED.value(0)
        send_packet()
        LED.value(1)
        if ack_seen():
            LED.value(0)
            if SWITCHLESS:
                # Field-proven (findings/38 SS38.26-1): release and let the
                # permanently-attached host's real SOFs calibrate the chip.
                print("ACK (switchless) -> lines released; watch dmesg/lsusb")
                CLK.value(1)
                DATA.value(1)             # high-Z: the bus belongs to the PC
                while True:               # solid LED = enumerate on the PC now
                    LED.value(1)          # (run jl_hidboot.py / jl-uboot-tool)
                    sleep_ms(1000)
            print("ACK seen -> SOF calibration phase")
            if sof_phase():
                print("calibration done -> connecting PC bus")
                CLK.value(1)
                DATA.value(1)             # high-Z: hand the lines to the PC
                SW_EN.value(1)            # close pass-through switch
                while True:               # solid LED = enumerate on the PC now
                    LED.value(1)          # (run jl_hidboot.py / jl-uboot-tool)
                    sleep_ms(1000)
            print("SOF timeout -> re-streaming key")


if __name__ == "__main__":
    main()
