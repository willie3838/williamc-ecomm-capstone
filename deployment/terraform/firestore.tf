# Cloud Firestore Infrastructure for User Behavior, Engagement & Feedback Analytics

resource "google_firestore_database" "analytics_db" {
  project     = var.project_id
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  delete_protection_state = "DELETE_PROTECTION_DISABLED"
  deletion_policy         = "DELETE"

  depends_on = [google_project_service.required_apis]
}
