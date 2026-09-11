from django.urls import path

from . import views as v

urlpatterns = [
    path("crypto/company-key", v.CompanyKeyView.as_view(), name="crypto-company-key"),
    path("crypto/company-key/rotate", v.CompanyKeyRotateView.as_view(), name="crypto-rotate"),
    path("crypto/company-key/rewrap", v.RewrapView.as_view(), name="crypto-rewrap"),
    path("crypto/my-key", v.MyKeyView.as_view(), name="crypto-my-key"),
    path("crypto/grants", v.GrantsView.as_view(), name="crypto-grants"),
    path("crypto/grants/<uuid:user_id>", v.GrantDetailView.as_view(), name="crypto-grant-detail"),
    path("crypto/recovery", v.RecoveryView.as_view(), name="crypto-recovery"),
    path(
        "crypto/users/<uuid:user_id>/public-key", v.UserPublicKeyView.as_view(), name="crypto-user-public-key"
    ),
]
