import { HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  AdminLift, AdminSkiArea, AdminSlope, AdminUser, AdminZone, CompanyInfo, Device, EnrollmentCode, InviteRequest,
  LookupAdminItem, PermissionsPut, Role, TeamAdmin, UserPatch,
} from './admin.models';
import { ApiService } from './api.service';

function params(obj: Record<string, string | boolean | null | undefined>): HttpParams {
  let p = new HttpParams();
  for (const [k, v] of Object.entries(obj)) {
    if (v !== null && v !== undefined && v !== '') p = p.set(k, String(v));
  }
  return p;
}

/** API di gestione (M6): utenti, ruoli, squadre, dispositivi, territorio, vocabolari, società. */
@Injectable({ providedIn: 'root' })
export class AdminService {
  private readonly api = inject(ApiService);

  // utenti
  users(q: { status?: string; search?: string; team?: string } = {}): Observable<AdminUser[]> {
    return this.api.get<AdminUser[]>('users', params(q));
  }
  invite(body: InviteRequest): Observable<AdminUser> {
    return this.api.post<AdminUser>('users/invite', body);
  }
  patchUser(id: string, body: UserPatch): Observable<AdminUser> {
    return this.api.patch<AdminUser>(`users/${id}`, body);
  }
  resendInvite(id: string): Observable<AdminUser> {
    return this.api.post<AdminUser>(`users/${id}/resend-invite`, {});
  }
  disableUser(id: string): Observable<AdminUser> {
    return this.api.post<AdminUser>(`users/${id}/disable`, {});
  }
  enableUser(id: string): Observable<AdminUser> {
    return this.api.post<AdminUser>(`users/${id}/enable`, {});
  }
  putPermissions(id: string, body: PermissionsPut): Observable<AdminUser> {
    return this.api.put<AdminUser>(`users/${id}/permissions`, body);
  }
  roles(): Observable<Role[]> {
    return this.api.get<Role[]>('roles');
  }
  createRole(body: Omit<Role, 'id' | 'is_system' | 'is_custom'>): Observable<Role> {
    return this.api.post<Role>('roles', body);
  }

  // squadre
  teams(includeInactive = true): Observable<TeamAdmin[]> {
    return this.api.get<TeamAdmin[]>('teams', params({ include_inactive: includeInactive }));
  }
  createTeam(body: { name: string; body: string | null }): Observable<TeamAdmin> {
    return this.api.post<TeamAdmin>('teams', body);
  }
  patchTeam(id: string, body: Partial<{ name: string; body: string | null; is_active: boolean }>): Observable<TeamAdmin> {
    return this.api.patch<TeamAdmin>(`teams/${id}`, body);
  }
  deactivateTeam(id: string): Observable<void> {
    return this.api.delete<void>(`teams/${id}`);
  }

  // dispositivi
  devices(status?: string): Observable<Device[]> {
    return this.api.get<Device[]>('devices', params({ status }));
  }
  deviceSummary(): Observable<Record<string, number>> {
    return this.api.get<Record<string, number>>('devices/summary');
  }
  enrollmentCode(): Observable<EnrollmentCode> {
    return this.api.post<EnrollmentCode>('devices/enrollment-code', {});
  }
  authorizeDevice(id: string): Observable<Device> {
    return this.api.post<Device>(`devices/${id}/authorize`, {});
  }
  renameDevice(id: string, name: string): Observable<Device> {
    return this.api.patch<Device>(`devices/${id}`, { name });
  }
  revokeDevice(id: string): Observable<void> {
    return this.api.delete<void>(`devices/${id}`);
  }

  // territorio
  skiAreas(): Observable<AdminSkiArea[]> {
    return this.api.get<AdminSkiArea[]>('ski-areas', params({ include_inactive: true }));
  }
  zones(skiArea?: string): Observable<AdminZone[]> {
    return this.api.get<AdminZone[]>('zones', params({ include_inactive: true, ski_area: skiArea }));
  }
  slopes(zone?: string): Observable<AdminSlope[]> {
    return this.api.get<AdminSlope[]>('slopes', params({ include_inactive: true, zone }));
  }
  lifts(skiArea?: string): Observable<AdminLift[]> {
    return this.api.get<AdminLift[]>('lifts', params({ include_inactive: true, ski_area: skiArea }));
  }
  save<T>(resource: 'ski-areas' | 'zones' | 'slopes' | 'lifts', id: string | null, body: Record<string, unknown>): Observable<T> {
    return id ? this.api.patch<T>(`${resource}/${id}`, body) : this.api.post<T>(resource, body);
  }
  deactivate(resource: 'ski-areas' | 'zones' | 'slopes' | 'lifts', id: string): Observable<void> {
    return this.api.delete<void>(`${resource}/${id}`);
  }

  // vocabolari
  lookupValues(dimension: string): Observable<LookupAdminItem[]> {
    return this.api.get<LookupAdminItem[]>(`lookups/${dimension}`);
  }
  createLookup(dimension: string, body: Record<string, unknown>): Observable<LookupAdminItem> {
    return this.api.post<LookupAdminItem>(`lookups/${dimension}`, body);
  }
  patchLookup(dimension: string, id: string, body: Record<string, unknown>): Observable<LookupAdminItem> {
    return this.api.patch<LookupAdminItem>(`lookups/${dimension}/${id}`, body);
  }

  // società
  company(): Observable<CompanyInfo> {
    return this.api.get<CompanyInfo>('company');
  }
  patchCompany(body: Record<string, unknown>): Observable<CompanyInfo> {
    return this.api.patch<CompanyInfo>('company', body);
  }
}
