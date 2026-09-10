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
    await this.oauth.loadDiscoveryDocumentAndTryLogin();
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

  accountUrl(): string {
    return `${this.appConfig.config.oidc.issuer}/account`;
  }
}
