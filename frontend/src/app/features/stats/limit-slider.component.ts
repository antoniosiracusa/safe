import { ChangeDetectionStrategy, Component, inject, input, signal, OnInit } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { TranslocoDirective } from '@jsverse/transloco';

/** Slider "mostra i primi N" con debounce, riflesso nella URL (es. `slopes_limit`). */
@Component({
  selector: 'safe-limit-slider',
  imports: [TranslocoDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="slider" *transloco="let t">
      <label [for]="'slider-' + param()">{{ t(labelKey()) }}</label>
      <input type="range" [id]="'slider-' + param()" [min]="min()" [max]="max()" [value]="value()" (input)="onInput($any($event.target).valueAsNumber)" />
      <output [for]="'slider-' + param()">{{ value() }}</output>
    </div>
  `,
  styles: `
    .slider { display: flex; align-items: center; gap: 0.75rem; padding: 0 0.25rem; font-size: 0.85rem; color: var(--p-text-muted-color); }
    input[type='range'] { width: 200px; }
    output { font-variant-numeric: tabular-nums; color: var(--p-text-color); min-width: 2ch; }
  `,
})
export class LimitSliderComponent implements OnInit {
  readonly param = input.required<string>();
  readonly labelKey = input.required<string>();
  readonly default = input(20);
  readonly min = input(1);
  readonly max = input(100);

  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private timer: ReturnType<typeof setTimeout> | null = null;

  readonly value = signal<number>(20);

  ngOnInit(): void {
    const raw = this.route.snapshot.queryParamMap.get(this.param());
    const n = raw ? Number(raw) : this.default();
    this.value.set(Number.isFinite(n) && n >= this.min() && n <= this.max() ? n : this.default());
  }

  onInput(n: number): void {
    if (!Number.isFinite(n)) return;
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.value.set(n);
      void this.router.navigate([], { queryParams: { [this.param()]: n === this.default() ? null : n }, queryParamsHandling: 'merge' });
    }, 300);
  }
}
