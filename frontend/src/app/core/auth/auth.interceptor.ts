import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';

import { AppConfigService } from '../config/app-config';
import { AuthService } from './auth.service';

/** Aggiunge il Bearer alle chiamate verso l'API; su 401 rimanda al login (token scaduto/revocato). */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  const config = inject(AppConfigService);
  const router = inject(Router);

  const isApi = req.url.startsWith(config.config.apiBaseUrl);
  const token = auth.accessToken;
  const request = isApi && token ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }) : req;

  return next(request).pipe(
    catchError((err: unknown) => {
      if (isApi && err instanceof HttpErrorResponse && err.status === 401) {
        const code = (err.error as { code?: string } | null)?.code;
        if (code === 'user_not_provisioned' || code === 'user_disabled') {
          void router.navigate(['/not-provisioned'], { state: { code } });
        } else {
          auth.login(router.url);
        }
      }
      return throwError(() => err);
    }),
  );
};
