use actix_web::{HttpResponse, Responder, http, post, web::Json};
use serde::{Deserialize};

#[derive(Deserialize)]
struct ActivateRequest {
    name: String,
    id: String,
    password: String
}


#[post("/{modle_name}")]
pub async fn activate_modle(request: Json<ActivateRequest>) -> impl Responder {
    let request: ActivateRequest = request.into_inner();

    HttpResponse::Ok()
}



