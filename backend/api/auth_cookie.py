from rest_framework.response import Response
from django.conf import settings
from rest_framework_simplejwt.views import TokenRefreshView
from .auth_throttle import LoginView

COOKIE = "marian_rt"


def put_cookie(resp):
    tok = getattr(resp, "data", None) and resp.data.get("refresh")
    if resp.status_code == 200 and tok:
        resp.set_cookie(COOKIE, tok, max_age=7 * 24 * 3600, httponly=True,
                        secure=not settings.DEBUG, samesite="Lax",
                        path="/api/auth/")
    return resp


class _Cookie:
    def finalize_response(self, request, response, *a, **k):
        r = super().finalize_response(request, response, *a, **k)
        return put_cookie(r)


class CookieLoginView(_Cookie, LoginView): pass


class CookieRefreshView(_Cookie, TokenRefreshView):
    def get_serializer(self, *args, **kwargs):
        data, c = kwargs.get("data"), self.request.COOKIES.get(COOKIE)
        if data is not None and not data.get("refresh") and c:
            kwargs["data"] = {"refresh": c}
        return super().get_serializer(*args, **kwargs)

    def post(self, request, *a, **k):
        if not request.data.get("refresh") and not origin_ok(request):
            return Response({"detail": "Bad origin."}, status=403)
        return super().post(request, *a, **k)


def origin_ok(request):
    o = request.headers.get("Origin")
    if not o:
        return True
    ok = set(getattr(settings, "CORS_ALLOWED_ORIGINS", []))
    ok |= set(settings.CSRF_TRUSTED_ORIGINS)
    ok.add(f"{request.scheme}://{request.get_host()}")
    return o in ok
