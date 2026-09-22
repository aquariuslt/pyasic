# ------------------------------------------------------------------------------
#  Copyright 2022 Upstream Data Inc                                            -
#                                                                              -
#  Licensed under the Apache License, Version 2.0 (the "License");             -
#  you may not use this file except in compliance with the License.            -
#  You may obtain a copy of the License at                                     -
#                                                                              -
#      http://www.apache.org/licenses/LICENSE-2.0                              -
#                                                                              -
#  Unless required by applicable law or agreed to in writing, software         -
#  distributed under the License is distributed on an "AS IS" BASIS,           -
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.    -
#  See the License for the specific language governing permissions and         -
#  limitations under the License.                                              -
# ------------------------------------------------------------------------------


class APIError(Exception):
    def __init__(self, *args):
        if args:
            self.message = args[0]
        else:
            self.message = None

    def __str__(self):
        if self.message:
            if self.message == "can't access write cmd":
                return f"{self.message}, please make sure your miner has been unlocked."
            return f"{self.message}"
        else:
            return "Incorrect API parameters."


class APITransportError(APIError):
    """The command got no usable answer: connection refused, connect or read
    timeout, an HTTP error status, or a body that is not the json the command
    speaks. A parser failing on an answer that did come back is not one."""


# what a transport error carries for the two failures with no exception of
# their own to pass on
DECODE_FAILURE_MESSAGE = "Failed to decode JSON"
AUTH_FAILURE_MESSAGE = "Failed to authenticate"


class PhaseBalancingError(Exception):
    def __init__(self, *args):
        if args:
            self.message = args[0]
        else:
            self.message = None

    def __str__(self):
        if self.message:
            return f"{self.message}"
        else:
            return "Failed to balance phase."


class APIWarning(Warning):
    def __init__(self, *args):
        if args:
            self.message = args[0]
        else:
            self.message = None

    def __str__(self):
        if self.message:
            return f"{self.message}"
        else:
            return "Incorrect API parameters."
