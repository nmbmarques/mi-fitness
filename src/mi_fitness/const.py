"""Constants and configuration."""

# region Xiaomi account OAuth endpoints
XIAOMI_LOGIN_URL = "https://account.xiaomi.com/pass/serviceLogin"
XIAOMI_LOGIN_AUTH_URL = "https://account.xiaomi.com/pass/serviceLoginAuth2"
XIAOMI_PREFERENCE_URL = "https://account.xiaomi.com/pass/preference"
XIAOMI_PHONE_INFO_URL = "https://account.xiaomi.com/pass/phoneInfo"
XIAOMI_SEND_TICKET_URL = "https://account.xiaomi.com/pass/sendServiceLoginTicket"
XIAOMI_TICKET_AUTH_URL = "https://account.xiaomi.com/pass/serviceLoginTicketAuth"
XIAOMI_QR_LOGIN_URL = "https://account.xiaomi.com/longPolling/loginUrl"
# endregion

# region Service SID (the sid parameter of serviceLogin)
SERVICE_SID_HEALTH = "miothealth"
# endregion

# region STS (security token exchange) endpoints
STS_HEALTH_URL = "https://sts-hlth.io.mi.com/healthapp/sts"
# endregion

# region API base URLs
HEALTH_API_BASE = "https://hlth.io.mi.com"
# endregion

# region Relatives API paths
RELATIVES_LIST_PATH = "/app/v1/relatives/get_relative_list"
RELATIVES_LATEST_DATA_PATH = "/app/v1/relatives/get_latest_data"
RELATIVES_AGGREGATED_DATA_PATH = "/app/v1/relatives/get_aggregated_data"
RELATIVES_FITNESS_DATA_PATH = "/app/v1/relatives/get_fitness_data"
RELATIVES_VERIFY_USER_PATH = "/app/v1/relatives/verify_userinfo_by_id"
RELATIVES_SEND_INVITE_PATH = "/app/v1/relatives/send_invite"
RELATIVES_OPERATE_INVITE_PATH = "/app/v1/relatives/operate_invite"
RELATIVES_DELETE_PATH = "/app/v1/relatives/delete_relative"
RELATIVES_GET_SHARED_TYPES_PATH = "/app/v1/relatives/get_shared_data_types"
RELATIVES_GET_APPLIED_SHARED_TYPES_PATH = "/app/v1/relatives/get_applied_shared_data_types"
RELATIVES_GET_FAMILY_MEMBER_PATH = "/app/v1/relatives/get_family_member"
RELATIVES_GET_INVITE_ID_PATH = "/app/v1/relatives/get_invite_unique_id"
RELATIVES_GET_TOPIC_SUBS_PATH = "/app/v1/relatives/get_topic_subscriptions"
# endregion

# region Messages API paths
MESSAGE_GET_LIST_PATH = "/app/v1/message/get_msg_list"
MESSAGE_CHECK_NEW_PATH = "/app/v1/message/check_new_msg"
MESSAGE_MODULE_RELATIVES = 1
# endregion

# region Business error codes
ERR_NOT_RELATIVES = -4002001
ERR_NOT_SHARED_DATA_TYPE = -4002004
ERR_DEVICE_UNTRUST = 70016
# endregion

# region Data type keys (used in get_aggregated_data / get_fitness_data requests)
DATA_KEY_GOAL = "goal"
DATA_KEY_HEART_RATE = "heart_rate"
DATA_KEY_SLEEP = "sleep"
DATA_KEY_BLOOD_PRESSURE = "blood_pressure"
DATA_KEY_STEPS = "steps"
DATA_KEY_CALORIES = "calories"
DATA_KEY_VALID_STAND = "valid_stand"
DATA_KEY_INTENSITY = "intensity"
DATA_KEY_WEIGHT = "weight"
DATA_KEY_SPO2 = "spo2"
DATA_TAG_DAILY_REPORT = "daily_report"
# endregion

# region Shareable data types (full auth_data set for send_invite)
ALL_SHARED_DATA_TYPES: tuple[str, ...] = (
    "goal",
    "heart_rate",
    "sleep",
    "blood_pressure",
    "steps",
    "calories",
    "valid_stand",
    "intensity",
    "weight",
    "spo2",
)
# endregion

# region verify_type enum for verify_userinfo_by_id
VERIFY_TYPE_XIAOMI_ID = 1
# endregion

# region Common HTTP headers
DEFAULT_USER_AGENT = "Android-12-3.53.1-vivo-V2284A"
DEFAULT_LOGIN_USER_AGENT = (
    "Dalvik/2.1.0 (Linux; U; Android 12; V2284A Build/ab8c0d1.1) "
    "APP/mi.health APPV/353001 MK/VjIyODRB "
    "SDKV/5.3.0.release.68 CPN/com.mi.health PassportSDK/"
)
APP_NAME = "com.mi.health"
REGION_TAG = "cn"
# endregion
