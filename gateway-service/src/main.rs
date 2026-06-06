use actix_cors::Cors;
use actix_web::{middleware, web, App, HttpServer};
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
    env_logger::init_from_env(env_logger::Env::default().default_filter_or("info"));

    let pool = db::create_pool().await;
    log::info!("Gateway starting on 0.0.0.0:8080");
    
    HttpServer::new(move || {
        App::new()
            .wrap(
                Cors::default()
                .allow_any_origin()
                .allow_any_method()
                .allow_any_header()
                .supports_credentials()
            )
            .wrap(middleware::Logger::new("%a \"%r\" %s %b %T"))
            .app_data(web::Data::new(AppState { pool: pool.clone() }))
            .app_data(
                web::JsonConfig::default().error_handler(|err, _| {
                    let msg = err.to_string();
                    actix_web::error::InternalError::from_response(
                        err,
                        actix_web::HttpResponse::BadRequest()
                            .json(serde_json::json!({ "error": msg })),
                    ).into()
                }),
            )
            // Auth
            .service(web::scope("/auth").service(auth::login))
            // Users
            .service(web::scope("/user").service(user_service::create_user))
            // Predict
            .service(predict::forward_predict)
            // Train
            .service(train::forward_train)
            .service(train::init_base_model)
            // Activate + admin data routes
            .service(web::scope("/activate").service(activate::activate_model))
            .service(activate::list_models)
            .service(activate::list_training_runs)
            // Health
            .service(predict::health)
    })
    .bind(("0.0.0.0", 8080))?
    .run()
    .await
}