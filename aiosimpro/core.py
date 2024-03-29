'''
core simpro
'''

from aiohttp import ClientSession, hdrs
from aiohttp.client_exceptions import ContentTypeError
from functools import wraps
from collections import namedtuple
from typing import Dict, Any
from itertools import count
from logging import getLogger

# hello
Response = namedtuple('Response', 'headers json')

logger = getLogger(__name__)

def updating_method(func):
    @wraps(func)
    async def wrapped(*args, **kwargs):
        assert args[0]._allow_write, 'simPRO instance read only'
        return await func(*args, **kwargs)

    return wrapped

class SimproAPIError(Exception):
    def __init__(self, status_code, payload, headers):
        self.status_code = status_code
        self.payload = payload
        self.headers = headers

class Simpro:
    def __init__(self,
            client_session: ClientSession,
            *,
            simpro_base_url,
            simpro_bearer_token,
            allow_write = False,
            ):
        self.client_session = client_session
        self.__simpro_base_url = simpro_base_url
        self.__std_headers = {
                hdrs.AUTHORIZATION: f'Bearer {simpro_bearer_token}',
                hdrs.CONTENT_TYPE: 'application/json',
                hdrs.ACCEPT: 'application/json',
                }
        self._allow_write = allow_write
        self.__prebuild_group_cache = None
        self.__catalog_group_cache = None
        self.__tax_code_cache = None
        self.__uom_cache = None

    async def _pages(self, url: str, *,
            headers: Dict[str, str] = None,
            params: Dict[str, Any] = None,
            page_size: int = None,
            item_limit: int = None,
            modified_since: str = None):

        params = dict(params or {})
        if page_size:
            params['pageSize'] = min(item_limit, page_size) if item_limit is not None else page_size

        headers = dict(headers or self._std_headers)
        if modified_since:
            headers['If-Modified-Since'] = modified_since

        item_count = 0
        for page in count(1):
            params['page'] = page
            async with self.client_session.get(
                    url,
                    headers = headers,
                    params = params
                    ) as response:
                resp = await _respond(response)
                num_pages = _get_possible_missing_int(resp.headers, 'Result-Pages')

                for item_count, item in zip(count(item_count + 1), resp.json):
                    yield item
                    if item_limit is not None and item_count >= item_limit:
                        return

            if page >= num_pages:
                return

    @property
    def _std_headers(self):
        return dict(self.__std_headers)

    def _url(self, path: str) -> str:
        if path.startswith('/'):
            path = path[1:]
        return f'{self.__simpro_base_url}/api/v1.0/companies/0/{path}'

def _get_possible_missing_int(in_dict: Dict, key: str):
    value = in_dict.get(key)
    if value is not None:
        return int(value)
    return 0

async def _respond(response):
    if response.status > 299:
        payload = await response.text()
        logger.warning('API failed with respose code %d, text %s.',
                response.status,
                payload)
        raise SimproAPIError(
                response.status,
                payload,
                response.headers
                )

    try:
        return Response(response.headers, await response.json())
    except ContentTypeError as error:
        logger.warning('API returned not json response')
