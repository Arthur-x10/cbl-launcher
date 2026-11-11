"""认证模块 - 支持离线模式和微软正版登录"""

import time
import uuid
from typing import Callable, Optional

import minecraft_launcher_lib

# 微软 Azure AD 应用 Client ID（使用公开的 Minecraft Launcher Client ID）
# 如需正式发布，应注册自己的 Azure AD 应用
CLIENT_ID = "00000000402b5328"

# 登录重定向 URI
REDIRECT_URL = "https://login.live.com/oauth20_desktop.srf"


class AuthResult:
    """认证结果"""

    def __init__(self, auth_type: str, username: str, uuid_str: str,
                 access_token: str, refresh_token: str = ""):
        self.auth_type = auth_type
        self.username = username
        self.uuid = uuid_str
        self.access_token = access_token
        self.refresh_token = refresh_token


def offline_login(username: str) -> AuthResult:
    """离线登录 - 生成假的 UUID 和 token"""
    player_uuid = str(uuid.uuid3(uuid.NAMESPACE_DNS, username))
    return AuthResult(
        auth_type="offline",
        username=username,
        uuid_str=player_uuid,
        access_token="0",
    )


def get_microsoft_login_url() -> tuple[str, str, str]:
    """获取微软登录 URL (用于浏览器打开)
    
    返回: (login_url, redirect_uri, state)
    """
    login_url, state, code_verifier = (
        minecraft_launcher_lib.microsoft_account.get_secure_login_data(
            CLIENT_ID, REDIRECT_URL
        )
    )
    return login_url, state, code_verifier


def complete_microsoft_login(auth_code: str, code_verifier: str,
                             redirect_uri: str = "") -> Optional[AuthResult]:
    """用 auth code 完成微软登录流程
    
    这是一个耗时操作，需要在后台线程调用。
    redirect_uri: 留空则用默认 REDIRECT_URL，自动登录会传入 localhost URI。
    """
    try:
        redir = redirect_uri or REDIRECT_URL
        login_data = (
            minecraft_launcher_lib.microsoft_account.complete_login(
                CLIENT_ID, None, redir, auth_code, code_verifier
            )
        )
        return AuthResult(
            auth_type="microsoft",
            username=login_data["name"],
            uuid_str=login_data["id"],
            access_token=login_data["access_token"],
            refresh_token=login_data.get("refresh_token", ""),
        )
    except Exception as e:
        print(f"微软登录失败: {e}")
        return None


# ═══════════════════ 设备码流程（内嵌浏览器不可用时的备用登录） ═══════════════════
# 现状：UI 走 ui/widgets/ms_login_dialog.py 的内嵌浏览器 + PKCE。
# 下面这组 API 是完整的备用路径，必须在后台线程调用（poll 会阻塞）。
# 已删除旧的 open_microsoft_login()：它用系统浏览器打开登录页，
# 但回调无法回到应用，永远拿不到授权码，属于不可用的死代码。


def start_device_code_login() -> dict:
    """设备代码流 — 获取 user_code 让用户在浏览器输入。

    返回: {"user_code", "device_code", "verification_uri", "interval", "expires_in"}
    """
    import requests
    resp = requests.post(
        "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode",
        data={
            "client_id": CLIENT_ID,
            "scope": "XboxLive.signin offline_access",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def poll_device_code(device_code: str, interval: int = 5, timeout: int = 300,
                     should_cancel: Optional[Callable[[], bool]] = None) -> Optional[dict]:
    """轮询设备代码，等待用户完成登录。

    成功返回 {"access_token": ...}，超时/拒绝/取消返回 None。
    should_cancel 是可选回调，返回 True 时立即结束（供 UI 的取消按钮使用）。
    """
    import requests
    deadline = time.time() + timeout
    while time.time() < deadline:
        for _ in range(int(max(1, interval) * 10)):
            if should_cancel is not None and should_cancel():
                return None
            time.sleep(0.1)
        resp = requests.post(
            "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
            data={
                "client_id": CLIENT_ID,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
            },
            timeout=15,
        )
        data = resp.json()
        if "access_token" in data:
            return data
        error = data.get("error", "")
        if error == "authorization_pending":
            continue
        if error in ("authorization_declined", "expired_token", "bad_verification_code"):
            return None
    return None


def complete_device_code_login(ms_access_token: str) -> Optional[AuthResult]:
    """用设备代码流获得的 MS token 完成 XBL → XSTS → MC 登录链。"""
    try:
        xbl = minecraft_launcher_lib.microsoft_account.authenticate_with_xbl(ms_access_token)
        xsts = minecraft_launcher_lib.microsoft_account.authenticate_with_xsts(xbl["Token"])
        mc = minecraft_launcher_lib.microsoft_account.authenticate_with_minecraft(
            xsts["Token"], xsts["DisplayClaims"]["xui"][0]["uhs"]
        )
        profile = minecraft_launcher_lib.microsoft_account.get_profile(mc["access_token"])
        return AuthResult(
            auth_type="microsoft",
            username=profile["name"],
            uuid_str=profile["id"],
            access_token=mc["access_token"],
            refresh_token="",
        )
    except Exception as e:
        print(f"设备代码登录失败: {e}")
        return None
