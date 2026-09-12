import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { SessionService } from '../session/session.service';
import { AuthService } from './auth.service';

/** Richiede un token valido e una sessione applicativa (/me) caricata. */
export const authGuard: CanActivateFn = async (_route, state) => {
  const auth = inject(AuthService);
  const session = inject(SessionService);
  const router = inject(Router);

  if (!auth.isLoggedIn) {
    // senza rete il login non può avvenire: pagina di attesa (la coda della modalità pista resta al sicuro)
    if (!navigator.onLine) return router.createUrlTree(['/offline']);
    auth.login(state.url);
    return false;
  }
  try {
    await session.ensureLoaded();
    return true;
  } catch {
    return router.createUrlTree(['/not-provisioned']);
  }
};
