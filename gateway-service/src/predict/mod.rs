use actix_web::{get, post, web::{Data, Json}, HttpRequest, HttpResponse, Responder};
use serde::{Deserialize, Serialize};
use crate::{AppState, auth::{auth_check, bearer_from_header, verify_jwt}};

/// Passenger input — all engineered features are derived server-side.
/// Name, SibSp, Parch are optional for backward compatibility:
///   - If Name is absent, Title is inferred from Sex + Age
///   - If SibSp/Parch are absent, FamilySize defaults to 1 (travelling alone)
#[derive(Serialize, Deserialize)]
pub struct Passenger {
    #[serde(rename = "Pclass")]
    pub pclass: i32,

    #[serde(rename = "Sex")]
    pub sex: String,

    #[serde(rename = "Age")]
    pub age: Option<f32>,

    #[serde(rename = "Fare")]
    pub fare: Option<f32>,

    #[serde(rename = "Embarked")]
    pub embarked: Option<String>,

    // ── Feature-engineering inputs (optional) ────────────────────────────────
    /// Full name e.g. "Braund, Mr. Owen Harris" — used to extract title.
    /// If absent, title is inferred from Sex + Age.
    #[serde(rename = "Name")]
    pub name: Option<String>,

    /// Number of siblings/spouses aboard (default 0)
    #[serde(rename = "SibSp")]
    pub sibsp: Option<i32>,

    /// Number of parents/children aboard (default 0)
    #[serde(rename = "Parch")]
    pub parch: Option<i32>,
}

#[post("/predict")]
pub async fn forward_predict(
    req:     HttpRequest,
    _db:     Data<AppState>,
    payload: Json<Passenger>,
) -> impl Responder {
    let token = match bearer_from_header(&req) {
        Some(t) => t,
        None    => return HttpResponse::Unauthorized()
            .json(serde_json::json!({ "error": "Missing Authorization header" })),
    };
    if verify_jwt(&token).is_err() {
        return HttpResponse::Unauthorized()
            .json(serde_json::json!({ "error": "Invalid or expired token" }));
    }

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(5))
        .build()
        .unwrap();

    match client
        .post("http://prediction-service:8000/predict")
        .json(&payload.0)
        .send()
        .await
    {
        Ok(resp) => {
            let status = resp.status().as_u16();
            let body   = resp.text().await.unwrap_or_default();
            HttpResponse::build(
                actix_web::http::StatusCode::from_u16(status).unwrap()
            ).content_type("application/json").body(body)
        }
        Err(e) => HttpResponse::BadGateway()
            .json(serde_json::json!({ "error": format!("{e}") })),
    }
}

#[get("/health")]
pub async fn health() -> impl Responder {
    HttpResponse::Ok().json(serde_json::json!({ "status": "ok" }))
}

#[post("/refresh-cache")]
pub async fn refresh_cache(req:  HttpRequest) -> impl Responder{
    let _: crate::auth::Claims = match auth_check(&req) {
        Ok(c)  => c,
        Err(r) => return r,
    };

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(120))
        .build()
        .unwrap();
    match client.post("http://training-service:8001/refresh-cache").send().await {
        Ok(resp) => {
            let status = resp.status().as_u16();
            let body   = resp.text().await.unwrap_or_default();
            HttpResponse::build(
                actix_web::http::StatusCode::from_u16(status).unwrap()
            ).content_type("application/json").body(body)
        },
        Err(e) => HttpResponse::BadGateway()
            .json(serde_json::json!({ "error": format!("{e}") }))
    }
}