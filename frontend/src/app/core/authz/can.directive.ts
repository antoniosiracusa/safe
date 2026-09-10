import { Directive, Input, TemplateRef, ViewContainerRef, effect, inject, input } from '@angular/core';

import { LockedPanelComponent } from '../../shared/locked-panel/locked-panel.component';
import { SessionService } from '../session/session.service';

/**
 * `*safeCan="'events.view'"`: se l'utente ha il permesso rende il contenuto; altrimenti, per
 * regola di prodotto, la funzione resta VISIBILE ma bloccata (pannello con messaggio).
 * `*safeCan="'x'; mode: 'hide'"` nasconde del tutto (per pulsanti/azioni).
 */
@Directive({ selector: '[safeCan]' })
export class CanDirective {
  private readonly template = inject(TemplateRef<unknown>);
  private readonly container = inject(ViewContainerRef);
  private readonly session = inject(SessionService);

  readonly safeCan = input.required<string | string[]>();
  readonly safeCanMode = input<'lock' | 'hide'>('lock');

  @Input() safeCanTitle?: string;

  constructor() {
    effect(() => {
      const codes = Array.isArray(this.safeCan()) ? (this.safeCan() as string[]) : [this.safeCan() as string];
      const allowed = this.session.can(...codes);
      this.container.clear();
      if (allowed) {
        this.container.createEmbeddedView(this.template);
      } else if (this.safeCanMode() === 'lock') {
        const ref = this.container.createComponent(LockedPanelComponent);
        ref.setInput('missing', codes.filter((c) => !this.session.can(c)));
        if (this.safeCanTitle) ref.setInput('title', this.safeCanTitle);
      }
    });
  }
}
