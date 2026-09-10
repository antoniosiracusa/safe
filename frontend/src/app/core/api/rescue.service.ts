import { HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { ApiService, Paginated } from './api.service';
import { EventDetail, EventRow, EventWrite, Person, PersonWrite, SkiArea, Slope, Zone } from './rescue.models';

export interface ListQuery {
  page: number;
  page_size: number;
  ordering?: string;
}

function withList(base: HttpParams, q: ListQuery, extra: Record<string, string | string[] | null | undefined>): HttpParams {
  let p = base.set('page', String(q.page)).set('page_size', String(q.page_size));
  if (q.ordering) p = p.set('ordering', q.ordering);
  for (const [k, v] of Object.entries(extra)) {
    if (v === null || v === undefined || v === '') continue;
    if (Array.isArray(v)) v.forEach((x) => (p = p.append(k, x)));
    else p = p.set(k, v);
  }
  return p;
}

@Injectable({ providedIn: 'root' })
export class RescueService {
  private readonly api = inject(ApiService);

  listEvents(global: HttpParams, q: ListQuery, extra: Record<string, string | string[] | null | undefined> = {}) {
    return this.api.get<Paginated<EventRow>>('events', withList(global, q, extra));
  }

  getEvent(id: string): Observable<EventDetail> {
    return this.api.get<EventDetail>(`events/${id}`);
  }

  createEvent(body: EventWrite): Observable<EventDetail> {
    return this.api.post<EventDetail>('events', body);
  }

  updateEvent(id: string, body: Partial<EventWrite>): Observable<EventDetail> {
    return this.api.patch<EventDetail>(`events/${id}`, body);
  }

  deleteEvent(id: string): Observable<void> {
    return this.api.delete<void>(`events/${id}`);
  }

  lockEvent(id: string): Observable<EventDetail> {
    return this.api.post<EventDetail>(`events/${id}/lock`, {});
  }

  unlockEvent(id: string, reason: string): Observable<EventDetail> {
    return this.api.post<EventDetail>(`events/${id}/unlock`, { reason });
  }

  addPerson(eventId: string, body: PersonWrite): Observable<Person> {
    return this.api.post<Person>(`events/${eventId}/persons`, body);
  }

  listPersons(global: HttpParams, q: ListQuery, extra: Record<string, string | string[] | null | undefined> = {}) {
    return this.api.get<Paginated<Person>>('persons', withList(global, q, extra));
  }

  getPerson(id: string): Observable<Person> {
    return this.api.get<Person>(`persons/${id}`);
  }

  updatePerson(id: string, body: PersonWrite): Observable<Person> {
    return this.api.patch<Person>(`persons/${id}`, body);
  }

  deletePerson(id: string): Observable<void> {
    return this.api.delete<void>(`persons/${id}`);
  }

  skiAreas(): Observable<SkiArea[]> {
    return this.api.get<SkiArea[]>('ski-areas');
  }

  zones(): Observable<Zone[]> {
    return this.api.get<Zone[]>('zones');
  }

  slopes(): Observable<Slope[]> {
    return this.api.get<Slope[]>('slopes');
  }
}
