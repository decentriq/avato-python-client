import requests
import socket
import platform
from enum import Enum
from urllib3.connection import HTTPConnection

AVATO_API_PREFIX = "/api"
AVATO_GENERAL_INFIX = ""
AVATO_ACTIVE_INSTANCE_INFIX = "/instance/:instanceId"


class Endpoints(str, Enum):
    # Instance
    INSTANCES_COLLECTION = "/instances",
    INSTANCE = "/instance/:instanceId",
    INSTANCE_FATQUOTE = "/instance/:instanceId/fatquote",
    INSTANCE_COMMANDS = "/instance/:instanceId/commands",
    INSTANCE_LOGS = "/instance/:instanceId/logs",
    # User
    USERS_COLLECTION = "/users",
    USER = "/user/:userId",
    USER_PASSWORD = "/user/:userId/password",
    USER_PERMISSIONS = "/user/:userId/permissions",
    USER_TOKENS_COLLECTION = "/user/:userId/tokens",
    USER_TOKEN = "/user/:userId/token/:tokenId",
    USER_FILES_COLLECTION = "/user/:userId/files"
    USER_FILE = "/user/:userId/file/:fileId",
    USER_FILE_CHUNK = "/user/:userId/file/:fileId/chunk/:chunkHash"

	

class APIError(Exception):
    def __init__(self, body):
        self.body = body

class AuthorizationError(APIError):
    """ """

    pass


class NotFoundError(APIError):
    """ """

    pass


class BadRequestError(APIError):
    """ """

    pass


class ServerError(APIError):
    """ """

    pass


class UnknownError(APIError):
    """ """

    pass

class HTTPAdapterWithSocketOptions(requests.adapters.HTTPAdapter):
    def __init__(self, *args, **kwargs):
        self.socket_options = kwargs.pop("socket_options", None)
        super(HTTPAdapterWithSocketOptions, self).__init__(*args, **kwargs)

    def init_poolmanager(self, *args, **kwargs):
        if self.socket_options is not None:
            kwargs["socket_options"] = self.socket_options
        super(HTTPAdapterWithSocketOptions, self).init_poolmanager(*args, **kwargs)

class HTTPAdapterWithTCPKeepalive(HTTPAdapterWithSocketOptions):
    def __init__(self, *args, **kwargs):
        platform_socket_options = [
            (socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 60),
            (socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 5),
        ]
        if platform.system()=="Linux":
            platform_socket_options += [
                (socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60),
            ]
        elif platform.system()=="Darwin":
            TCP_KEEPALIVE = getattr(socket, 'TCP_KEEPALIVE', 0x10)
            platform_socket_options += [
                (socket.IPPROTO_TCP, TCP_KEEPALIVE, 60)
            ]
        self.socket_options = HTTPConnection.default_socket_options + \
                [(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)] + \
                platform_socket_options
        super(HTTPAdapterWithTCPKeepalive, self).__init__(*args, **kwargs)

class API:
    def __init__(
        self,
        api_token,
        backend_host,
        backend_port,
        use_ssl,
        http_proxy,
        https_proxy,
    ):
        adapter = HTTPAdapterWithTCPKeepalive()
        session = requests.Session()
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        if use_ssl:
            if https_proxy:
                session.proxies = {"https": https_proxy}
            protocol = "https"
        else:
            if http_proxy:
                session.proxies = {"http": http_proxy}
            protocol = "http"
        self.base_url = f"{protocol}://{backend_host}:{backend_port}{AVATO_API_PREFIX}"
        auth_header = {"Authorization": "Bearer " + api_token}
        session.headers.update(auth_header)
        self.session = session

    @staticmethod
    def __check_response_status_code(response):
        if response.status_code >= 200 and response.status_code <= 204:
            pass
        elif response.status_code == 400:
            raise BadRequestError(response.content)
        elif response.status_code == 401 or response.status_code == 403:
            raise AuthorizationError(response.content)
        elif response.status_code == 404:
            raise NotFoundError(response.content)
        elif response.status_code >= 500 and response.status_code <= 504:
            raise ServerError(response.content)
        else:
            raise UnknownError(response.content)

    def post(self, endpoint, req_body=None, headers={}):
        url = self.base_url + endpoint
        response = self.session.post(url, data=req_body, headers={**headers})
        API.__check_response_status_code(response)
        return response

    def post_multipart(self, endpoint, parts=None, headers={}):
        url = self.base_url + endpoint
        response = self.session.post(url, files=parts, headers={**headers})
        API.__check_response_status_code(response)
        return response

    def put(self, endpoint, req_body=None, headers={}):
        url = self.base_url + endpoint
        response = self.session.put(url, data=req_body, headers={**headers})
        API.__check_response_status_code(response)
        return response

    def patch(self, endpoint, req_body=None, headers={}):
        url = self.base_url + endpoint
        response = self.session.patch(url, data=req_body, headers={**headers})
        API.__check_response_status_code(response)
        return response

    def get(self, endpoint, headers={}):
        url = self.base_url + endpoint
        response = self.session.get(url, headers={**headers})
        API.__check_response_status_code(response)
        return response

    def head(self, endpoint, headers={}):
        url = self.base_url + endpoint
        response = self.session.head(url, headers={**headers})
        API.__check_response_status_code(response)
        return response

    def delete(self, endpoint, headers={}):
        url = self.base_url + endpoint
        response = self.session.delete(url, headers={**headers})
        API.__check_response_status_code(response)
        return response
