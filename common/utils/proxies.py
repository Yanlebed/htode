# common/utils/proxies.py

import random

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/98.0.4758.102 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 ...",
    # ...
]

PROXIES = [
    "http://user:pass@1.2.3.4:8080",
    "http://1.2.3.5:8080",
    # ...
]


def get_user_agent():
    return random.choice(USER_AGENTS)


def get_proxy():
    return random.choice(PROXIES)
