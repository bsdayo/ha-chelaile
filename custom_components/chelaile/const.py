"""集成设置与上游小程序协议常量。"""

DOMAIN = "chelaile"
DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 30
MAX_SCAN_INTERVAL = 900

# 上游 API 主机与路径
BASE_URL = "https://web.chelaile.net.cn"
API_BASE = f"{BASE_URL}/api/bus/"
# 城市列表使用明文响应，不经过 /api/bus/。
CITY_LIST_URL = f"{BASE_URL}/wwd/ncitylist"

# 请求签名盐值（微信小程序变体，与 H5 共用）
SIGN_SALT = "qwihrnbtmj"

# 响应使用 AES-256-ECB 加密，密钥为 32 字节 ASCII 文本。
AES_KEY = b"FF32AE65FBFD19414EAAFF6291A54B42"

# 签名时先放入默认参数，再放入本次请求的业务参数。
DEFAULT_PARAMS = {
    "s": "h5",
    "wxs": "wx_app",
    "sign": "1",
    "h5RealData": "1",
    "v": "3.11.28",
    "src": "weixinapp_cx",
    "ctm_mp": "mp_wx",
    "vc": "2",
    "favoriteGray": "1",
    "gpstype": "wgs",
    "geo_type": "wgs",
    "scene": "1256",
}

# 接口要求的请求头，包含微信小程序客户端标识。
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 "
        "MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI "
        "MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) "
        "UnifiedPCWindowsWechat(0xf254160a) XWEB/18055"
    ),
    "xweb_xhr": "1",
    "Content-Type": "text",
    "Accept": "*/*",
    "Sec-Fetch-Site": "cross-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Referer": "https://servicewechat.com/wx71d589ea01ce3321/814/page-frame.html",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

# 接口路径（相对于 API_BASE）
EP_SEARCH_LINES = "query!nSearch.action"
EP_LINE_DETAIL = "line!encryptedLineDetail.action"
EP_BUS_DETAIL = "line!encryptedBusDetail.action"

# 上游状态码
STATUS_OK = {"00", "0000", "0"}
