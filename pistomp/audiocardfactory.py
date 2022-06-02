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

import pistomp.audioinjector
import pistomp.hifiberry
import pistomp.iqaudiocodec
from pathlib import Path


class Audiocardfactory:
    __single = None

    def __init__(self, cwd):
        if Audiocardfactory.__single:
            raise Audiocardfactory.__single
        Audiocardfactory.__single = self
        self.cwd = cwd
        self.system_card_file="/proc/asound/cards"

    def get_current_card(self):
        result = None
        if Path(self.system_card_file).exists() is False:
            return result

        with open(self.system_card_file) as f:
            line = f.readline()
            while line:
                strs = line.split()
                if len(strs) > 2 and strs[0] == '0':
                    result = strs[1].lstrip('[').rstrip(']:')
                    break
                line = f.readline()
        f.close()
        return result

    def create(self):
        # get the current card
        card_name = self.get_current_card()
        if card_name == "IQaudIOCODEC":
            card = pistomp.iqaudiocodec.IQaudioCodec(self.cwd)
        elif card_name == "sndrpihifiberry":
            card = pistomp.hifiberry.Hifiberry(self.cwd)
        else:  # Could be explicit here but we need to return some card, so make it the most common option
            card = pistomp.audioinjector.Audioinjector(self.cwd)

        return card
