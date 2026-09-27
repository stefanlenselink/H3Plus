"""Extract ASCII/UTF-16 strings from binaries and filter by keyword."""
# Copyright (c) 2026 Stefan Lenselink <Stefan@lenselink.org>
#
# SPDX-License-Identifier: MIT
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import sys, re, os

def strings(data, minlen=5):
    out = []
    # ASCII
    for m in re.finditer(rb'[\x20-\x7e]{%d,}' % minlen, data):
        out.append((m.start(), 'a', m.group().decode('ascii')))
    # UTF-16LE
    for m in re.finditer(rb'(?:[\x20-\x7e]\x00){%d,}' % minlen, data):
        out.append((m.start(), 'w', m.group().decode('utf-16le')))
    out.sort()
    return out

KEYWORDS = [
    'firmware', 'Firmware', 'FIRMWARE', 'upgrade', 'Upgrade', 'update', 'Update',
    '.fw', '.bin', 'encrypt', 'decrypt', 'Encrypt', 'Decrypt', 'AES', 'aes', 'xor', 'XOR',
    'crc', 'CRC', 'md5', 'MD5', 'sha', 'SHA', 'key', 'Key', 'password', 'Password',
    'bootloader', 'Bootloader', 'boot', 'flash', 'Flash', 'erase', 'Erase',
    'baud', 'COM', 'serial', 'Serial', 'usb', 'USB', 'HID', 'vid', 'pid', 'VID', 'PID',
    'TIDRADIO', 'TID', 'H3', 'Kenwood', 'Kendwood', 'ESP32', 'esp32', 'BK4819', 'AT1846',
    'http', 'https', 'api', 'token', 'PACKET', 'packet', 'ack', 'ACK', 'sector', 'addr',
]

def main():
    path = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else 'filter'
    data = open(path, 'rb').read()
    ss = strings(data, int(sys.argv[3]) if len(sys.argv) > 3 else 6)
    print(f"# {os.path.basename(path)}: {len(data)} bytes, {len(ss)} strings")
    if mode == 'all':
        for off, k, s in ss:
            print(f"{off:#010x} {k} {s}")
    else:
        seen = set()
        for off, k, s in ss:
            if any(kw in s for kw in KEYWORDS):
                if s in seen:
                    continue
                seen.add(s)
                print(f"{off:#010x} {k} {s}")

main()
