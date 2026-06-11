use actix_web::{HttpRequest, HttpResponse, Responder, post, web::{Data, Json}};
use argon2::{Argon2, PasswordVerifier, password_hash::PasswordHash};
use jsonwebtoken::{encode, decode, Header, EncodingKey, DecodingKey, Validation};
use serde::{Deserialize, Serialize};
use chrono::{Utc, Duration};
use crate::{AppState, user_service::{ADMIN, ML_ENGINEER}};

fn jwt_secret() -> Vec<u8> {
    std::env::var("JWT_SECRET")
        .expect("JWT_SECRET must be set in .env")
        .into_bytes()
}

fn jwt_expiry_hours() -> i64 {
    std::env::var("JWT_EXPIRY_HOURS")
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(8)
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct Claims {
    pub sub:      String,
    pub role:     String,
    pub username: String,
    pub exp:      usize,
}

#[derive(Deserialize)]
pub struct LoginRequest {
    pub email:    String,
    pub password: String,
}

#[derive(Serialize)]
struct LoginResponse {
    token:    String,
    role:     String,
    username: String,
}

#[derive(sqlx::FromRow)]
struct UserRow {
    id:            String,
    username:      String,
    password_hash: String,
    role:          String,
}

#[post("/login")]
pub async fn login(
    db:      Data<AppState>,
    request: Json<LoginRequest>,
) -> impl Responder {
    let row = match sqlx::query_as::<_, UserRow>(
        "SELECT id::text, username, password_hash, role FROM users WHERE email = $1",
    )
    .bind(&request.email)
    .fetch_one(&db.pool)
    .await
    {
        Ok(r)  => r,
        Err(_) => return HttpResponse::Unauthorized()
            .json(serde_json::json!({ "error": "Invalid credentials" })),
    };

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

    let exp = (Utc::now() + Duration::hours(jwt_expiry_hours()))
        .timestamp() as usize;

    let claims = Claims {
        sub:      row.id,
        role:     row.role.clone(),
        username: row.username.clone(),
        exp,
    };

    match encode(
        &Header::default(),
        &claims,
        &EncodingKey::from_secret(&jwt_secret()),
    ) {
        Ok(token) => HttpResponse::Ok().json(LoginResponse {
            token,
            role:     row.role,
            username: row.username,
        }),
        Err(_) => HttpResponse::InternalServerError()
            .json(serde_json::json!({ "error": "Failed to create token" })),
    }
}

pub fn verify_jwt(token: &str) -> Result<Claims, ()> {
    decode::<Claims>(
        token,
        &DecodingKey::from_secret(&jwt_secret()),
        &Validation::default(),
    )
    .map(|data| data.claims)
    .map_err(|_| ())
}

pub fn bearer_from_header(req: &actix_web::HttpRequest) -> Option<String> {
    req.headers()
        .get("Authorization")?
        .to_str()
        .ok()?
        .strip_prefix("Bearer ")
        .map(|s| s.to_string())
}

pub fn auth_check(req: &HttpRequest) -> Result<crate::auth::Claims, HttpResponse> {
    let token = match bearer_from_header(req) {
        Some(t) => t,
        None    => return Err(HttpResponse::Unauthorized()
            .json(serde_json::json!({ "error": "Missing Authorization header" }))),
    };
    let claims = match verify_jwt(&token) {
        Ok(c)  => c,
        Err(_) => return Err(HttpResponse::Unauthorized()
            .json(serde_json::json!({ "error": "Invalid or expired token" }))),
    };
    if claims.role != ADMIN && claims.role != ML_ENGINEER {
        return Err(HttpResponse::Forbidden()
            .json(serde_json::json!({ "error": "ML_ENGINEER or ADMIN role required" })));
    }
    Ok(claims)
}
