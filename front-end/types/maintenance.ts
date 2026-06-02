export type MaintenancePublicStatus = "none" | "scheduled" | "active"
export type MaintenanceWindowStatus = "scheduled" | "active" | "cancelled" | "completed"

export type MaintenanceStatusResponse = {
  status: MaintenancePublicStatus
  message: string
  eta: string
  title?: string
  id?: string | null
  starts_at?: string | null
  ends_at?: string | null
  version?: string | null
}

export type MaintenanceWindow = {
  id: string
  status: MaintenanceWindowStatus
  title: string
  message: string
  starts_at: string
  ends_at?: string | null
  eta?: string | null
  created_by?: string | null
  created_by_email?: string | null
  created_at: string
  updated_at: string
  activated_at?: string | null
  cancelled_at?: string | null
  completed_at?: string | null
}
