import { DatePipe, DecimalPipe, JsonPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, effect, inject, input, output, signal, untracked } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { TranslocoDirective, TranslocoService } from '@jsverse/transloco';
import { ConfirmationService, MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { DialogModule } from 'primeng/dialog';
import { DrawerModule } from 'primeng/drawer';
import { SkeletonModule } from 'primeng/skeleton';
import { TabsModule } from 'primeng/tabs';
import { TextareaModule } from 'primeng/textarea';
import { TooltipModule } from 'primeng/tooltip';

import { EventDetail, Person } from '../../../core/api/rescue.models';
import { RescueService } from '../../../core/api/rescue.service';
import { CanDirective } from '../../../core/authz/can.directive';
import { LookupLabelPipe } from '../../../core/lookups/lookup-label.pipe';
import { SessionService } from '../../../core/session/session.service';
import { PdfButtonComponent } from '../../../shared/ui/pdf-button.component';
import { StateTagComponent } from '../../../shared/ui/state-tag.component';
import { PersonFormComponent } from '../persons/person-form.component';
import { EventFormComponent } from './event-form.component';

/** Drawer laterale: dettaglio evento (Dati, Persone, Storico), modifica, blocco/sblocco, eliminazione,
 *  oppure creazione di un nuovo evento. */
@Component({
  selector: 'safe-event-drawer',
  imports: [
    DatePipe, DecimalPipe, JsonPipe,
    FormsModule, TranslocoDirective, DrawerModule, TabsModule, ButtonModule, DialogModule, ConfirmDialogModule,
    SkeletonModule, TextareaModule, TooltipModule, CanDirective, LookupLabelPipe, StateTagComponent, PdfButtonComponent,
    EventFormComponent, PersonFormComponent,
  ],
  providers: [ConfirmationService],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './event-drawer.component.html',
  styleUrl: './event-drawer.component.scss',
})
export class EventDrawerComponent {
  readonly eventId = input<string | null>(null);
  readonly createMode = input(false);
  readonly closed = output<boolean>();
  readonly created = output<string>();

  readonly session = inject(SessionService);
  private readonly rescue = inject(RescueService);
  private readonly confirm = inject(ConfirmationService);
  private readonly messages = inject(MessageService);
  private readonly transloco = inject(TranslocoService);

  readonly visible = signal(true);
  readonly event = signal<EventDetail | null>(null);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly editing = signal(false);
  readonly changed = signal(false);
  readonly tab = signal<string>('data');
  readonly unlockDialog = signal(false);
  readonly unlockReason = signal('');
  readonly personDialog = signal<{ person: Person | null } | null>(null);

  readonly canEditThis = computed(() => {
    const ev = this.event();
    if (!ev || ev.locked_at) return false;
    if (!this.session.can('events.edit')) return false;
    if (this.session.can('events.edit_any_team')) return true;
    return this.session.teams().some((t) => t.id === ev.team?.id);
  });

  constructor() {
    effect(() => {
      const id = this.eventId();
      untracked(() => {
        if (id) this.load(id);
        else this.event.set(null);
      });
    });
  }

  load(id: string): void {
    this.loading.set(true);
    this.error.set(null);
    this.rescue.getEvent(id).subscribe({
      next: (ev) => {
        this.event.set(ev);
        this.loading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        this.error.set(err.status === 404 ? 'not_found' : 'load_error');
      },
    });
  }

  onHide(): void {
    this.closed.emit(this.changed());
  }

  onSaved(ev: EventDetail): void {
    this.event.set(ev);
    this.editing.set(false);
    this.changed.set(true);
    this.messages.add({ severity: 'success', summary: this.transloco.translate('events.saved') });
  }

  onCreatedEvent(ev: EventDetail): void {
    this.changed.set(true);
    this.created.emit(ev.id);
  }

  lock(): void {
    const ev = this.event();
    if (!ev) return;
    this.rescue.lockEvent(ev.id).subscribe({
      next: (updated) => {
        this.event.set(updated);
        this.changed.set(true);
        this.messages.add({ severity: 'info', summary: this.transloco.translate('events.locked_ok') });
      },
      error: () => this.messages.add({ severity: 'error', summary: this.transloco.translate('common.save_error') }),
    });
  }

  unlock(): void {
    const ev = this.event();
    if (!ev || !this.unlockReason().trim()) return;
    this.rescue.unlockEvent(ev.id, this.unlockReason().trim()).subscribe({
      next: (updated) => {
        this.event.set(updated);
        this.changed.set(true);
        this.unlockDialog.set(false);
        this.unlockReason.set('');
        this.messages.add({ severity: 'info', summary: this.transloco.translate('events.unlocked_ok') });
      },
      error: () => this.messages.add({ severity: 'error', summary: this.transloco.translate('common.save_error') }),
    });
  }

  remove(): void {
    const ev = this.event();
    if (!ev) return;
    this.confirm.confirm({
      message: this.transloco.translate('events.delete_confirm'),
      header: this.transloco.translate('events.delete'),
      icon: 'pi pi-exclamation-triangle',
      acceptButtonProps: { label: this.transloco.translate('common.delete'), severity: 'danger' },
      rejectButtonProps: { label: this.transloco.translate('common.cancel'), severity: 'secondary', text: true },
      accept: () => {
        this.rescue.deleteEvent(ev.id).subscribe({
          next: () => {
            this.changed.set(true);
            this.visible.set(false);
            this.messages.add({ severity: 'success', summary: this.transloco.translate('events.deleted') });
          },
          error: () => this.messages.add({ severity: 'error', summary: this.transloco.translate('common.save_error') }),
        });
      },
    });
  }

  addPerson(): void {
    this.personDialog.set({ person: null });
  }

  editPerson(p: Person): void {
    this.personDialog.set({ person: p });
  }

  onPersonSaved(): void {
    const ev = this.event();
    this.personDialog.set(null);
    this.changed.set(true);
    if (ev) this.load(ev.id);
  }

  removePerson(p: Person): void {
    this.confirm.confirm({
      message: this.transloco.translate('persons.delete_confirm', { n: p.sequence }),
      header: this.transloco.translate('persons.delete'),
      icon: 'pi pi-exclamation-triangle',
      acceptButtonProps: { label: this.transloco.translate('common.delete'), severity: 'danger' },
      rejectButtonProps: { label: this.transloco.translate('common.cancel'), severity: 'secondary', text: true },
      accept: () => {
        this.rescue.deletePerson(p.id).subscribe({
          next: () => this.onPersonSaved(),
          error: () => this.messages.add({ severity: 'error', summary: this.transloco.translate('common.save_error') }),
        });
      },
    });
  }

  shortId(id: string): string {
    return id.slice(-8).toUpperCase();
  }

  means(p: Person): string[] {
    return [...p.evacuation_means].sort((a, b) => a.order - b.order).map((m) => m.mean);
  }
}
