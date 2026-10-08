import argparse

import mlflow
import numpy as np
from mlflow.models import infer_signature
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split

p = argparse.ArgumentParser()
p.add_argument("--catalog", required=True)
p.add_argument("--schema", required=True)
p.add_argument("--experiment", required=True)
p.add_argument("--model", required=True)
args = p.parse_args()

MODEL_NAME = f"{args.catalog}.{args.schema}.{args.model}"
SEED = 42

mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment(args.experiment)

rng = np.random.default_rng(SEED)
X = rng.normal(size=(200, 3))
y = rng.integers(0, 2, size=200)
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.3, random_state=SEED
)

model = LogisticRegression()
model.fit(X_train, y_train)
accuracy = model.score(X_test, y_test)
print(f"accuracy on random data: {accuracy:.3f}")

with mlflow.start_run():
    mlflow.log_param("seed", SEED)
    mlflow.log_metric("accuracy", accuracy)
    signature = infer_signature(X_train, model.predict(X_train))
    mlflow.sklearn.log_model(
        model,
        name="model",
        signature=signature,
        registered_model_name=MODEL_NAME,
    )