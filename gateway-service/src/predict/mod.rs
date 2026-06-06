use actix_web::{get, post, web::{Data, Json}, HttpRequest, HttpResponse, Responder};
use serde::{Deserialize, Serialize};
use crate::{AppState, auth::{bearer_from_header, verify_jwt}};

#[derive(Serialize, Deserialize)]
pub struct Passenger {
    pub Pclass:   i32,
    pub Sex:      String,
    pub Age:      Option<f32>,
    pub Fare:     Option<f32>,
    pub Embarked: Option<String>,
}

#[post("/predict")]
pub async fn forward_predict(
    req:     HttpRequest,
    _db:     Data<AppState>,
    payload: Json<Passenger>,
) -> impl Responder {
    // Any valid logged-in user can predict
    let token  = match bearer_from_header(&req) {
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
            ).body(body)
        }
        Err(e) => HttpResponse::BadGateway()
            .json(serde_json::json!({ "error": format!("{e}") })),
    }
}

#[get("/health")]
pub async fn health() -> impl Responder {
    HttpResponse::Ok().json(serde_json::json!({ "status": "ok" }))
}