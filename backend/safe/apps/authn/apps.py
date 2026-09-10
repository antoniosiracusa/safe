from django.apps import AppConfig


class AuthnConfig(AppConfig):
    name = "safe.apps.authn"
    label = "authn"
    verbose_name = "SAFE authentication (OIDC)"
