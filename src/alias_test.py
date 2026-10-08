import mlflow
from mlflow import MlflowClient

mlflow.set_registry_uri("databricks-uc")
c = MlflowClient()
NAME = "workspace.nhanes_demo.dummy_model"

# challenger -> v1, champion -> v2
c.set_registered_model_alias(NAME, "champion", 1)
c.set_registered_model_alias(NAME, "challenger", 2)

for v in c.search_model_versions(f"name='{NAME}'"):
    print(v.version, v.aliases)