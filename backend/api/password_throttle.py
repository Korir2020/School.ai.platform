from rest_framework.throttling import UserRateThrottle


class PasswordRateThrottle(UserRateThrottle):
    scope = "password"
