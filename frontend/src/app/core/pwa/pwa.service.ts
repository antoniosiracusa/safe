import { Injectable, inject, signal } from '@angular/core';
import { SwUpdate, VersionReadyEvent } from '@angular/service-worker';
import { filter } from 'rxjs';

/** Evento `beforeinstallprompt` (Chrome/Android): non tipizzato nel DOM standard. */
interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

/**
 * Stato dell'app installabile (M8): rete, modalità standalone, possibilità di installazione,
 * aggiornamenti del service worker. Nessuna dipendenza dal backend.
 */
@Injectable({ providedIn: 'root' })
export class PwaService {
  private readonly updates = inject(SwUpdate);
  private installPrompt: BeforeInstallPromptEvent | null = null;

  /** `false` quando il browser dichiara di essere senza rete. */
  readonly online = signal(typeof navigator === 'undefined' ? true : navigator.onLine);
  /** Aperta dall'icona sulla schermata Home (finestra senza barra del browser). */
  readonly standalone = signal(this.detectStandalone());
  /** Installazione con un tocco disponibile (Android/Chrome). */
  readonly canPromptInstall = signal(false);
  /** Una nuova versione è pronta: ricaricare per applicarla. */
  readonly updateReady = signal(false);
  readonly isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !('MSStream' in window);

  constructor() {
    window.addEventListener('online', () => this.online.set(true));
    window.addEventListener('offline', () => this.online.set(false));
    window.addEventListener('beforeinstallprompt', (e) => {
      e.preventDefault();
      this.installPrompt = e as BeforeInstallPromptEvent;
      this.canPromptInstall.set(true);
    });
    window.addEventListener('appinstalled', () => {
      this.canPromptInstall.set(false);
      this.standalone.set(true);
    });
    if (this.updates.isEnabled) {
      this.updates.versionUpdates
        .pipe(filter((e): e is VersionReadyEvent => e.type === 'VERSION_READY'))
        .subscribe(() => this.updateReady.set(true));
      // controllo all'avvio e poi ogni 6 ore (l'app installata può restare aperta per giorni)
      void this.updates.checkForUpdate().catch(() => undefined);
      setInterval(() => void this.updates.checkForUpdate().catch(() => undefined), 6 * 60 * 60 * 1000);
    }
  }

  /** Mostra la finestra di installazione del browser (dove disponibile). */
  async promptInstall(): Promise<boolean> {
    if (!this.installPrompt) return false;
    await this.installPrompt.prompt();
    const { outcome } = await this.installPrompt.userChoice;
    this.installPrompt = null;
    this.canPromptInstall.set(false);
    return outcome === 'accepted';
  }

  /** Applica la nuova versione ricaricando la pagina. */
  async applyUpdate(): Promise<void> {
    try {
      await this.updates.activateUpdate();
    } finally {
      window.location.reload();
    }
  }

  private detectStandalone(): boolean {
    const nav = navigator as Navigator & { standalone?: boolean };
    return window.matchMedia?.('(display-mode: standalone)').matches || nav.standalone === true;
  }
}
