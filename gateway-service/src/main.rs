use actix_web::{
    post,
    web,
    App,
    HttpResponse,
    HttpServer,
    Responder
};

mod activate;
mod user_service;
mod db;

use serde::{Deserialize, Serialize};

#[derive(Serialize, Deserialize)]
struct Passenger {
    Pclass: i32,
    Sex: String,
    Age: f32,
    Fare: f32,
    Embarked: String,
}

#[post("/predict")]
async fn predict(
    payload: web::Json<Passenger>
) -> impl Responder {

    let client = reqwest::Client::new();

    let response = client
        .post("http://prediction-service:8000/predict")
        .json(&payload.0)
        .send()
        .await;

    match response {

        Ok(resp) => {

            let body = resp.text().await.unwrap();

            HttpResponse::Ok().body(body)
        }

        Err(e) => {

            HttpResponse::InternalServerError()
                .body(format!("{}", e))
        }
    }
}



#[actix_web::main]

async fn main() -> std::io::Result<()> {

    HttpServer::new(|| {

        App::new()
            .service(predict)

    })

    .bind(("0.0.0.0", 8080))?

    .run()

    .await
}