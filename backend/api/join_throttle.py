from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class JoinRegisterThrottle(AnonRateThrottle):
    scope = "join_register"


class JoinCodeThrottle(UserRateThrottle):
    scope = "join_code"


class SchoolRegisterThrottle(AnonRateThrottle):
    scope = "school_register"


class SchoolRegStatusThrottle(AnonRateThrottle):
    scope = "school_reg_status"
