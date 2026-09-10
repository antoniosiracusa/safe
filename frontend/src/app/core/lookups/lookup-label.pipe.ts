import { Pipe, PipeTransform, inject } from '@angular/core';

import { LookupsService } from './lookups.service';

/** `{{ code | lookup:'cause' }}` → etichetta nella lingua attiva; null → "Non classificato".
 *  Impuro perché dipende da lingua e caricamento dei vocabolari (signals). */
@Pipe({ name: 'lookup', pure: false })
export class LookupLabelPipe implements PipeTransform {
  private readonly lookups = inject(LookupsService);

  transform(code: string | null | undefined, dimension: string): string {
    return this.lookups.label(dimension, code);
  }
}
