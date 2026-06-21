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

import common.token as Token
import common.util as Util

import modalapi.mod as Mod
import modalapi.modhandler as Modhandler

class Handlerfactory:
    __single = None

    def __init__(self):
        if Handlerfactory.__single:
            raise Handlerfactory.__single
        Handlerfactory.__single = self

    def create(self, cfg, audiocard, cwd):
        # TODO handler could be independent of hardware (ie, have a software/ui version in the config, etc.)
        # to avoid supporting too many hardware/handler combos, we'll keep the handler locked to hardware versioning
        hw = Util.DICT_GET(cfg, Token.HARDWARE)
        if not hw:
            return None
        version = Util.DICT_GET(hw, Token.VERSION)
        if version is None or (version < 2.0):
            handler = Mod.Mod(audiocard, cwd)
        elif (version >= 2.0) and (version < 3.0):
            handler = Modhandler.Modhandler(audiocard, cwd)
        elif (version >= 3.0) and (version < 4.0):
            handler = Modhandler.Modhandler(audiocard, cwd)
        else:
            return None

        return handler
