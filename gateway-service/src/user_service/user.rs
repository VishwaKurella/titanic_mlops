use serde::Deserialize;
use sqlx::FromRow;

#[derive(Deserialize)]
pub struct CreateRequest {
    pub name:     String,
    pub email:    String,
    pub password: String,
    pub role:     Option<String>,
}

#[derive(FromRow)]
pub struct UserRow {
    pub password_hash: String,
    pub role:          String,
}