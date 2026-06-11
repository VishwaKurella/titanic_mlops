use actix_multipart::Multipart;
use actix_web::{post, web::Data, HttpRequest, HttpResponse, Responder};
use futures_util::StreamExt;
use crate::{AppState, auth::{bearer_from_header, verify_jwt}, user_service::{ADMIN, ML_ENGINEER}};

fn auth_check(req: &HttpRequest) -> Result<crate::auth::Claims, HttpResponse> {
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

/// POST /train — multipart fields:
///   "file"       CSV data (optional — uses default dataset if absent)
///   "model_name" custom name for the model (optional)
///   "model_type" one of: SGDClassifier, RandomForestClassifier, LogisticRegression
///                (optional — defaults to SGDClassifier)
#[post("/train")]
pub async fn forward_train(
    req:    HttpRequest,
    _db:    Data<AppState>,
    mut mp: Multipart,
) -> impl Responder {
    let claims = match auth_check(&req) {
        Ok(c)  => c,
        Err(r) => return r,
    };

    let mut csv_bytes:  Vec<u8>        = Vec::new();
    let mut model_name: Option<String> = None;
    let mut model_type: Option<String> = None;

    while let Some(Ok(mut field)) = mp.next().await {
        match field.name() {
            Some("file") => {
                while let Some(Ok(chunk)) = field.next().await {
                    csv_bytes.extend_from_slice(&chunk);
                }
            }
            Some("model_name") => {
                let mut buf = Vec::new();
                while let Some(Ok(chunk)) = field.next().await { buf.extend_from_slice(&chunk); }
                model_name = String::from_utf8(buf).ok()
                    .map(|s| s.trim().to_string())
                    .filter(|s| !s.is_empty());
            }
            Some("model_type") => {
                let mut buf = Vec::new();
                while let Some(Ok(chunk)) = field.next().await { buf.extend_from_slice(&chunk); }
                model_type = String::from_utf8(buf).ok()
                    .map(|s| s.trim().to_string())
                    .filter(|s| !s.is_empty());
            }
            _ => {}
        }
    }

    let rows: Option<Vec<serde_json::Value>> = if csv_bytes.is_empty() {
        None
    } else {
        let mut reader = csv::Reader::from_reader(csv_bytes.as_slice());
        let parsed: Vec<serde_json::Value> = reader
            .deserialize::<serde_json::Map<String, serde_json::Value>>()
            .filter_map(|r| r.ok().map(serde_json::Value::Object))
            .collect();
        if parsed.is_empty() {
            return HttpResponse::BadRequest()
                .json(serde_json::json!({ "error": "CSV parsed to 0 rows — check format" }));
        }
        Some(parsed)
    };

    let body = serde_json::json!({
        "data":       rows,
        "model_name": model_name,
        "model_type": model_type,
        "user_id":    claims.sub,
    });

    forward_to_training("http://training-service:8001/incremental-train", &body).await
}

/// POST /initBaseModel — full train from default dataset, defaults to SGDClassifier.
/// Accepts optional JSON body: { "model_type": "RandomForestClassifier" }
#[post("/initBaseModel")]
pub async fn init_base_model(
    req:  HttpRequest,
    _db:  Data<AppState>,
    body: actix_web::web::Json<serde_json::Value>,
) -> impl Responder {
    let claims = match auth_check(&req) {
        Ok(c)  => c,
        Err(r) => return r,
    };

    let model_type = body.get("model_type")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string());

    let payload = serde_json::json!({
        "data":       null,
        "model_name": null,
        "model_type": model_type,
        "user_id":    claims.sub,
    });

    log::info!(
        "Base model init triggered by '{}' (type: {})",
        claims.username,
        payload["model_type"]
    );

    forward_to_training("http://training-service:8001/train", &payload).await
}

async fn forward_to_training(url: &str, body: &serde_json::Value) -> HttpResponse {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(120))
        .build()
        .unwrap();

    match client.post(url).json(body).send().await {
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