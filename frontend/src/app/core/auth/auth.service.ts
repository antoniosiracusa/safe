import { Injectable, inject } from '@angular/core';
import { Router } from '@angular/router';
import { AuthConfig, OAuthService } from 'angular-oauth2-oidc';

import { AppConfigService } from '../config/app-config';

/** Autenticazione delegata all'identity provider OIDC (Keycloak): Authorization Code + PKCE.
 *  Nessuna password transita dall'applicazione. */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly oauth = inject(OAuthService);
  private readonly appConfig = inject(AppConfigService);
  private readonly router = inject(Router);

  async init(): Promise<void> {
    const { oidc } = this.appConfig.config;
    const config: AuthConfig = {
      issuer: oidc.issuer,
      clientId: oidc.clientId,
      redirectUri: `${window.location.origin}/`,
      postLogoutRedirectUri: `${window.location.origin}/`,
      responseType: 'code',
      scope: 'openid profile email',
      requireHttps: oidc.issuer.startsWith('https://') ? 'remoteOnly' : false,
      strictDiscoveryDocumentValidation: false,
      useSilentRefresh: false,
      timeoutFactor: 0.75,
      showDebugInformation: false,
      clearHashAfterLogin: true,
    };
    this.oauth.configure(config);
    this.oauth.setupAutomaticSilentRefresh();
    try {
      await this.oauth.loadDiscoveryDocumentAndTryLogin();
    } catch (err) {
      // Senza rete (app installata, M8) il documento di discovery non è raggiungibile: se in memoria c'è
      // ancora un token valido l'app parte in modalità offline, altrimenti l'errore è reale.
      if (navigator.onLine || !this.oauth.hasValidAccessToken()) throw err;
      console.warn('OIDC discovery non disponibile offline: si prosegue con il token in memoria');
      return;
    }
    const target = this.oauth.state ? decodeURIComponent(this.oauth.state) : null;
    if (target && target.startsWith('/')) {
      // ritorno dal login: torniamo alla pagina richiesta (filtri inclusi)
      await this.router.navigateByUrl(target);
    }
  }

  get isLoggedIn(): boolean {
    return this.oauth.hasValidAccessToken();
  }

  get accessToken(): string | null {
    return this.oauth.hasValidAccessToken() ? this.oauth.getAccessToken() : null;
  }

  login(returnUrl: string): void {
    this.oauth.initCodeFlow(returnUrl);
  }

  logout(): void {
    this.oauth.logOut();
  }

  /** Console "account" di Keycloak, sezione sicurezza: cambio password, app di autenticazione, sessioni. */
  accountUrl(): string {
    return `${this.appConfig.config.oidc.issuer}/account/#/security/signing-in`;
  }

  /** Azione richiesta dall'utente (AIA di Keycloak): rimanda alla pagina di accesso con l'azione da
   *  eseguire, poi torna al portale. Non dipende dalla console "account". */
  requestAction(action: 'UPDATE_PASSWORD' | 'CONFIGURE_TOTP', returnUrl: string): void {
    this.oauth.initCodeFlow(returnUrl, { kc_action: action });
  }
}
