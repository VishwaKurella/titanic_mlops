use actix_web::{web, App, HttpServer};
use sqlx::PgPool;

mod auth;
mod activate;
mod db;
mod predict;
mod train;
mod user_service;

pub struct AppState {
    pub pool: PgPool,
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    dotenvy::dotenv().ok();

    let pool = db::create_pool().await;

    HttpServer::new(move || {
        App::new()
            .app_data(web::Data::new(AppState { pool: pool.clone() }))
            // Auth
            .service(
                web::scope("/auth")
                    .service(auth::login)
            )
            // Users
            .service(
                web::scope("/user")
                    .service(user_service::create_user)
            )
            // Predict — any logged-in user
            .service(predict::forward_predict)
            // Train — ML_ENGINEER or ADMIN only (checked inside handler)
            .service(train::forward_train)
            // Activate model — ADMIN only (checked inside handler)
            .service(
                web::scope("/activate")
                    .service(activate::activate_model)
            )
            // Health
            .service(predict::health)
    })
    .bind(("0.0.0.0", 8080))?
    .run()
    .await
}