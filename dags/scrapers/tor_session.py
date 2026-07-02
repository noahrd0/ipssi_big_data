"""
tor_session.py
--------------
Gestion des sessions HTTP via les proxies Tor.
Rotation automatique sur erreur 429 / timeout.

Depuis l'hôte (WSL) : localhost:9050, 9052, 9054 (ports mappés Docker)
Depuis Airflow/Docker : tor1:9050, tor2:9050, tor3:9050

Chaque worker thread reçoit un proxy sticky (IP Tor distincte) via bind_worker_proxy().
"""

from __future__ import annotations

import logging
import os
import random
import threading
import time

import requests

logger = logging.getLogger(__name__)

_tls = threading.local()

_DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:128.0) "
        "Gecko/20100101 Firefox/128.0"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "fr-BE,fr;q=0.9,en-US;q=0.5,en;q=0.3",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


def _tor_proxies() -> list[str]:
    """Liste des proxies Tor selon l'environnement d'exécution."""
    explicit = os.getenv("TOR_PROXIES", "").strip()
    if explicit:
        return [p.strip() for p in explicit.split(",") if p.strip()]

    if os.getenv("TOR_MODE", "").lower() == "docker":
        return [
            "socks5h://tor1:9050",
            "socks5h://tor2:9050",
            "socks5h://tor3:9050",
        ]

    host = os.getenv("TOR_PROXY_HOST", "127.0.0.1")
    ports = os.getenv("TOR_PROXY_PORTS", "9050,9052,9054")
    return [f"socks5h://{host}:{p.strip()}" for p in ports.split(",") if p.strip()]


def _use_tor() -> bool:
    if os.getenv("CBSO_USE_DIRECT", "").lower() in ("1", "true", "yes"):
        return False
    if os.getenv("CBSO_USE_TOR", "1").lower() in ("0", "false", "no"):
        return False
    return True


def bind_worker_proxy(worker_index: int) -> str:
    """Assigne un proxy Tor fixe au thread courant (1 IP par worker)."""
    proxies = _tor_proxies()
    proxy = proxies[worker_index % len(proxies)]
    _tls.proxy = proxy
    _tls.proxy_index = worker_index % len(proxies)
    logger.info(f"[TOR] Worker {worker_index} → proxy {proxy}")
    return proxy


def _thread_proxy() -> str | None:
    return getattr(_tls, "proxy", None)


def _next_proxy(current: str | None) -> str:
    """Passe au proxy Tor suivant (rotation d'IP)."""
    proxies = _tor_proxies()
    if not proxies:
        raise RuntimeError("Aucun proxy Tor configuré")
    if current and current in proxies:
        idx = (proxies.index(current) + 1) % len(proxies)
    else:
        idx = getattr(_tls, "proxy_index", 0)
    proxy = proxies[idx]
    _tls.proxy = proxy
    _tls.proxy_index = idx
    return proxy


def make_session(proxy_url: str | None = None) -> requests.Session:
    """Crée une Session requests avec headers standard et proxy Tor optionnel."""
    session = requests.Session()
    session.headers.update(_DEFAULT_HEADERS)
    if proxy_url:
        session.proxies = {"http": proxy_url, "https": proxy_url}
    return session


def _direct_get(
    url: str,
    params: dict | None,
    extra_headers: dict | None,
    timeout: int,
    init_session_url: str | None,
) -> requests.Response:
    """Requête directe sans Tor."""
    session = make_session()
    if extra_headers:
        session.headers.update(extra_headers)
    if init_session_url:
        try:
            session.get(init_session_url, timeout=15)
        except Exception:
            pass
    logger.info(f"[CBSO] Requête directe (sans Tor) → {url[:80]}")
    return session.get(url, params=params, timeout=timeout)


def _tor_get(
    url: str,
    params: dict | None,
    extra_headers: dict | None,
    max_retries: int,
    base_wait: float,
    timeout: int,
    init_session_url: str | None,
) -> requests.Response:
    """GET via Tor avec proxy sticky par thread et rotation sur 429."""
    proxies = _tor_proxies()
    if not proxies:
        raise RuntimeError("Aucun proxy Tor disponible")

    proxy = _thread_proxy() or proxies[0]
    wait = base_wait
    last_exc: Exception | None = None

    for attempt in range(max_retries):
        session = make_session(proxy)
        if extra_headers:
            session.headers.update(extra_headers)

        if init_session_url:
            try:
                session.get(init_session_url, timeout=15)
            except Exception:
                pass

        try:
            logger.info(f"[TOR] Tentative {attempt + 1}/{max_retries} — proxy={proxy}")
            resp = session.get(url, params=params, timeout=timeout)

            if resp.status_code == 200:
                _tls.proxy = proxy
                return resp

            if resp.status_code in (429, 503):
                logger.warning(
                    f"[TOR] Rate-limit {resp.status_code} — rotation IP "
                    f"(attente {wait:.1f}s)"
                )
                time.sleep(wait + random.uniform(0, 1))
                wait = min(wait * 2, 60)
                proxy = _next_proxy(proxy)
                continue

            if resp.status_code in (403, 404, 500):
                return resp

            logger.warning(f"[TOR] Statut {resp.status_code} — rotation proxy")
            time.sleep(min(wait, 10))
            proxy = _next_proxy(proxy)

        except (requests.exceptions.ProxyError,
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as exc:
            last_exc = exc
            logger.warning(f"[TOR] Erreur réseau ({exc.__class__.__name__}) — rotation proxy")
            time.sleep(2)
            proxy = _next_proxy(proxy)

    raise RuntimeError(
        f"[TOR] Échec après {max_retries} tentatives pour {url}"
        + (f" ({last_exc})" if last_exc else "")
    )


def get_with_rotation(
    url: str,
    params: dict | None = None,
    extra_headers: dict | None = None,
    max_retries: int = 9,
    base_wait: float = 2.0,
    timeout: int = 30,
    init_session_url: str | None = None,
) -> requests.Response:
    """GET avec Tor (défaut) ou direct si CBSO_USE_DIRECT=1."""
    if not _use_tor():
        return _direct_get(url, params, extra_headers, timeout, init_session_url)
    return _tor_get(url, params, extra_headers, max_retries, base_wait, timeout, init_session_url)


def post_with_rotation(
    url: str,
    json: dict | None = None,
    data: dict | None = None,
    extra_headers: dict | None = None,
    max_retries: int = 6,
    timeout: int = 30,
) -> requests.Response:
    """POST avec rotation Tor."""
    if not _use_tor():
        session = make_session()
        if extra_headers:
            session.headers.update(extra_headers)
        return session.post(url, json=json, data=data, timeout=timeout)

    proxy = _thread_proxy() or _tor_proxies()[0]
    wait = 2.0

    for attempt in range(max_retries):
        session = make_session(proxy)
        if extra_headers:
            session.headers.update(extra_headers)

        try:
            resp = session.post(url, json=json, data=data, timeout=timeout)
            if resp.status_code == 200:
                return resp
            if resp.status_code in (429, 503):
                time.sleep(wait + random.uniform(0, 1))
                wait = min(wait * 2, 60)
                proxy = _next_proxy(proxy)
            else:
                return resp
        except Exception as exc:
            logger.warning(f"[TOR] POST erreur: {exc}")
            time.sleep(2)
            proxy = _next_proxy(proxy)

    raise RuntimeError(f"[TOR] POST échoué après {max_retries} tentatives")
