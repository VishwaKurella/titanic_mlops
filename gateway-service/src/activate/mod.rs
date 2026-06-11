use actix_web::{get, post, web::{Data, Path}, HttpRequest, HttpResponse, Responder};
use crate::{AppState, auth::{bearer_from_header, verify_jwt}, user_service::ADMIN};

#[post("/{model_name}")]
pub async fn activate_model(
    req:        HttpRequest,
    db:         Data<AppState>,
    model_name: Path<String>,
) -> impl Responder {
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

    if claims.role != ADMIN {
        return HttpResponse::Forbidden()
            .json(serde_json::json!({ "error": "Admin access required" }));
    }

    let model_name = model_name.into_inner();

    let exists = match sqlx::query_scalar::<_, bool>(
        "SELECT EXISTS(SELECT 1 FROM models WHERE model_name = $1)",
    )
    .bind(&model_name)
    .fetch_one(&db.pool)
    .await
    {
        Ok(e)  => e,
        Err(_) => return HttpResponse::InternalServerError()
            .json(serde_json::json!({ "error": "Database error" })),
    };

    if !exists {
        return HttpResponse::NotFound()
            .json(serde_json::json!({ "error": "Model not found" }));
    }

    let mut tx = match db.pool.begin().await {
        Ok(t)  => t,
        Err(_) => return HttpResponse::InternalServerError()
            .json(serde_json::json!({ "error": "Transaction error" })),
    };

    let deactivate = sqlx::query("UPDATE models SET active = FALSE")
        .execute(&mut *tx).await;
    let activate = sqlx::query(
        "UPDATE models SET active = TRUE WHERE model_name = $1",
    )
    .bind(&model_name)
    .execute(&mut *tx).await;

    if deactivate.is_err() || activate.is_err() {
        return HttpResponse::InternalServerError()
            .json(serde_json::json!({ "error": "Failed to update model" }));
    }

    if tx.commit().await.is_err() {
        return HttpResponse::InternalServerError()
            .json(serde_json::json!({ "error": "Failed to commit" }));
    }

    // Tell prediction service to clear its cache
    let _ = reqwest::Client::new()
        .post("http://prediction-service:8000/reload")
        .send()
        .await;

    log::info!("Model '{}' activated by user '{}'", model_name, claims.sub);

    HttpResponse::Ok().json(serde_json::json!({
        "status":       "activated",
        "model_name":   model_name,
        "activated_by": claims.username,
    }))
}

// Proxy to training service — ADMIN only
#[get("/models")]
pub async fn list_models(req: HttpRequest) -> impl Responder {
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

    if claims.role != ADMIN {
        return HttpResponse::Forbidden()
            .json(serde_json::json!({ "error": "Admin access required" }));
    }

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(5))
        .build()
        .unwrap();

    match client
        .get("http://training-service:8001/models")
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

#[get("/training-runs")]
pub async fn list_training_runs(req: HttpRequest) -> impl Responder {
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
    if claims.role != ADMIN {
        return HttpResponse::Forbidden()
            .json(serde_json::json!({ "error": "Admin access required" }));
    }

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(5)).build().unwrap();

    match client.get("http://training-service:8001/training-runs").send().await {
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

// Add this to gateway-service/src/activate/mod.rs
// Proxies to training-service — no auth required (just metadata)
#[get("/supported-models")]
pub async fn supported_models() -> impl Responder {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(5))
        .build()
        .unwrap();

    match client.get("http://training-service:8001/supported-models").send().await {
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