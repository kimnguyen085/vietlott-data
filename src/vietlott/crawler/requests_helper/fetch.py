"""
fetch data utilities
"""

import json
import os
import re
from typing import Callable, Optional, Tuple
from urllib.parse import urlencode

import requests
from loguru import logger

from vietlott.crawler.requests_helper.config import TIMEOUT

_SCRAPERAPI_ENDPOINT = "https://api.scraperapi.com/"


def _scraperapi_key() -> Optional[str]:
    return os.environ.get("SCRAPERAPI_KEY")


def _get(url: str, **kwargs) -> requests.Response:
    api_key = _scraperapi_key()
    if api_key:
        return requests.get(
            _SCRAPERAPI_ENDPOINT,
            params={"api_key": api_key, "url": url},
            timeout=TIMEOUT,
        )
    return requests.get(url, timeout=TIMEOUT, **kwargs)


def _post(url: str, params: dict, headers: dict, data: str, cookies: Optional[dict]) -> requests.Response:
    api_key = _scraperapi_key()
    if api_key:
        # ScraperAPI forwards the body and headers to the target URL.
        target = url + ("?" + urlencode(params) if params else "")
        return requests.post(
            _SCRAPERAPI_ENDPOINT,
            params={"api_key": api_key, "url": target},
            data=data,
            headers=headers,
            timeout=TIMEOUT,
        )
    return requests.post(
        url,
        data=data,
        params=params,
        headers=headers,
        cookies=cookies,
        timeout=TIMEOUT,
    )


def get_vietlott_cookie() -> Tuple[str, dict]:
    res = _get("https://vietlott.vn/ajaxpro/")
    match = re.search(r'document.cookie="(.*?)"', res.text)
    if match is None:
        raise ValueError(f"cookie is None, text={res.text}")
    cookie = match.group(1)
    cookies = {cookie.split("=")[0]: cookie.split("=")[1]}
    return cookie, cookies


def fetch_wrapper(
    url: str,
    headers: Optional[dict],
    org_params: Optional[dict],
    org_body: dict,
    process_result_fn: Callable,
    cookies: Optional[dict],
):
    """
    return a fn to fetch data for a set of params and body
    """

    def fetch(tasks):
        """
        perform fetching on multiple requests
        replace: org_params, org_body
        :param tasks: list of dict(task_id, task_data{params, body})
        :return:
        """
        tasks_str = ",".join(str(t["task_id"]) for t in tasks)
        logger.debug(f"worker start, tasks_ids={tasks_str}")
        _headers = headers.copy() if headers is not None else {}

        results = []
        for task in tasks:
            task_id, task_data = task["task_id"], task["task_data"]
            params = org_params.copy() if org_params is not None else {}
            body = org_body.copy()

            params.update(task_data["params"])
            body.update(task_data["body"])

            res = _post(url, params, _headers, json.dumps(body), cookies)

            if not res.ok:
                logger.error(
                    f"req fail, args={task_data}, code={res.status_code}, text={res.text[:200]}, headers={_headers}, body={body}, params={params}"
                )
                continue
            try:
                result = process_result_fn(params, body, res.json(), task_data)
                results.append(result)
                logger.debug(f"task {task_id} done")
            except json.JSONDecodeError as e:
                logger.error(
                    f"json decode error, args={task_data}, text={res.text[:200]}, headers={headers}, cookies={cookies}, body={body}, params={params}"
                )
                raise e
        logger.debug(f"worker done, tasks={tasks_str}")
        return results

    return fetch
