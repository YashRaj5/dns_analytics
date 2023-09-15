# Databricks notebook source
# DBTITLE 1,Installing our libraries
# MAGIC %pip install tldextract dnstwist geoip2

# COMMAND ----------

import re
import os

# COMMAND ----------

current_user_name = dbutils.notebook.entry_point.getDbutils().notebook().getContext().tags().get("user").get()

# COMMAND ----------

def get_user_prefix():
  return re.sub(r'[^A-Za-z0-9_]', '_', re.sub(r'^([^@]+)(@.*)?$', r'\1', current_user_name))

# COMMAND ----------

current_user_name_prefix = get_user_prefix()

# COMMAND ----------

def get_default_path():
  return f'/tmp/{current_user_name_prefix}/dns_analytics'

# COMMAND ----------

try:
  dbutils.fs.mkdirs(get_default_path())
except:
  pass

# COMMAND ----------

def dbfs_file_exists(path: str):
  try:
    dbutils.fs.ls(path)
  except Exception as e:
    return False
  
  return True

# COMMAND ----------

if dbfs_file_exists('dbfs:/FileStore/dns_analytics/GeoLite2-City.mmdb') and not dbfs_file_exists(f'dbfs:{get_default_path()}/datasets/GeoLite2_City.mmdb'):
  dbutils.fs.cp('dbfs:/FileStore/dns_analytics/GeoLite2-City.mmdb', f'{get_default_path()}/datasets/GeoLite2_City.mmdb')

# COMMAND ----------

if dbfs_file_exists(f'dbfs:{get_default_path()}/datasets/GeoLite2_City.mmdb'):
  sc.addFile(f'dbfs:{get_default_path()}/datasets/GeoLite2_City.mmdb')

# COMMAND ----------

def get_default_database():
  return f'{current_user_name_prefix}_dns'

# COMMAND ----------

spark.sql(f'create database if not exists {get_default_database()}')
spark.sql(f'use {get_default_database()}')

# COMMAND ----------

print(f'Default database: {get_default_database()}')
print(f'Files are stored in {get_default_path()}')

# COMMAND ----------

spark.conf.set("spark.sql.execution.arrow.pyspark.enabled", "true")

# COMMAND ----------

# We will extract the registered_domain_extract and domain_extract fields from the URLHaus feeds
import tldextract
import numpy as np

# COMMAND ----------

def registered_domain_extract(uri):
    ext = tldextract.extract(uri)
    if (not ext.suffix):
        return " "
    else:
        return ext.registered_domain

# COMMAND ----------

def domain_extract(uri):
    ext = tldextract.extract(uri)
    if (not ext.suffix):
        return " "
    else:
        return ext.domain

# COMMAND ----------

# The next three lines are registering our user defined functions(UDFs) in the databricks runtime environment
registered_domain_extract = spark.udf.register("registered_domain_extract", registered_domain_extract)
domain_extract_udf = spark.udf.register("domain_extract", domain_extract)

# COMMAND ----------

# Load the DGA model. This is a pre-trained model that we will use to enrich our incoming DNS events. You will see how to train this model in a later step.
import mlflow
import mlflow.pyfunc

# COMMAND ----------

def get_and_register_ioc_detect_model():
  if dbfs_file_exists(f'dbfs:{get_default_path()}/new_model/dga_model'):
    model_path = f'dbfs:{get_default_path()}/new_model/dga_model'
  else:
    model_path = f'dbfs:{get_default_path()}/model'
  print(f"Loading model from {model_path}")
  loaded_model = mlflow.pyfunc.load_model(model_path)
  spark.udf.register("ioc_detect", loaded_model.predict)
  return loaded_model

# COMMAND ----------

def cleanup_files_and_database():
  try:
    dbutils.fs.rm(get_default_path(), True)
  except:
    pass
  try:
    spark.sql(f'drop database if exists {get_default_database()} cascade')
  except:
    pass
  try:
    from mlflow.tracking.client import MlflowClient
    client = MlflowClient()
    model_name = f"{get_user_prefix()}_dns_dga"
    client.delete_registered_model(model_name)
  except:
    pass
  try:
    dbutils.fs.rm("file:/tmp/dns-notebook-datasets", True)
  except:
    pass

# COMMAND ----------

import mlflow
experiment_name = f"/Users/{current_user_name}/dns_analytics_experiment"
mlflow.set_experiment(experiment_name) 
