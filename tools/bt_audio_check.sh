#!/usr/bin/env bash
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

#
# Diagnose why radio audio is (or isn't) reaching this machine's speakers.
#
#   ./tools/bt_audio_check.sh [radio-mac]
#   ./tools/bt_audio_check.sh 0B:FF:59:E8:85:92
#
# Background -- WHO PLAYS WHICH ROLE
#
# The radio's firmware registers JL_A2DP_SRC and JL_HFP_AG (Findings.md 8.x).
# So the radio is the AUDIO GATEWAY / SOURCE, and this PC has to be the
# HANDS-FREE unit / SINK. Two different paths can carry received traffic to
# your speakers:
#
#   A2DP sink  - one-way, high quality. Radio -> PC only. No microphone.
#   HFP HF     - two-way, narrowband SCO. Needed for PTT mic audio.
#
# On Linux NEITHER of these lives in bluetoothd. Both are implemented by
# PipeWire + WirePlumber. bluetoothd only brokers the connection. This is why
# "stop pipewire" broke everything (Findings.md 9A.21) -- with it stopped
# there is nothing on this box that can accept an audio profile at all, so the
# radio sits on "Connecting ..." and you get no sound.
#
# THE SPP RED HERRING
#
# If the radio only reports "Bluetooth Connected" once you start
# bt_spp_hold.py, that is a SYMPTOM, not a fix. It means SPP was the only
# profile that accepted, i.e. PipeWire did NOT take the audio connection. SPP
# carries key events only (+SPP=P / +SPP=R) and will never produce sound.
# Audio working and SPP working are independent; you want both to connect.
#
# Requires: this must run as YOUR user, not root -- PipeWire is a per-user
# session service and is invisible from a root shell.

set -u

MAC="${1:-}"

if [[ $EUID -eq 0 ]]; then
    echo "!! Running as root. PipeWire is a PER-USER service, so every check"
    echo "!! below will look broken even if it is fine. Re-run WITHOUT sudo:"
    echo "!!     ./$(basename "$0") ${MAC}"
    echo
fi

hr() { echo; echo "=== $* ========================================"; }

hr "1. Is PipeWire actually running?"
# If these are not active, nothing on this machine can accept an audio
# profile, and the radio will never get past "Connecting ...".
for unit in pipewire pipewire-pulse wireplumber; do
    state="$(systemctl --user is-active "$unit" 2>/dev/null || true)"
    printf '  %-16s %s\n' "$unit" "${state:-<no user session>}"
done
echo
echo "  All three should say 'active'. If not:"
echo "      systemctl --user start pipewire pipewire-pulse wireplumber"

hr "2. Does PipeWire offer the HF / sink roles to BlueZ?"
# WirePlumber only registers BlueZ profile endpoints for the roles it is
# configured to expose. If hfp_hf / a2dp_sink are missing, the radio has
# nothing to connect to even though everything else looks healthy.
if command -v wpctl >/dev/null 2>&1; then
    wpctl status 2>/dev/null | sed -n '/Audio/,/^$/p' | head -n 40
else
    echo "  wpctl not found (install wireplumber's CLI) -- skipping"
fi
echo
echo "  Expect a Bluetooth device to appear here once the radio connects."

hr "3. What does BlueZ think the radio has connected?"
# This is the key line. Connected=yes with NO audio UUIDs negotiated means
# only SPP came up.
if [[ -n "$MAC" ]]; then
    bluetoothctl info "$MAC" 2>/dev/null || echo "  no info for $MAC"
else
    echo "  (pass the radio MAC as an argument to see this)"
    bluetoothctl devices Connected 2>/dev/null
fi

hr "4. Which profile is the card actually using?"
# A Bluetooth card usually has profiles: off / a2dp-sink / headset-head-unit.
# If it sits on 'off', audio is connected but muted at the routing layer --
# a very common cause of "connected but silent".
if command -v pactl >/dev/null 2>&1; then
    pactl list cards short 2>/dev/null | grep -i blue || echo "  no bluetooth card present"
    echo
    pactl list cards 2>/dev/null \
        | awk '/Name: bluez/,/Ports:/' \
        | grep -Ei 'Name:|Active Profile:|available: (yes|no)' \
        | head -n 40
else
    echo "  pactl not found -- skipping"
fi
echo
echo "  If 'Active Profile: off', force it:"
echo "      pactl set-card-profile <card-name> a2dp-sink        # listen only"
echo "      pactl set-card-profile <card-name> headset-head-unit # + microphone"

hr "5. Is PipeWire's BlueZ backend even loaded?"
#
# THE DECISIVE CHECK when section 3 shows audio UUIDs but section 4 shows
# "no bluetooth card present".
#
# PipeWire does not speak Bluetooth on its own. Audio support comes from a
# SEPARATE SPA plugin, shipped in its own package (libspa-0.2-bluetooth on
# Debian/Ubuntu). Without it, pipewire and wireplumber both report 'active'
# and everything looks perfectly healthy -- but no BlueZ card will EVER be
# created, and the radio's audio connection has nothing to land on.
#
# This also silently breaks if the plugin is present but WirePlumber's
# bluez5.roles list omits a2dp_sink / hfp_hf, since the radio is an Audio
# SOURCE and an Audio GATEWAY -- it needs us in the matching sink/HF roles.
plugin="$(find /usr/lib /usr/local/lib -name 'libspa-bluez5*.so' 2>/dev/null | head -n1)"
if [[ -n "$plugin" ]]; then
    echo "  BlueZ SPA plugin: $plugin"
else
    echo "  !! BlueZ SPA plugin NOT FOUND -- this alone explains 'no bluetooth card'."
    echo "  !! Install it and restart the session services:"
    echo "  !!     sudo apt install libspa-0.2-bluetooth"
    echo "  !!     systemctl --user restart pipewire pipewire-pulse wireplumber"
fi
echo
echo "  Roles WirePlumber is configured to accept (blank = defaults, which"
echo "  normally include a2dp_sink and hfp_hf):"
grep -rns 'bluez5.roles\|bluez5.enable\|bluez5.headset-roles' \
    /etc/wireplumber /usr/share/wireplumber ~/.config/wireplumber \
    2>/dev/null | sed 's/^/    /' | head -n 20
echo
echo "  Any BlueZ-related errors PipeWire logged:"
journalctl --user -u pipewire -u wireplumber --since '-10 min' 2>/dev/null \
    | grep -i 'bluez\|bluetooth' | tail -n 15 | sed 's/^/    /' \
    || echo "    (nothing)"

hr "6. Try forcing the audio connection now"
#
# The radio is the Audio SOURCE, so it would normally initiate. But an
# outbound profile connect from our side works too and is the fastest way to
# prove whether the backend can accept audio at all: if a card appears after
# this, the plumbing is fine and only the auto-connect was missing.
if [[ -n "$MAC" ]]; then
    echo "  Asking BlueZ to connect audio profiles to $MAC ..."
    bluetoothctl connect "$MAC" 2>&1 | sed 's/^/    /'
    sleep 3
    echo
    echo "  Bluetooth cards after the attempt:"
    pactl list cards short 2>/dev/null | grep -i blue | sed 's/^/    /' \
        || echo "    still none"
else
    echo "  (pass the radio MAC as an argument to try this)"
fi

hr "7. Is the BlueZ monitor actually LOADED by WirePlumber?"
#
# The plugin existing on disk proves nothing -- WirePlumber still has to load
# and run its bluez monitor. If the monitor is disabled or crashed, the file
# is present, everything reports 'active', no errors appear, and no card is
# ever created. Total silence in the logs is itself the tell: a working
# monitor logs something whenever a device connects.
echo "  Bluetooth objects known to PipeWire (expect bluez5 nodes/devices):"
if command -v pw-dump >/dev/null 2>&1; then
    pw-dump 2>/dev/null | grep -io '"[^"]*bluez[^"]*"' | sort -u | head -n 20 \
        | sed 's/^/    /' || true
    [[ -z "$(pw-dump 2>/dev/null | grep -i bluez)" ]] && \
        echo "    NONE -- the bluez monitor is not running."
else
    echo "    pw-dump not found"
fi
echo
echo "  Is the monitor disabled in config?"
grep -rns 'bluetooth\|bluez' \
    /etc/wireplumber ~/.config/wireplumber 2>/dev/null \
    | sed 's/^/    /' | head -n 20 || echo "    (no local overrides -- using defaults)"
echo
echo "  To see why it is not loading, restart WirePlumber with debug logging:"
echo "      systemctl --user stop wireplumber"
echo "      WIREPLUMBER_DEBUG=D wireplumber 2>&1 | grep -i bluez"
echo "  (Ctrl+C when done, then: systemctl --user start wireplumber)"

hr "8. CONTROL TEST -- does a known-good headset create a card?"
#
# This is the single most informative test left, and it needs no radio.
# The Jabra Evolve 65 is known to work with this PC. Connect it and re-check:
#
#   Jabra creates a card  -> PipeWire Bluetooth audio is FINE, and the fault
#                            is specific to the radio (role/codec negotiation).
#   Jabra creates NO card -> PipeWire Bluetooth audio is broken for
#                            EVERYTHING. Stop investigating the radio; this is
#                            a plain PipeWire/WirePlumber problem on this PC.
#
# Note the ROLE DIFFERENCE that makes this test sharp: the Jabra is a SINK
# (we send to it) and is handled by the a2dp_source/hfp_ag side of PipeWire.
# The radio is a SOURCE (it sends to us), needing a2dp_sink/hfp_hf. Those are
# separate role implementations, so the Jabra working does NOT by itself prove
# the roles the radio needs are available -- but it cleanly separates "all of
# Bluetooth audio is dead" from "only the source direction is".
echo "  Turn the Jabra on, connect it, then run:"
echo "      pactl list cards short"
echo "      wpctl status"
echo
echo "  Currently connected devices:"
bluetoothctl devices Connected 2>/dev/null | sed 's/^/    /' || true

hr "9. Summary of what a HEALTHY state looks like"
cat <<'EOF'
  pipewire/wireplumber .... active
  libspa-bluez5*.so ....... present
  bluetoothctl info ....... Connected: yes, audio UUIDs listed
  pactl list cards ........ a bluez_card.* present
  Active Profile .......... a2dp-sink  (or headset-head-unit for mic)

  NOTE ON ROLES: the radio advertises Audio Source + Handsfree Audio Gateway,
  i.e. it is the source/gateway. So this PC must run the MIRROR roles,
  a2dp_sink and hfp_hf. Audio UUIDs present (section 3) but no card
  (section 4) means the fault is on THIS side, not the radio's -- almost
  always a missing BlueZ SPA plugin or a roles list that excludes them.

  Audio and SPP are independent links. Neither needs the other, so get sound
  working on its own first, then start bt_spp_hold.py for the PTT key events.

  IF SECTIONS 1-6 ALL LOOK FINE AND THERE IS STILL NO CARD, the usual fix is
  simply to make WirePlumber re-enumerate -- it only builds cards for devices
  present when its bluez monitor starts, so a device connected during a
  restart can be missed entirely:

      systemctl --user restart wireplumber
      # then reconnect the radio and re-run this script
EOF
echo
