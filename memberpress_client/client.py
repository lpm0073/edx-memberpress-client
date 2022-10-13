"""
Lawrence McDaniel - https://lawrencemcdaniel.com
Oct-2022

memberpress REST API Client plugin for Open edX - rest api client implementation
"""
# Python stuff
import logging
import inspect
import json
import urllib3
from urllib.parse import urljoin
import requests

# Django stuff
from django.conf import settings
from django.core.cache import cache

# our stuff
from utils import MPJSONEncoder, masked_dict, log_pretrip, log_postrip, log_trace
from constants import MemberPressAPI_Endpoints, MemberPressAPI_Operations
from decorators import request_manager, app_logger

# disable the following warnings:
# -------------------------------
# /usr/local/lib/python3.9/site-packages/urllib3/connectionpool.py:1043:
# InsecureRequestWarning: Unverified HTTPS request is being made to host 'staging.global-communications-academy.com'.
# Adding certificate verification is strongly advised. See: https://urllib3.readthedocs.io/en/1.26.x/advanced-usage.html#ssl-warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


class APIClientBaseClass:
    def get_url(self, path) -> str:
        return urljoin(settings.MEMBERPRESS_API_BASE_URL, path)

    @property
    def headers(self) -> dict:
        return {
            f"{settings.MEMBERPRESS_API_KEY_NAME}": f"{settings.MEMBERPRESS_API_KEY}",
        }

    @request_manager
    def post(self, path, data=None, host=None, operation="") -> json:
        url = self.get_url(path, host=host)
        log_pretrip(caller=inspect.currentframe().f_code.co_name, url=url, data=data, operation=operation)
        response = requests.post(url, data=data, headers=self.headers)
        log_postrip(caller=inspect.currentframe().f_code.co_name, path=url, response=response, operation=operation)
        response.raise_for_status()
        return response.json()

    @request_manager
    def patch(self, path, data=None, host=None, headers=None, json=True, operation=""):
        url = self.get_url(path, host=host)
        if not headers:
            headers = self.headers

        log_pretrip(caller=inspect.currentframe().f_code.co_name, url=url, data=data, operation=operation)
        response = requests.patch(url, json=data, headers=headers)
        log_postrip(caller=inspect.currentframe().f_code.co_name, path=url, response=response, operation=operation)
        response.raise_for_status()
        if json:
            return response.json()
        return response

    @request_manager
    def get(self, path, params=None, host=None, full_url=False, operation="") -> json:
        url = self.get_url(path, host=host) if full_url is False else path
        log_pretrip(caller=inspect.currentframe().f_code.co_name, url=url, data={}, operation=operation)
        response = requests.get(url, params=params, headers=self.headers, verify=False)
        log_postrip(caller=inspect.currentframe().f_code.co_name, path=url, response=response, operation=operation)
        response.raise_for_status()
        return response.json()

    def is_valid_dict(self, response, qc_keys) -> bool:
        if not type(response) == dict:
            logger.warning(
                "is_valid_dict() was expecting a dict but received an object of type: {type}".format(
                    type=type(response)
                )
            )
            return False
        return all(key in response for key in qc_keys)


class MPClient(APIClientBaseClass):
    """
    memberpress REST API client
    """

    @app_logger
    def get_member(self, username) -> requests.Response:
        """
        Return a Memberpress REST api json object describing the authenticated user.
        """
        cache_key = f"get_member:{username}"
        log_trace(caller=inspect.currentframe().f_code.co_name, path=cache_key, data={})
        response = cache.get(cache_key)
        if response is None:
            path = MemberPressAPI_Endpoints.MEMBERPRESS_API_ME_PATH
            response = self.get(path=path, operation=MemberPressAPI_Operations.GET_MEMBER)
        cache.set(cache_key, response, settings.MEMBERPRESS_CACHE_EXPIRATION)
        return response

    @app_logger
    def is_active_subscription(self, request) -> bool:
        req_username = request.user.username
        if not req_username or req_username == "":
            logger.warning("received request with an invalid username {username}".format(username=req_username))
            return False

        member = self.get_member(req_username)
        if not self.is_valid_member(member):
            logger.warning(
                "get_member() returned an invalid json response {response}".format(
                    response=json.dumps(masked_dict(member), cls=MPJSONEncoder, indent=4)
                )
            )
            return False

        if not member:
            logger.warning("get_member() returned None for username {username}".format(username=req_username))
            return False

        res_username = member.get("username", "MISSING")
        if res_username != req_username:
            logger.warning(
                "internal error: requested username {req_username} but received {res_username}".format(
                    req_username=req_username, res_username=res_username
                )
            )
            return False

        recent_subscriptions = member.get("recent_subscriptions", [])
        for subscription in recent_subscriptions:
            if subscription.get("status", "") == "active":
                return True

        return False

    def is_valid_member(self, response: json) -> bool:
        """
        validate that response is a json dict containing at least
        the keys in qc_keys. These are the dict keys returned by the
        MemberPress REST api /me endpoint for a subscribed user.
        """
        qc_keys = [
            "id",
            "email",
            "username",
            "nicename",
            "url",
            "message",
            "registered_at",
            "first_name",
            "last_name",
            "display_name",
            "active_memberships",
            "active_txn_count",
            "expired_txn_count",
            "trial_txn_count",
            "sub_count",
            "login_count",
            "first_txn",
            "latest_txn",
            "address",
            "profile",
            "recent_transactions",
            "recent_subscriptions",
        ]
        return self.is_valid_dict(response, qc_keys)


class ClientWrapper:
    """
    A singleton wrapper around MPClient. Manages a single instance
    and returns it for reuse.
    """

    _client = None

    @classmethod
    def get_client(cls) -> MPClient:
        if not cls._client:
            cls._client = MPClient()
        return cls._client


def mp_client() -> MPClient:
    """
    A handy function to return a single client instance
    which is reused across all requests.
    """
    return ClientWrapper.get_client()
