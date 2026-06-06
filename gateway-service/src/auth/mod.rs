use actix_web::{post, web::{Data, Json}, HttpResponse, Responder};
use argon2::{Argon2, PasswordVerifier, password_hash::PasswordHash};
use jsonwebtoken::{encode, decode, Header, EncodingKey, DecodingKey, Validation};
use serde::{Deserialize, Serialize};
use chrono::{Utc, Duration};

use crate::AppState;

// ── JWT secret — in production load from env, never hardcode ──────────────────
const JWT_SECRET: &[u8] = b"change_this_in_production";
const JWT_EXPIRY_HOURS: i64 = 8;

// ── Claims embedded in the JWT ────────────────────────────────────────────────
#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Claims {
    pub sub:  String,   // user id (UUID as string)
    pub role: String,   // e.g. "ADMIN"
    pub exp:  usize,    // unix timestamp expiry
}

// ── Request / response shapes ─────────────────────────────────────────────────
#[derive(Deserialize)]
pub struct LoginRequest {
    pub email:    String,
    pub password: String,
}

#[derive(Serialize)]
struct LoginResponse {
    token: String,
}

// ── DB row returned for login lookup ─────────────────────────────────────────
#[derive(sqlx::FromRow)]
struct UserRow {
    id:            String,
    password_hash: String,
    role:          String,
}

// ── POST /auth/login ──────────────────────────────────────────────────────────
#[post("/login")]
pub async fn login(
    db:      Data<AppState>,
    request: Json<LoginRequest>,
) -> impl Responder {
    // 1. Fetch user row
    let row = match sqlx::query_as::<_, UserRow>(
        "SELECT id::text, password_hash, role FROM users WHERE email = $1",
    )
    .bind(&request.email)
    .fetch_one(&db.pool)
    .await
    {
        Ok(r)  => r,
        Err(_) => return HttpResponse::Unauthorized()
            .json(serde_json::json!({ "error": "Invalid credentials" })),
    };

    // 2. Verify password
    let parsed = match PasswordHash::new(&row.password_hash) {
        Ok(h)  => h,
        Err(_) => return HttpResponse::InternalServerError()
            .json(serde_json::json!({ "error": "Auth error" })),
    };

    if Argon2::default()
        .verify_password(request.password.as_bytes(), &parsed)
        .is_err()
    {
        return HttpResponse::Unauthorized()
            .json(serde_json::json!({ "error": "Invalid credentials" }));
    }

    // 3. Build JWT
    let exp = (Utc::now() + Duration::hours(JWT_EXPIRY_HOURS))
        .timestamp() as usize;

    let claims = Claims { sub: row.id, role: row.role, exp };

    match encode(&Header::default(), &claims, &EncodingKey::from_secret(JWT_SECRET)) {
        Ok(token) => HttpResponse::Ok().json(LoginResponse { token }),
        Err(_)    => HttpResponse::InternalServerError()
            .json(serde_json::json!({ "error": "Failed to create token" })),
    }
}

// ── Helper used by every protected handler ────────────────────────────────────
pub fn verify_jwt(token: &str) -> Result<Claims, ()> {
    decode::<Claims>(
        token,
        &DecodingKey::from_secret(JWT_SECRET),
        &Validation::default(),
    )
    .map(|data| data.claims)
    .map_err(|_| ())
}

// ── Extract Bearer token from Authorization header ────────────────────────────
pub fn bearer_from_header(req: &actix_web::HttpRequest) -> Option<String> {
    req.headers()
        .get("Authorization")?
        .to_str()
        .ok()?
        .strip_prefix("Bearer ")
        .map(|s| s.to_string())
}