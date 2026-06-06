use actix_web::{post, web::{Data, Json}, HttpResponse, Responder};
use argon2::{Argon2, PasswordHasher, password_hash::{SaltString, rand_core::OsRng}};

pub mod user;
use crate::AppState;
use user::CreateRequest;

pub const ML_ENGINEER: &str = "ML_ENGINEER";
pub const ANALYST:     &str = "ANALYST";
pub const VIEWER:      &str = "VIEWER";
pub const ADMIN:       &str = "ADMIN";

const VALID_ROLES: &[&str] = &[ML_ENGINEER, ANALYST, VIEWER, ADMIN];

#[post("/create")]
pub async fn create_user(
    db:      Data<AppState>,
    request: Json<CreateRequest>,
) -> impl Responder {
    let request = request.into_inner();

    let role = request.role
        .as_deref()
        .filter(|r| VALID_ROLES.contains(r))
        .unwrap_or(VIEWER)
        .to_string();

    let salt          = SaltString::generate(&mut OsRng);
    let password_hash = match Argon2::default()
        .hash_password(request.password.as_bytes(), &salt)
    {
        Ok(h)  => h.to_string(),
        Err(_) => return HttpResponse::InternalServerError()
            .body("Failed to hash password"),
    };

    let result = sqlx::query(
        "INSERT INTO users (username, email, password_hash, role)
         VALUES ($1, $2, $3, $4)",
    )
    .bind(&request.name)
    .bind(&request.email)
    .bind(&password_hash)
    .bind(&role)
    .execute(&db.pool)
    .await;

    match result {
        Ok(_)  => HttpResponse::Created()
            .json(serde_json::json!({ "status": "user created" })),
        Err(e) => {
            let msg = e.to_string();
            if msg.contains("unique") || msg.contains("duplicate") {
                HttpResponse::Conflict()
                    .body("Username or email already exists")
            } else {
                HttpResponse::InternalServerError()
                    .body("Failed to create user")
            }
        }
    }
}