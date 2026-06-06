use actix_multipart::Multipart;
use actix_web::{post, web::Data, HttpRequest, HttpResponse, Responder};
use futures_util::StreamExt;
use crate::{AppState, auth::{bearer_from_header, verify_jwt}, user_service::{ADMIN, ML_ENGINEER}};

#[post("/train")]
pub async fn forward_train(
    req: HttpRequest,
    _db: Data<AppState>,
    mut mp: Multipart,
) -> impl Responder {
    // 1. Verify JWT and check role
    let token  = match bearer_from_header(&req) {
        Some(t) => t,
        None    => return HttpResponse::Unauthorized()
            .json(serde_json::json!({ "error": "Missing Authorization header" })),
    };
    let claims = match verify_jwt(&token) {
        Ok(c)  => c,
        Err(_) => return HttpResponse::Unauthorized()
            .json(serde_json::json!({ "error": "Invalid or expired token" })),
    };

    if claims.role != ADMIN && claims.role != ML_ENGINEER {
        return HttpResponse::Forbidden()
            .json(serde_json::json!({ "error": "ML_ENGINEER or ADMIN role required" }));
    }

    // 2. Pull CSV bytes from multipart field "file"
    let mut csv_bytes: Vec<u8> = Vec::new();
    let mut model_name: Option<String> = None;

    while let Some(Ok(mut field)) = mp.next().await {
        match field.name() {
            Some("file") => {
                while let Some(Ok(chunk)) = field.next().await {
                    csv_bytes.extend_from_slice(&chunk);
                }
            }
            Some("model_name") => {
                let mut buf = Vec::new();
                while let Some(Ok(chunk)) = field.next().await {
                    buf.extend_from_slice(&chunk);
                }
                model_name = String::from_utf8(buf).ok();
            }
            _ => {}
        }
    }

    // 3. Parse CSV → JSON rows  (empty = use default dataset on training service)
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
                .json(serde_json::json!({ "error": "CSV parsed to 0 rows" }));
        }
        Some(parsed)
    };

    let body = serde_json::json!({
        "data":       rows,          // null = training service uses its default dataset
        "model_name": model_name,    // null = train on top of active model
        "user_id":    claims.sub,
    });

    // 4. Forward to training service (longer timeout — training takes time)
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(120))
        .build()
        .unwrap();

    match client
        .post("http://training-service:8001/incremental-train")
        .json(&body)
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


#[post("/initBaseModel")]
pub async fn init_base_model(
    req: HttpRequest,
    _db: Data<AppState>,
) -> impl Responder {
    // 1. Verify JWT and check role
    let token  = match bearer_from_header(&req) {
        Some(t) => t,
        None    => return HttpResponse::Unauthorized()
            .json(serde_json::json!({ "error": "Missing Authorization header" })),
    };
    let claims = match verify_jwt(&token) {
        Ok(c)  => c,
        Err(_) => return HttpResponse::Unauthorized()
            .json(serde_json::json!({ "error": "Invalid or expired token" })),
    };

    if claims.role != ADMIN && claims.role != ML_ENGINEER {
        return HttpResponse::Forbidden()
            .json(serde_json::json!({ "error": "ML_ENGINEER or ADMIN role required" }));
    }

    let body = serde_json::json!({
        "data":       null,          // null = training service uses its default dataset
        "model_name": null,    // null = train on top of active model
        "user_id":    claims.sub,
    });

    // 4. Forward to training service (longer timeout — training takes time)
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(120))
        .build()
        .unwrap();

    match client
        .post("http://training-service:8001/train")
        .json(&body)
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

