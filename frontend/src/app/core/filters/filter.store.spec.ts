import { defaultFilters, parseFilters, seasonCodeFor, serializeFilters, toHttpParams } from './filter.store';

describe('filter.store helpers', () => {
  it('computes the ski season (1 June → 31 May)', () => {
    expect(seasonCodeFor(new Date(2026, 0, 18))).toBe('2025/2026');
    expect(seasonCodeFor(new Date(2026, 4, 31))).toBe('2025/2026');
    expect(seasonCodeFor(new Date(2026, 5, 1))).toBe('2026/2027');
  });

  it('defaults to the current season when no period is in the URL', () => {
    const f = parseFilters({}, new Date(2026, 8, 10));
    expect(f.season).toBe('2026/2027');
    expect(f.team).toEqual([]);
    expect(f.valid_only).toBeFalse();
  });

  it('parses multi-team, dates and flags from the query string', () => {
    const f = parseFilters({ team: ['a', 'b'], date_from: '2026-01-01', zone: 'z1', valid_only: 'true' });
    expect(f.team).toEqual(['a', 'b']);
    expect(f.season).toBeNull();
    expect(f.date_from).toBe('2026-01-01');
    expect(f.zone).toBe('z1');
    expect(f.valid_only).toBeTrue();
  });

  it('serializes to the same query string shape the API expects', () => {
    const f = { ...defaultFilters(new Date(2026, 0, 1)), team: ['a'], ski_area: 's', valid_only: true };
    expect(serializeFilters(f)).toEqual({
      team: ['a'],
      season: '2025/2026',
      date_from: null,
      date_to: null,
      ski_area: 's',
      zone: null,
      valid_only: 'true',
    });
    expect(toHttpParams(f).toString()).toBe('team=a&season=2025/2026&ski_area=s&valid_only=true');
  });
});
