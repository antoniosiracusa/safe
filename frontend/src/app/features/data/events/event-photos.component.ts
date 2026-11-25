import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, DestroyRef, computed, effect, inject, input, output, signal, untracked } from '@angular/core';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { ConfirmationService, MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { SkeletonModule } from 'primeng/skeleton';
import { firstValueFrom } from 'rxjs';

import { errorMessage } from '../../../core/api/errors';
import { KeyStoreService } from '../../../core/crypto/key-store.service';
import { EventPhoto, MAX_PHOTOS_PER_EVENT, PhotosService } from '../../../core/photos/photos.service';
import { KeyDialogComponent } from '../../../layout/key-dialog/key-dialog.component';

/** Foto dell'evento nel dettaglio: elenco, caricamento (ridotte e cifrate qui), visione con la chiave
 *  sbloccata, eliminazione. Le immagini decifrate restano solo in memoria (URL temporanei). */
@Component({
  selector: 'safe-event-photos',
  imports: [DatePipe, TranslocoDirective, ButtonModule, DialogModule, SkeletonModule, KeyDialogComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <ng-container *transloco="let t">
      <div class="bar">
        <span class="count">{{ t('photos.count', { n: photos().length, max: max }) }}</span>
        @if (canAdd()) {
          <input #picker type="file" accept="image/*" multiple hidden (change)="onPick(picker)" />
          <p-button [label]="t('photos.add')" icon="pi pi-camera" size="small" [outlined]="true" [loading]="uploading() > 0" (onClick)="picker.click()" />
        }
      </div>
      <p class="hint"><i class="pi pi-lock" aria-hidden="true"></i> {{ t('photos.hint') }}</p>
      @if (uploading() > 0) { <p class="muted">{{ t('photos.uploading', { n: uploading() }) }}</p> }

      @if (loading()) {
        <p-skeleton height="6rem" />
      } @else if (!photos().length) {
        <p class="muted">{{ t('photos.none') }}</p>
      } @else if (!keyStore.unlocked()) {
        <p class="locked">{{ t('photos.locked') }}</p>
        <p-button [label]="t('photos.unlock')" icon="pi pi-lock-open" size="small" (onClick)="keyDialog.set(true)" />
      } @else if (!keyStore.canDecrypt()) {
        <p class="locked">{{ t('photos.no_grant') }}</p>
      } @else {
        <div class="grid">
          @for (p of photos(); track p.id; let i = $index) {
            <figure>
              @if (urls()[p.id]; as url) {
                @if (url === 'error') {
                  <div class="tile missing">{{ t('photos.unavailable') }}</div>
                } @else {
                  <button type="button" class="tile" (click)="zoom.set(url)" [attr.aria-label]="t('photos.open', { n: i + 1 })"><img [src]="url" alt="" /></button>
                }
              } @else {
                <p-skeleton styleClass="tile" />
              }
              <figcaption>
                <span>{{ i + 1 }} · {{ p.created_at | date: 'dd/MM HH:mm' }}@if (p.created_by) { · {{ p.created_by }} }</span>
                @if (canEdit()) {
                  <p-button icon="pi pi-trash" [text]="true" size="small" severity="danger" [attr.aria-label]="t('photos.delete')" (onClick)="remove(p)" />
                }
              </figcaption>
            </figure>
          }
        </div>
      }

      <p-dialog [visible]="!!zoom()" (visibleChange)="!$event && zoom.set(null)" [modal]="true" [dismissableMask]="true" appendTo="body" [style]="{ width: 'min(96vw, 1100px)' }" [header]="t('photos.title')">
        @if (zoom(); as z) { <img class="zoomed" [src]="z" alt="" /> }
      </p-dialog>
      <safe-key-dialog [visible]="keyDialog()" (closed)="keyDialog.set(false)" />
    </ng-container>
  `,
  styles: `
    .bar { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; margin: 0.5rem 0; }
    .count { font-weight: 600; }
    .hint { font-size: 0.82rem; color: var(--p-text-muted-color); margin: 0 0 0.75rem; display: flex; gap: 0.35rem; align-items: baseline; }
    .muted { color: var(--p-text-muted-color); }
    .locked { margin: 0.25rem 0 0.5rem; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 0.75rem; }
    figure { margin: 0; }
    .tile { display: block; width: 100%; aspect-ratio: 4 / 3; border: 1px solid var(--p-surface-200); border-radius: 6px; overflow: hidden; padding: 0; background: var(--p-surface-100); cursor: zoom-in; }
    .tile img { width: 100%; height: 100%; object-fit: cover; display: block; }
    .tile.missing { display: flex; align-items: center; justify-content: center; color: var(--p-text-muted-color); font-size: 0.85rem; cursor: default; }
    figcaption { display: flex; align-items: center; justify-content: space-between; font-size: 0.8rem; color: var(--p-text-muted-color); }
    .zoomed { width: 100%; height: auto; display: block; }
  `,
})
export class EventPhotosComponent {
  readonly eventId = input.required<string>();
  readonly canEdit = input(false);
  readonly countChanged = output<number>();

  readonly keyStore = inject(KeyStoreService);
  private readonly photosApi = inject(PhotosService);
  private readonly confirm = inject(ConfirmationService);
  private readonly messages = inject(MessageService, { optional: true });
  private readonly transloco = inject(TranslocoService);

  readonly max = MAX_PHOTOS_PER_EVENT;
  readonly photos = signal<EventPhoto[]>([]);
  readonly loading = signal(true);
  readonly uploading = signal(0);
  /** id foto → URL dell'immagine decifrata ('error' se non apribile) */
  readonly urls = signal<Record<string, string>>({});
  readonly zoom = signal<string | null>(null);
  readonly keyDialog = signal(false);
  readonly canAdd = computed(() => this.canEdit() && this.photos().length + this.uploading() < this.max);

  constructor() {
    void this.keyStore.ensureLoaded();
    effect(() => {
      const id = this.eventId();
      untracked(() => void this.load(id));
    });
    // appena la chiave è sbloccata (anche dopo) si decifrano le foto ancora chiuse
    effect(() => {
      if (this.keyStore.canDecrypt() && this.photos().length) untracked(() => void this.decryptMissing());
    });
    inject(DestroyRef).onDestroy(() => this.revokeAll());
  }

  private async load(eventId: string): Promise<void> {
    this.loading.set(true);
    this.revokeAll();
    try {
      this.photos.set(await firstValueFrom(this.photosApi.list(eventId)));
    } catch {
      this.photos.set([]);
    } finally {
      this.loading.set(false);
    }
  }

  private async decryptMissing(): Promise<void> {
    for (const p of this.photos()) {
      if (this.urls()[p.id]) continue;
      let url = 'error';
      try {
        const bytes = await this.photosApi.open(p);
        url = URL.createObjectURL(new Blob([bytes as BlobPart], { type: 'image/jpeg' }));
      } catch {
        /* contenuto mancante o non decifrabile: riquadro "non disponibile" */
      }
      if (!this.photos().some((x) => x.id === p.id)) {
        if (url !== 'error') URL.revokeObjectURL(url);
        continue;
      }
      this.urls.update((u) => ({ ...u, [p.id]: url }));
    }
  }

  async onPick(input: HTMLInputElement): Promise<void> {
    const files = Array.from(input.files ?? []);
    input.value = '';
    const free = this.max - this.photos().length - this.uploading();
    if (files.length > free) this.messages?.add({ severity: 'warn', summary: this.transloco.translate('photos.limit', { max: this.max }) });
    for (const file of files.slice(0, Math.max(0, free))) {
      this.uploading.update((n) => n + 1);
      try {
        const prepared = await this.photosApi.prepare(file);
        const saved = await firstValueFrom(this.photosApi.upload(this.eventId(), prepared));
        // l'anteprima in chiaro c'è già: la foto si vede subito senza riscaricarla
        this.urls.update((u) => ({ ...u, [saved.id]: URL.createObjectURL(prepared.preview) }));
        this.photos.update((list) => [...list, saved]);
        this.countChanged.emit(this.photos().length);
      } catch (err) {
        const code = err instanceof Error ? err.message : '';
        const detail = code === 'company_key_missing' || code === 'photo_unreadable' ? this.transloco.translate('photos.' + code) : errorMessage(err, '');
        this.messages?.add({ severity: 'error', summary: this.transloco.translate('photos.error_upload'), detail });
      } finally {
        this.uploading.update((n) => n - 1);
      }
    }
  }

  remove(p: EventPhoto): void {
    this.confirm.confirm({
      message: this.transloco.translate('photos.delete_confirm'),
      header: this.transloco.translate('photos.delete'),
      icon: 'pi pi-exclamation-triangle',
      acceptButtonProps: { label: this.transloco.translate('common.delete'), severity: 'danger' },
      rejectButtonProps: { label: this.transloco.translate('common.cancel'), severity: 'secondary', text: true },
      accept: () => {
        this.photosApi.remove(p.id).subscribe({
          next: () => {
            const url = this.urls()[p.id];
            if (url && url !== 'error') URL.revokeObjectURL(url);
            this.photos.update((list) => list.filter((x) => x.id !== p.id));
            this.countChanged.emit(this.photos().length);
          },
          error: (err) => this.messages?.add({ severity: 'error', summary: this.transloco.translate('common.save_error'), detail: errorMessage(err, '') }),
        });
      },
    });
  }

  private revokeAll(): void {
    for (const url of Object.values(this.urls())) if (url !== 'error') URL.revokeObjectURL(url);
    this.urls.set({});
  }
}
