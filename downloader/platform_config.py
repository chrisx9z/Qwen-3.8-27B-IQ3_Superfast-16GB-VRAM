from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlparse


class Platform(StrEnum):
    BILIBILI = "bilibili"
    DOUYIN = "douyin"
    REDNOTE = "rednote"


@dataclass(frozen=True)
class PlatformConfig:
    platform: Platform
    display_name: str
    domains: tuple[str, ...]
    login_url: str
    test_url: str


PLATFORM_CONFIGS: dict[Platform, PlatformConfig] = {
    Platform.BILIBILI: PlatformConfig(
        platform=Platform.BILIBILI,
        display_name="Bilibili",
        domains=(
            "bilibili.com",
            "b23.tv",
        ),
        login_url="https://passport.bilibili.com/login",
        test_url="https://www.bilibili.com/",
    ),
    Platform.DOUYIN: PlatformConfig(
        platform=Platform.DOUYIN,
        display_name="Douyin",
        domains=(
            "douyin.com",
            "iesdouyin.com",
        ),
        login_url="https://www.douyin.com/",
        test_url="https://www.douyin.com/",
    ),
    Platform.REDNOTE: PlatformConfig(
        platform=Platform.REDNOTE,
        display_name="RedNote",
        domains=(
            "rednote.com",
            "xiaohongshu.com",
            "xhslink.com",
        ),
        login_url="https://www.xiaohongshu.com/",
        test_url="https://www.xiaohongshu.com/",
    ),
}


def detect_platform(url: str) -> Platform | None:
    host = urlparse(url.strip()).netloc.lower()

    if not host:
        return None

    for platform, config in PLATFORM_CONFIGS.items():
        if any(
            host == domain or host.endswith(f".{domain}")
            for domain in config.domains
        ):
            return platform

    return None


def get_platform_config(
    platform: Platform,
) -> PlatformConfig:
    return PLATFORM_CONFIGS[platform]
