"""
Lawrence McDaniel - https://lawrencemcdaniel.com
Aug-2021

memberpress REST API Client plugin for Open edX - utility and helper functions.
"""
import json
import logging
import pytz
from dateutil.parser import parse, ParserError
from unittest.mock import MagicMock
from requests import Response

# django stuff
from django.conf import settings
from django.contrib.auth import get_user_model

# open edx stuff
from opaque_keys.edx.keys import CourseKey
from common.lib.xmodule.xmodule.modulestore.django import modulestore
from lms.djangoapps.courseware.date_summary import VerifiedUpgradeDeadlineDate
from common.djangoapps.student.models import get_user_by_username_or_email
from openedx.core.djangoapps.user_api.errors import UserNotFound

# our  stuff

UTC = pytz.UTC
logger = logging.getLogger(__name__)
User = get_user_model()


def logger(msg):
    logger.info(msg)


def objects_key_by(iter, key):
    index = {}
    for obj in iter:
        value = getattr(obj, key)
        index[value] = obj
    return index


def masked_dict(obj) -> dict:
    """
    To mask sensitive key / value in log entries.
    masks the value of specified key.

    obj: a dict or a string representation of a dict, or None

    example:
        2022-10-07 20:03:01,455 INFO member_press.client.Client.register_user() request: path=/api/user/v1/account/registration/, data={
            "name": "__Pat_SelfReg-07",
            "username": "__Pat_SelfReg-07",
            "email": "pat.mcguire+Pat_SelfReg-07@cabinetoffice.gov.uk",
            "password": "*** -- REDACTED -- ***",
            "terms_of_service": true
        }

    """

    def redact(key: str, obj):
        if key in obj:
            obj[key] = "*** -- REDACTED -- ***"
        return obj

    obj = obj or {}
    obj = dict(obj)
    for key in settings.MEMBERPRESS_SENSITIVE_KEYS:
        obj = redact(key, obj)
    return obj


class MPJSONEncoder(json.JSONEncoder):
    """
    a custom encoder class.
    - smooth out bumps mostly related to test data.
    - ensure text returned is utf-8 encoded.
    - velvety smooth error handling, understanding that we mostly use
      this class for generating log data.
    """

    def default(self, obj):
        if isinstance(obj, bytes):
            return str(obj, encoding="utf-8")
        if isinstance(obj, MagicMock):
            return ""
        try:
            return json.JSONEncoder.default(self, obj)
        except Exception:
            # obj probably is not json serializable.
            return ""


def get_user(username):
    try:
        return User.objects.get(username=username)
    except UserNotFound:
        pass


def log_trace(caller: str, path: str, data: dict) -> None:
    """
    add an application log entry for higher level defs that call the edxapp api.
    """
    logger.info(
        "member_press.client.Client.{caller}() request: path={path}, data={data}".format(
            caller=caller, path=path, data=json.dumps(masked_dict(data), cls=MPJSONEncoder, indent=4)
        )
    )


def log_pretrip(caller: str, url: str, data: dict, operation: str = "") -> None:
    """
    add an application log entry immediately prior to calling the edxapp api.
    """
    logger.info(
        "member_press.client.Client.{caller}() {operation}, request: url={url}, data={data}".format(
            operation=operation,
            caller=caller,
            url=url,
            data=json.dumps(masked_dict(data), cls=MPJSONEncoder, indent=4),
        )
    )


def log_postrip(caller: str, path: str, response: Response, operation: str = "") -> None:
    """
    log the api response immediately after calling the edxapp api.
    """
    status_code = response.status_code if response is not None else 599
    log_message = "member_press.client.Client.{caller}() {operation}, response status_code={response_status_code}, path={path}".format(
        operation=operation, caller=caller, path=path, response_status_code=status_code
    )
    if 200 <= status_code <= 399:
        logger.info(log_message)
    else:
        try:
            response_content = (
                json.dumps(response.content, cls=MPJSONEncoder, indent=4)
                if response is not None
                else "No response object."
            )
            log_message += ", response_content={response_content}".format(response_content=response_content)
        except TypeError:
            # TypeError: cannot convert dictionary update sequence element #0 to a sequence
            # This happens occasionally. Appears to be a malformed dict in the response body.
            pass

        logger.error(log_message)
