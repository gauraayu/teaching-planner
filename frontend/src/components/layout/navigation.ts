import {
  BarChart3, BookOpen, CalendarClock, BookOpenCheck, Building2, CalendarDays, CalendarRange, ClipboardCheck, ClipboardList, DoorOpen, FileSpreadsheet, FileWarning,
  GraduationCap, History, LayoutDashboard, LineChart, ListChecks, Radio, Settings, ShieldCheck, TriangleAlert, Users, UserSquare2, Workflow,
  type LucideIcon,
} from 'lucide-react'
import type { Role } from '@/types/domain'

export type NavItem = { to: string; label: string; icon: LucideIcon; permission?: string; end?: boolean; badgeKey?: string }
export type NavGroup = { label?: string; items: NavItem[] }

export const NAVIGATION: Record<'admin' | 'professor' | 'verification' | 'om', NavGroup[]> = {
  admin: [
    { items: [{ to: '/admin/dashboard', label: 'Dashboard', icon: LayoutDashboard }] },
    {
      label: 'Academic management',
      items: [
        { to: '/admin/academic-setup', label: 'Academic Setup', icon: Building2, permission: 'academic.manage' },
        { to: '/admin/subjects', label: 'Subjects', icon: BookOpen },
        { to: '/admin/faculty-mapping', label: 'Faculty Mapping', icon: UserSquare2 },
      ],
    },
    {
      label: 'Teaching management',
      items: [
        { to: '/admin/sprint-plans', label: 'Sprint Plans', icon: CalendarClock, permission: 'plans.manage' },
        { to: '/admin/plans', label: 'Subjects & Curriculum', icon: ClipboardList },
        { to: '/admin/imports', label: 'Import Curriculum', icon: FileSpreadsheet, permission: 'plans.import' },
        { to: '/admin/sprint-plan', label: 'Weekly Sprint Plan', icon: CalendarRange, permission: 'plans.manage' },
        { to: '/admin/sprint-history', label: 'Sprint Meeting History', icon: History, permission: 'plans.manage' },
        { to: '/admin/schedule', label: 'Schedule', icon: CalendarDays },
      ],
    },
    {
      label: 'Monitoring',
      items: [
        { to: '/admin/monitor', label: 'Workflow Monitor', icon: Workflow },
        { to: '/admin/progress', label: 'Progress', icon: LineChart },
        { to: '/admin/verification', label: 'Verification', icon: ShieldCheck },
        { to: '/admin/reports', label: 'Reports', icon: BarChart3 },
      ],
    },
    {
      label: 'System',
      items: [
        { to: '/admin/users', label: 'User Management', icon: Users, permission: 'users.manage' },
        { to: '/admin/settings', label: 'Settings', icon: Settings },
      ],
    },
  ],
  professor: [
    { label: 'Overview', items: [{ to: '/professor/dashboard', label: 'Dashboard', icon: LayoutDashboard }] },
    {
      label: 'Teaching',
      items: [
        { to: '/professor/today', label: "Today's Classes", icon: DoorOpen },
        { to: '/professor/sprint-plan', label: 'Sprint Plan', icon: CalendarRange },
        { to: '/professor/schedule', label: 'My Schedule', icon: CalendarDays },
      ],
    },
    {
      label: 'Tracking',
      items: [
        { to: '/professor/courses', label: 'Course Progress', icon: GraduationCap },
        { to: '/professor/corrections', label: 'Correction Requests', icon: FileWarning, badgeKey: 'corrections' },
      ],
    },
  ],
  verification: [
    { items: [{ to: '/verification/dashboard', label: 'Dashboard', icon: LayoutDashboard }] },
    {
      label: 'Verification',
      items: [
        { to: '/verification/pending', label: 'Pending Review', icon: ClipboardCheck, badgeKey: 'pending' },
        { to: '/verification/sprint-plan', label: 'Sprint Plan', icon: CalendarRange },
        { to: '/verification/verified', label: 'Verified Records', icon: BookOpenCheck },
        { to: '/verification/corrections', label: 'Correction Requests', icon: FileWarning },
      ],
    },
    {
      label: 'Monitoring',
      items: [
        { to: '/verification/subjects', label: 'Subjects', icon: ListChecks },
        { to: '/verification/faculty-progress', label: 'Faculty Progress', icon: Users },
        { to: '/verification/reports', label: 'Reports', icon: BarChart3 },
      ],
    },
  ],
  om: [
    { items: [{ to: '/om/dashboard', label: 'Dashboard', icon: LayoutDashboard }] },
    {
      label: 'Live operations',
      items: [
        { to: '/om/today', label: "Today's Classes", icon: DoorOpen },
        { to: '/om/running', label: 'Currently Running', icon: Radio, badgeKey: 'running' },
        { to: '/om/schedule', label: 'Class Schedule', icon: CalendarDays },
        { to: '/om/sprint-plan', label: 'Sprint Plan', icon: CalendarRange },
      ],
    },
    {
      label: 'Records',
      items: [
        { to: '/om/records', label: 'Operations Records', icon: History },
        { to: '/om/faculty', label: 'Faculty Records', icon: Users },
      ],
    },
    {
      label: 'Verification',
      items: [
        { to: '/om/final-verification', label: 'Final Verification', icon: ShieldCheck, badgeKey: 'pending' },
        { to: '/om/review-required', label: 'Review Required', icon: TriangleAlert },
      ],
    },
    { label: 'Reports', items: [{ to: '/om/reports', label: 'Operational Reports', icon: BarChart3 }] },
  ],
}

export const AREA_BY_ROLE: Record<Role, keyof typeof NAVIGATION> = {
  ADMIN: 'admin',
  PROFESSOR: 'professor',
  CL_CH: 'verification',
  OM: 'om',
}

export const ROLE_LABEL: Record<Role, string> = {
  ADMIN: 'Administrator',
  PROFESSOR: 'Professor',
  CL_CH: 'CL/CH · Academic Verifier',
  OM: 'Operations Manager',
}
