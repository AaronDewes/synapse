# Copyright 2015, 2016 OpenMarket Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
from typing import TYPE_CHECKING, Tuple

from synapse.api.errors import AuthError, Codes, NotFoundError, SynapseError
from synapse.http.server import HttpServer
from synapse.http.servlet import RestServlet, parse_json_object_from_request
from synapse.http.site import SynapseRequest
from synapse.types import JsonDict, RoomID

from ._base import client_patterns

if TYPE_CHECKING:
    from synapse.server import HomeServer

logger = logging.getLogger(__name__)


class AccountDataServlet(RestServlet):
    """
    PUT /user/{user_id}/account_data/{account_dataType} HTTP/1.1
    GET /user/{user_id}/account_data/{account_dataType} HTTP/1.1
    """

    PATTERNS = client_patterns(
        "/user/(?P<user_id>[^/]*)/account_data/(?P<account_data_type>[^/]*)"
    )

    def __init__(self, hs: "HomeServer"):
        super().__init__()
        self._hs = hs
        self.auth = hs.get_auth()
        self.store = hs.get_datastores().main
        self.handler = hs.get_account_data_handler()

    async def on_PUT(
        self, request: SynapseRequest, user_id: str, account_data_type: str
    ) -> Tuple[int, JsonDict]:
        requester = await self.auth.get_user_by_req(request)
        if user_id != requester.user.to_string():
            raise AuthError(403, "Cannot add account data for other users.")

        body = parse_json_object_from_request(request)

        # If experimental support for MSC3391 is enabled, then providing an empty dict
        # as the value for an account data type should be functionally equivalent to
        # calling the DELETE method on the same type.
        if self._hs.config.experimental.msc3391_enabled:
            if body == {}:
                await self.handler.remove_account_data_for_user(
                    user_id, account_data_type
                )
                return 200, {}

        await self.handler.add_account_data_for_user(user_id, account_data_type, body)

        return 200, {}

    async def on_GET(
        self, request: SynapseRequest, user_id: str, account_data_type: str
    ) -> Tuple[int, JsonDict]:
        requester = await self.auth.get_user_by_req(request)
        if user_id != requester.user.to_string():
            raise AuthError(403, "Cannot get account data for other users.")

        event = await self.store.get_global_account_data_by_type_for_user(
            user_id, account_data_type
        )

        if event is None:
            raise NotFoundError("Account data not found")

        return 200, event


class UnstableAccountDataServlet(RestServlet):
    """
    Contains an unstable endpoint for removing user account data, as specified by
    MSC3391. If that MSC is accepted, this code should have unstable prefixes removed
    and become incorporated into AccountDataServlet above.
    """

    PATTERNS = client_patterns(
        "/org.matrix.msc3391/user/(?P<user_id>[^/]*)"
        "/account_data/(?P<account_data_type>[^/]*)",
        unstable=True,
        releases=(),
    )

    def __init__(self, hs: "HomeServer"):
        super().__init__()
        self.auth = hs.get_auth()
        self.store = hs.get_datastores().main
        self.handler = hs.get_account_data_handler()

    async def on_DELETE(
        self,
        request: SynapseRequest,
        user_id: str,
        account_data_type: str,
    ) -> Tuple[int, JsonDict]:
        requester = await self.auth.get_user_by_req(request)
        if user_id != requester.user.to_string():
            raise AuthError(403, "Cannot delete account data for other users.")

        await self.handler.remove_account_data_for_user(user_id, account_data_type)

        return 200, {}


class RoomAccountDataServlet(RestServlet):
    """
    PUT /user/{user_id}/rooms/{room_id}/account_data/{account_dataType} HTTP/1.1
    GET /user/{user_id}/rooms/{room_id}/account_data/{account_dataType} HTTP/1.1
    """

    PATTERNS = client_patterns(
        "/user/(?P<user_id>[^/]*)"
        "/rooms/(?P<room_id>[^/]*)"
        "/account_data/(?P<account_data_type>[^/]*)"
    )

    def __init__(self, hs: "HomeServer"):
        super().__init__()
        self._hs = hs
        self.auth = hs.get_auth()
        self.store = hs.get_datastores().main
        self.handler = hs.get_account_data_handler()

    async def on_PUT(
        self,
        request: SynapseRequest,
        user_id: str,
        room_id: str,
        account_data_type: str,
    ) -> Tuple[int, JsonDict]:
        requester = await self.auth.get_user_by_req(request)
        if user_id != requester.user.to_string():
            raise AuthError(403, "Cannot add account data for other users.")

        if not RoomID.is_valid(room_id):
            raise SynapseError(
                400,
                f"{room_id} is not a valid room ID",
                Codes.INVALID_PARAM,
            )

        body = parse_json_object_from_request(request)

        if account_data_type == "m.fully_read":
            raise SynapseError(
                405,
                "Cannot set m.fully_read through this API."
                " Use /rooms/!roomId:server.name/read_markers",
                Codes.BAD_JSON,
            )

        # If experimental support for MSC3391 is enabled, then providing an empty dict
        # as the value for an account data type should be functionally equivalent to
        # calling the DELETE method on the same type.
        if self._hs.config.experimental.msc3391_enabled:
            if body == {}:
                await self.handler.remove_account_data_for_room(
                    user_id, room_id, account_data_type
                )
                return 200, {}

        await self.handler.add_account_data_to_room(
            user_id, room_id, account_data_type, body
        )

        return 200, {}

    async def on_GET(
        self,
        request: SynapseRequest,
        user_id: str,
        room_id: str,
        account_data_type: str,
    ) -> Tuple[int, JsonDict]:
        requester = await self.auth.get_user_by_req(request)
        if user_id != requester.user.to_string():
            raise AuthError(403, "Cannot get account data for other users.")

        if not RoomID.is_valid(room_id):
            raise SynapseError(
                400,
                f"{room_id} is not a valid room ID",
                Codes.INVALID_PARAM,
            )

        event = await self.store.get_account_data_for_room_and_type(
            user_id, room_id, account_data_type
        )

        if event is None:
            raise NotFoundError("Room account data not found")

        return 200, event


class UnstableRoomAccountDataServlet(RestServlet):
    """
    Contains an unstable endpoint for removing room account data, as specified by
    MSC3391. If that MSC is accepted, this code should have unstable prefixes removed
    and become incorporated into RoomAccountDataServlet above.
    """

    PATTERNS = client_patterns(
        "/org.matrix.msc3391/user/(?P<user_id>[^/]*)"
        "/rooms/(?P<room_id>[^/]*)"
        "/account_data/(?P<account_data_type>[^/]*)",
        unstable=True,
        releases=(),
    )

    def __init__(self, hs: "HomeServer"):
        super().__init__()
        self.auth = hs.get_auth()
        self.store = hs.get_datastores().main
        self.handler = hs.get_account_data_handler()

    async def on_DELETE(
        self,
        request: SynapseRequest,
        user_id: str,
        room_id: str,
        account_data_type: str,
    ) -> Tuple[int, JsonDict]:
        requester = await self.auth.get_user_by_req(request)
        if user_id != requester.user.to_string():
            raise AuthError(403, "Cannot delete account data for other users.")

        if not RoomID.is_valid(room_id):
            raise SynapseError(
                400,
                f"{room_id} is not a valid room ID",
                Codes.INVALID_PARAM,
            )

        await self.handler.remove_account_data_for_room(
            user_id, room_id, account_data_type
        )

        return 200, {}


def register_servlets(hs: "HomeServer", http_server: HttpServer) -> None:
    AccountDataServlet(hs).register(http_server)
    RoomAccountDataServlet(hs).register(http_server)

    if hs.config.experimental.msc3391_enabled:
        UnstableAccountDataServlet(hs).register(http_server)
        UnstableRoomAccountDataServlet(hs).register(http_server)
