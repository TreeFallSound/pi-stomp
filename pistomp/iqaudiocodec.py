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

import os
import pistomp.audiocard as audiocard


class IQaudioCodec(audiocard.Audiocard):

    def __init__(self, cwd):
        super(IQaudioCodec, self).__init__(cwd)
        self.initial_config_file = os.path.join(cwd, 'setup', 'audio', 'iqaudiocodec.state')
        self.initial_config_name = 'IQaudIOCODEC'
        self.CAPTURE_VOLUME = 'Aux'
        self.MASTER = 'Headphone'  # Changed to headphone to allow digital control of output.
        self.DAC_EQ = "DAC EQ"
        self.EQ_1 = 'DAC EQ1'
        self.EQ_2 = 'DAC EQ2'
        self.EQ_3 = 'DAC EQ3'
        self.EQ_4 = 'DAC EQ4'
        self.EQ_5 = 'DAC EQ5'

        self.bypass_left = False
        self.bypass_right = False
        self._init_bypass()

    def _init_bypass(self):
        self.bypass_left = not self.get_switch_parameter('Mixout Left DAC Left')
        self.bypass_right = not self.get_switch_parameter('Mixout Right DAC Right')

    def get_bypass_left(self):
        return self.bypass_left

    def get_bypass_right(self):
        return self.bypass_right

    def set_bypass_left(self, bypass):
        self.bypass_left = bypass
        self.set_switch_parameter('Mixout Left Aux Left', self.bypass_left, store=False)
        self.set_switch_parameter('Mixout Left DAC Left', not self.bypass_left)

    def set_bypass_right(self, bypass):
        self.bypass_right = bypass
        self.set_switch_parameter('Mixout Right Aux Right', self.bypass_right, store=False)
        self.set_switch_parameter('Mixout Right DAC Right', not self.bypass_right)