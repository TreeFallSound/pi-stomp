# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.


def read_hw_params(card_index: int = 0) -> dict[str, str]:
    """Parsed hw_params for a card's playback PCM; empty dict if unreadable.

    Values are the first token, so 'rate: 48000 (48000/1)' yields '48000'.
    Empty off-device, or when nothing holds the PCM open (the file reads
    'closed') — on-device we Requires=jack.service, so jackd always does.

    jackd's -p lands in 'period_size', which is what jack_bufsize reports.
    'buffer_size' is period x nperiods (-n) and is not the JACK buffer size.
    """
    path = "/proc/asound/card%d/pcm0p/sub0/hw_params" % card_index
    try:
        with open(path) as f:
            text = f.read()
    except OSError:
        return {}
    params = {}
    for line in text.splitlines():
        key, sep, value = line.partition(":")
        tokens = value.split()
        if sep and tokens:
            params[key.strip()] = tokens[0]
    return params
