use actix_web::{post, web::{Data, Path}, HttpRequest, HttpResponse, Responder};
use crate::{AppState, auth::{bearer_from_header, verify_jwt}, user_service::ADMIN};

#[post("/{model_name}")]
pub async fn activate_model(
    req:        HttpRequest,
    db:         Data<AppState>,
    model_name: Path<String>,
) -> impl Responder {
    // 1. Verify JWT
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

    // 2. Check role
    if claims.role != ADMIN {
        return HttpResponse::Forbidden()
            .json(serde_json::json!({ "error": "Admin access required" }));
    }

    let model_name = model_name.into_inner();

    // 3. Check model exists
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

    // 4. Swap active model in a transaction
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

    // 5. Tell prediction service to drop its cached model
    let _ = reqwest::Client::new()
        .post("http://prediction-service:8000/reload")
        .send()
        .await;

    HttpResponse::Ok().json(serde_json::json!({
        "status":     "activated",
        "model_name": model_name,
        "activated_by": claims.sub,
    }))
}