### 
### Changes the alias to the other Model version
### 
import argparse
import mlflow
from mlflow import MlflowClient

mlflow.set_registry_uri("databricks-uc")
c = MlflowClient()

p = argparse.ArgumentParser()
p.add_argument("--catalog", required=True)
p.add_argument("--schema", required=True)
p.add_argument("--model", required=True)
args = p.parse_args()

NAME = f"{args.catalog}.{args.schema}.{args.model}"


def champion_version():
    return int(c.get_model_version_by_alias(NAME, "champion").version)

def load_champion_version():
    # load through the alias, the way scoring code would
    m = mlflow.pyfunc.load_model(f"models:/{NAME}@champion")
    return m.metadata.run_id, champion_version()

start = champion_version()
other = 2 if start == 1 else 1
print("start: champion ->", start)

# promote the other version # this will be removed 
c.set_registered_model_alias(NAME, "champion", other)
print("after promote: champion ->", champion_version())
print("loaded:", load_champion_version())

# rollback
c.set_registered_model_alias(NAME, "champion", start)
print("after rollback: champion ->", champion_version())
print("loaded:", load_champion_version())

assert champion_version() == start, "rollback failed"
print("ROLLBACK OK")