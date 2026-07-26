"""车来了(chelaile) Home Assistant 集成常量."""

from datetime import timedelta

# 集成 domain
DOMAIN = "chelaile"

# 上游 API 主机与路径
BASE_URL = "https://web.chelaile.net.cn"
API_BASE = f"{BASE_URL}/api/bus/"
# 城市列表(明文,不走 /api/bus/)
CITY_LIST_URL = f"{BASE_URL}/wwd/ncitylist"

# 请求签名盐值(微信小程序变体,与 H5 共用)
SIGN_SALT = "qwihrnbtmj"

# 响应解密:AES-256-ECB,32 字节 ASCII key
AES_KEY = b"FF32AE65FBFD19414EAAFF6291A54B42"

# 微信小程序默认参数(顺序敏感,合并到业务参数后再签名)
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

# 必需请求头(微信小程序指纹,tampering 会导致 400)
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

# 端点(相对 API_BASE)
EP_SEARCH_LINES = "query!nSearch.action"
EP_LINE_DETAIL = "line!encryptedLineDetail.action"
EP_STOP_DETAIL = "stop!encryptedPhyStnDetail.action"
EP_BUS_DETAIL = "line!encryptedBusDetail.action"
EP_CITY_MAX_INTERVAL = "bus/cityMaxInterval.action"
EP_BATCH_REALTIME = "line!encryptedTsfRealInfos.action"

# 上游状态码
STATUS_OK = {"00", "0000", "0"}
STATUS_DEPRECATED = "12009"

# 茂名默认城市 ID(对应 src=wechat_maoming 页面)。实测从 ncitylist 返回为 251。
# 此值仅作为 config flow 下拉默认选中,用户仍可选全部 477 个城市。
DEFAULT_CITY_ID = "251"  # 茂名

# 轮询间隔(秒)。城市 maxInterval 通常 30s,初版固定 30s
DEFAULT_SCAN_INTERVAL = timedelta(seconds=30)

# 配置流程各 step 名
STEP_USER = "user"
STEP_LINE = "line"
STEP_STOP = "stop"

# Config entry 数据键
CONF_CITY_ID = "city_id"
CONF_CITY_NAME = "city_name"
CONF_LINE_NO = "line_no"  # 用户输入的线路号(如 "7")
CONF_LINE_ID = "line_id"
CONF_LINE_NAME = "line_name"
CONF_DIRECTION = "direction"
CONF_START_SN = "start_sn"
CONF_END_SN = "end_sn"
CONF_TARGET_ORDER = "target_order"
CONF_STATION_ID = "station_id"
CONF_STATION_NAME = "station_name"
CONF_LAT = "lat"
CONF_LNG = "lng"

# Options
CONF_SCAN_INTERVAL = "scan_interval"

# 拥挤度映射: 0=空,1=中,2=挤
CAPACITY_MAP = {0: "空", 1: "中", 2: "挤"}
