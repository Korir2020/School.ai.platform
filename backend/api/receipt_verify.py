"""Public receipt check. The QR on a receipt carries a signed token that proves Marian issued it."""
from django.core import signing
from django.http import HttpResponse
from django.utils import timezone
from django.utils.html import escape
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.throttling import AnonRateThrottle

from schools.models import FeePayment

SALT = "marian.receipt.v1"
PATH = "/api/fees/receipt-verify/"
_CSS = ("body{font-family:system-ui,sans-serif;max-width:420px;margin:40px auto;padding:0 16px;color:#111}"
        "h1{font-size:1.2rem}dl{margin:16px 0}dt{color:#555;font-size:.85rem;margin-top:10px}"
        "dd{margin:0;font-weight:600}.ok{color:#0a7d33}.bad{color:#b42318}small{color:#555}")


class ReceiptVerifyThrottle(AnonRateThrottle):
    scope = "receipt_verify"


def make_token(payment_id):
    return signing.dumps(int(payment_id), salt=SALT, compress=False)


def read_token(token):
    """Returns the payment id, or None. No max_age: printed QR codes must keep working."""
    if not token or len(token) > 200:
        return None
    try:
        return int(signing.loads(token, salt=SALT))
    except (signing.BadSignature, TypeError, ValueError):
        return None


def verify_url(request, payment):
    return request.build_absolute_uri(f"{PATH}{make_token(payment.id)}/")


def qr_svg(url):
    from reportlab.graphics import renderSVG
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    widget = QrCodeWidget(url)
    b = widget.getBounds()
    size = 120
    d = Drawing(size, size, transform=[size / (b[2] - b[0]), 0, 0, size / (b[3] - b[1]), 0, 0])
    d.add(widget)
    svg = renderSVG.drawToString(d)
    if isinstance(svg, bytes):
        svg = svg.decode("utf-8")
    return svg[svg.index("<svg"):]


def verify_fields(request, payment):
    """Extra fields for the receipt JSON. A QR failure must never break the receipt."""
    url = verify_url(request, payment)
    try:
        svg = qr_svg(url)
    except Exception:
        svg = ""
    return {"verify_url": url, "qr_svg": svg}


def _page(ok, heading, rows, note, status):
    items = "".join(f"<dt>{escape(k)}</dt><dd>{escape(v)}</dd>" for k, v in rows)
    html = ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<meta name='robots' content='noindex'><title>Receipt check</title>"
            f"<style>{_CSS}</style></head><body>"
            f"<h1 class='{'ok' if ok else 'bad'}'>{escape(heading)}</h1>"
            f"<dl>{items}</dl><small>{escape(note)}</small></body></html>")
    resp = HttpResponse(html, status=status, content_type="text/html; charset=utf-8")
    resp["Cache-Control"] = "no-store"
    resp["X-Robots-Tag"] = "noindex"
    return resp


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([ReceiptVerifyThrottle])
def receipt_verify(request, token):
    """Public. Confirms a receipt was issued; never shows learner details."""
    pid = read_token(token)
    payment = None
    if pid is not None:
        payment = FeePayment.objects.select_related("student_fee__student__school").filter(pk=pid).first()
    if payment is None:
        return _page(False, "Not valid",
                     [],
                     "This code was not issued by Marian, or it was changed. Please check with the school.", 404)
    school = payment.student_fee.student.school
    try:
        when = timezone.localtime(payment.paid_at)
    except ValueError:
        when = payment.paid_at
    rows = [
        ("Receipt number", f"RCPT-{school.code}-{payment.id:06d}"),
        ("School", school.name),
        ("Amount", f"{school.currency or 'KES'} {payment.amount:,.2f}"),
        ("Date", when.strftime("%d %b %Y")),
    ]
    return _page(True, "Valid receipt", rows,
                 "This confirms the school issued this receipt. It does not show the current fee balance.", 200)
