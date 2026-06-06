from sklearn.linear_model import SGDClassifier
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import StandardScaler, OneHotEncoder
from sklearn.impute import SimpleImputer

NUMERIC_FEATURES     = ["Age", "Fare", "Pclass"]
CATEGORICAL_FEATURES = ["Sex", "Embarked"]
FEATURES             = NUMERIC_FEATURES + CATEGORICAL_FEATURES
TARGET               = "Survived"
DEFAULT_DATASET      = "/shared/datasets/Titanic-Dataset.csv"

def build_pipeline() -> Pipeline:
    num = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler",  StandardScaler()),
    ])
    cat = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("encoder", OneHotEncoder(handle_unknown="ignore")),
    ])
    pre = ColumnTransformer([("num", num, NUMERIC_FEATURES), ("cat", cat, CATEGORICAL_FEATURES)])
    return Pipeline([
        ("preprocessor", pre),
        ("classifier",   SGDClassifier(loss="log_loss", random_state=42)),
    ])